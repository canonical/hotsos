import copy
import os
import re

# NOTE: we import direct from searchkit rather than hotsos.core.search to
#       avoid circular dependency issues.
from searchkit import (
    FileSearcher,
    SearchDef,
    SequenceSearchDef,
)
from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers.cli import CLIHelper, CLIHelperFile
from hotsos.core.host_helpers.common import HostHelpersBase
from hotsos.core.log import log
from hotsos.core.utils import mktemp_dump

# compatible with ip addr and ip link
# this one is name and state
IP_IFACE_NAME = r"^\d+:\s+(\S+):\s+.+mtu\s+(\d+).+state\s+(\S+)"
IP_IFACE_NAME_TEMPLATE = r"^\d+:\s+({}):\s+.+"
IP_IFACE_V4_ADDR = r".+(inet) ([\d\.]+)/(\d+) (?:brd \S+ )?scope global (\S+)"
IP_IFACE_V6_ADDR = r".+(inet6) (\S+)/(\d+) scope global (\S+)"
IP_IFACE_HW_ADDR = r".+(link/ether) (\S+) brd .+"
IP_IFACE_HW_ADDR_TEMPLATE = r".+(link/ether) {} brd .+"
IP_IFACE_VXLAN_INFO = r"\s+(vxlan) id (\d+) local (\S+) dev (\S+) .+"
IP_EOF = r"^$"


class NetworkPort(HostHelpersBase):

    def __init__(self, name, addresses, hwaddr, state, encap_info,
                 mtu, namespace=None):
        self.name = name
        self.addresses = addresses
        self.hwaddr = hwaddr
        self.state = state
        self.encap_info = encap_info
        self.mtu = mtu
        self.namespace = namespace
        super().__init__()

    @property
    def cache_root(self):
        """
        Cache this information at the plugin level rather than globally.
        """
        return HotSOSConfig.plugin_tmp_dir

    @property
    def cache_type(self):
        return 'network_ports'

    @property
    def cache_name(self):
        if self.namespace:
            return f"ns-{self.namespace}-port-{self.name}"

        return f"port-{self.name}"

    def cache_load(self, key):
        contents = self.cache.get(key)
        if not contents:
            log.debug("network port %s not found in cache", self.name)
            return None

        log.debug("loading network port %s from cache", self.name)
        return contents

    def cache_save(self, key, value):
        log.debug("saving network port %s to cache", self.name)
        self.cache.set(key, value)

    def to_dict(self):
        info = {'addresses': copy.deepcopy(self.addresses),
                'hwaddr': self.hwaddr,
                'mtu': self.mtu,
                'state': self.state,
                'speed': self.speed}
        if self.namespace:
            info['namespace'] = self.namespace

        return {self.name: info}

    @property
    def speed(self):
        # need to strip @* since sosreport does that too
        name = self.name.partition('@')[0]
        out = CLIHelper().ethtool(interface=name)
        if out:
            for line in out:
                ret = re.match(r'\s*Speed:\s+(\S+)', line)
                if ret:
                    return ret.group(1)

        return 'unknown'

    @property
    def stats(self):
        """ Get ip link info for the interface. """
        counters = self.cache_load('stats') or {}
        if counters:
            return counters

        s = FileSearcher()
        seqdef = SequenceSearchDef(
                    # match start of interface
                    start=SearchDef(IP_IFACE_NAME_TEMPLATE.format(self.name)),
                    # match body of interface
                    body=SearchDef(r".+"),
                    # match next interface or EOF
                    end=SearchDef([IP_IFACE_NAME, IP_EOF]),
                    tag="ifaces")
        stats_raw = []
        with CLIHelperFile() as cli:
            s.add(seqdef, path=cli.ip_link())
            results = s.run()
            for section in results.find_sequence_sections(seqdef).values():
                for result in section:
                    if result.tag == seqdef.body_tag:
                        stats_raw.append(result.get(0))

        if not stats_raw:
            return {}

        # NOTE: we only expect one match
        for i, line in enumerate(stats_raw):
            ret = re.compile(r"\s+([RT]X):\s+.+").findall(line)
            if not ret:
                continue

            rxtx = ret[0].lower()
            ret = re.compile(r"\s*([a-z]+)\s*").findall(line)
            if not ret:
                continue

            for j, column in enumerate(ret):
                value = int(stats_raw[i + 1].split()[j])
                if column in ['packets', 'dropped', 'errors',
                              'overrun']:
                    if rxtx not in counters:
                        counters[rxtx] = {}

                    counters[rxtx][column] = value

        if counters:
            self.cache_save('stats', counters)
            return counters

        return {}


class HostNetworkingHelper(HostHelpersBase):

    def __init__(self):
        super().__init__()
        self._host_interfaces = None
        self._host_ns_interfaces = None
        self.cli = CLIHelper()

    @property
    def cache_type(self):
        return 'networks'

    @property
    def cache_name(self):
        # this is a global cache i.e. shared by all plugins
        return 'network-helper'

    def cache_load(self, key, all_namespaces=False, namespace=None):
        """
        @param all_namespaces: Set to True to if we are retrieving network info
                               for all namespaces.
        @param namespace: Name of specific namespace we are retrieving from.
                          Takes precedence over all_namespaces.
        """
        log.debug("loading network helper info from cache (all_namespaces=%s, "
                  "namespace=%s)", all_namespaces, namespace)
        if namespace is not None:
            contents = self.cache.get(f'ns-{namespace}-{key}')
        elif all_namespaces:
            contents = self.cache.get(f'ns-{key}')
        else:
            contents = self.cache.get(key)

        if contents:
            return contents

        log.debug("network helper info not available in cache "
                  "(all_namespaces=%s, namespace=%s)", all_namespaces,
                  namespace)
        return None

    def cache_save(self, key, value, all_namespaces=False, namespace=None):
        log.debug("saving network helper info to cache (all_namespaces=%s, "
                  "namespaces=%s)", all_namespaces, namespace)
        if namespace is not None:
            self.cache.set(f'ns-{namespace}-{key}', value)
        elif all_namespaces:
            self.cache.set(f'ns-{key}', value)
        else:
            self.cache.set(key, value)

    @staticmethod
    def _extract_iface_info(seqdef, section, search_obj):
        addrs = []
        encap_info = None
        hwaddr = None
        name = None
        mtu = None
        state = None
        for result in section:
            # infer ns name from filename prefix
            ns_name = None
            source = search_obj.resolve_source_id(result.source_id)
            ret = re.match(r'^__ns_start__(\S+)__ns__end__',
                           os.path.basename(source))
            if ret:
                ns_name = ret.group(1)

            if result.tag == seqdef.start_tag:
                name = result.get(1)
                mtu = int(result.get(2))
                state = result.get(3)
            elif result.tag == seqdef.body_tag:
                if result.get(1) in ['inet', 'inet6']:
                    addrs.append(result.get(2))
                elif result.get(1) in ['vxlan']:
                    encap_info = {result.get(1): {
                                      'id': result.get(2),
                                      'local_ip': result.get(3),
                                      'dev': result.get(4)}}
                else:
                    hwaddr = result.get(2)

        return {'name': name, 'addresses': addrs, 'hwaddr': hwaddr, 'mtu': mtu,
                'state': state, 'encap_info': encap_info, 'namespace': ns_name}

    @property
    def _ip_addr_show_iface_sequence_def(self):
        return SequenceSearchDef(start=SearchDef(IP_IFACE_NAME),
                                 body=SearchDef([IP_IFACE_V4_ADDR,
                                                 IP_IFACE_V6_ADDR,
                                                 IP_IFACE_HW_ADDR,
                                                 IP_IFACE_VXLAN_INFO]),
                                 tag='ip_addr_show')

    def get_ns_interfaces(self, namespace):
        """ Get all network ports for the given namespace.

        @param namespace: name of namespace
        @return: generator of NetworkPort objects
        """
        interfaces_raw = self.cache_load('interfaces',
                                         namespace=namespace) or []
        if not interfaces_raw:
            seq = self._ip_addr_show_iface_sequence_def
            search_obj = FileSearcher()
            ip_addr = self.cli.ns_ip_addr(namespace=namespace)
            prefix = f"__ns_start__{namespace}__ns__end__"
            path = mktemp_dump(''.join(ip_addr), prefix=prefix)
            try:
                search_obj.add(seq, path)
                r = search_obj.run()
                sections = r.find_sequence_sections(seq, path).values()
                for section in sections:
                    interfaces_raw.append(self._extract_iface_info(seq,
                                                                   section,
                                                                   search_obj))
            finally:
                os.unlink(path)

            self.cache_save('interfaces', interfaces_raw, namespace=namespace)

        for iface in interfaces_raw:
            yield NetworkPort(**iface)

    def _get_interfaces(self, all_namespaces=False):
        """
        Get all interfaces in ip address show.

        @param all_namespaces: if set to True will get interfaces from all
        namespaces on the host.
        @return: list of NetworkPort objects for each interface found.
        """
        interfaces_raw = self.cache_load('interfaces',
                                         all_namespaces=all_namespaces) or []
        if not interfaces_raw:
            seq = self._ip_addr_show_iface_sequence_def
            search_obj = FileSearcher()
            if all_namespaces:
                for ns in self.cli.ip_netns():
                    ns_name = ns.partition(" ")[0]
                    ip_addr = self.cli.ns_ip_addr(namespace=ns_name)
                    prefix = f"__ns_start__{ns_name}__ns__end__"
                    path = mktemp_dump(''.join(ip_addr), prefix=prefix)
                    search_obj.add(seq, path)
            else:
                path = mktemp_dump(''.join(self.cli.ip_addr()))
                search_obj.add(seq, path)

            if not search_obj.files:
                log.debug("no network info found (all_namespaces=%s)",
                          all_namespaces)
                return []

            r = search_obj.run()
            for path in search_obj.files:
                try:
                    sections = r.find_sequence_sections(seq, path).values()
                    for section in sections:
                        interfaces_raw.append(self._extract_iface_info(
                                                                seq,
                                                                section,
                                                                search_obj))
                finally:
                    os.unlink(path)

            self.cache_save('interfaces', interfaces_raw,
                            all_namespaces=all_namespaces)

        for iface in interfaces_raw:
            yield NetworkPort(**iface)

        return None

    @property
    def host_interfaces(self):
        if self._host_interfaces is not None:
            return self._host_interfaces

        self._host_interfaces = list(self._get_interfaces())
        return self._host_interfaces

    @property
    def host_ns_interfaces(self):
        if self._host_ns_interfaces is not None:
            return self._host_ns_interfaces

        self._host_ns_interfaces = list(
                                     self._get_interfaces(all_namespaces=True))
        return self._host_ns_interfaces

    @property
    def host_interfaces_all(self):
        return self.host_interfaces + self.host_ns_interfaces

    def get_interface_with_hwaddr(self, hwaddr):
        """ Returns first found. """
        for iface in self.host_interfaces_all:
            if iface.hwaddr == hwaddr:
                return iface

        return None

    def get_interface_with_addr(self, addr):
        for iface in self.host_interfaces_all:
            for _addr in iface.addresses:
                if _addr.startswith(addr):
                    return iface

        return None

    def get_interface_with_name(self, name):
        for iface in self.host_interfaces_all:
            if iface.name == name:
                return iface

        return None

    def host_interface_exists(self, name, check_namespaces=True):
        names = [_iface.name for _iface in self.host_interfaces]
        if name in names:
            return True

        if not check_namespaces:
            return False

        names = [_iface.name for _iface in self.host_ns_interfaces]
        if name in names:
            return True

        return False
