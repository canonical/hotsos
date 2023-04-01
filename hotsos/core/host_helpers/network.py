import copy
import os
import re

from hotsos.core.log import log
from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers.common import HostHelpersBase
from hotsos.core.host_helpers.cli import CLIHelper
from hotsos.core.utils import mktemp_dump
# NOTE: we import direct from searchkit rather than hotsos.core.search to
#       avoid circular dependency issues.
from searchkit import (
    FileSearcher,
    SearchDef,
    SequenceSearchDef,
)

# compatible with ip addr and ip link
# this one is name and state
IP_IFACE_NAME = r"^\d+:\s+(\S+):\s+.+state\s+(\S+)"
IP_IFACE_NAME_TEMPLATE = r"^\d+:\s+({}):\s+.+"
IP_IFACE_V4_ADDR = r".+(inet) ([\d\.]+)/(\d+) (?:brd \S+ )?scope global (\S+)"
IP_IFACE_V6_ADDR = r".+(inet6) (\S+)/(\d+) scope global (\S+)"
IP_IFACE_HW_ADDR = r".+(link/ether) (\S+) brd .+"
IP_IFACE_HW_ADDR_TEMPLATE = r".+(link/ether) {} brd .+"
IP_IFACE_VXLAN_INFO = r"\s+(vxlan) id (\d+) local (\S+) dev (\S+) .+"
IP_EOF = r"^$"


class NetworkPort(HostHelpersBase):

    def __init__(self, name, addresses, hwaddr, state, encap_info,
                 namespace=None):
        self.name = name
        self.addresses = addresses
        self.hwaddr = hwaddr
        self.state = state
        self.encap_info = encap_info
        self.namespace = namespace
        self.cli_helper = CLIHelper()
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
            return "ns-{}-port-{}".format(self.namespace, self.name)

        return "port-{}".format(self.name)

    def cache_load(self):
        contents = self.cache.get('stats')
        if not contents:
            log.debug("network port %s not found in cache", self.name)
            return

        log.debug("loading network port %s from cache", self.name)
        return contents

    def cache_save(self, data):
        log.debug("saving network port %s to cache", self.name)
        self.cache.set('stats', data)

    def to_dict(self):
        info = {'addresses': copy.deepcopy(self.addresses),
                'hwaddr': self.hwaddr,
                'state': self.state,
                'speed': self.speed}
        if self.namespace:
            info['namespace'] = self.namespace

        return {self.name: info}

    @property
    def speed(self):
        # need to strip @* since sosreport does that too
        name = self.name.partition('@')[0]
        out = self.cli_helper.ethtool(interface=name)
        if out:
            for line in out:
                ret = re.match(r'\s*Speed:\s+(\S+)', line)
                if ret:
                    return ret.group(1)

        return 'unknown'

    @property
    def stats(self):
        """ Get ip link info for the interface. """
        counters = self.cache_load() or {}
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
        f_ip_link_show = mktemp_dump(''.join(self.cli_helper.ip_link()))
        s.add(seqdef, path=f_ip_link_show)
        results = s.run()
        os.unlink(f_ip_link_show)
        stats_raw = []
        for section in results.find_sequence_sections(seqdef).values():
            for result in section:
                if result.tag == seqdef.body_tag:
                    stats_raw.append(result.get(0))

        if not stats_raw:
            return {}

        # NOTE: we only expect one match
        for i, line in enumerate(stats_raw):
            ret = re.compile(r"\s+([RT]X):\s+.+").findall(line)
            if ret:
                rxtx = ret[0].lower()
                ret = re.compile(r"\s*([a-z]+)\s*").findall(line)
                if ret:
                    for j, column in enumerate(ret):
                        value = int(stats_raw[i + 1].split()[j])
                        if column in ['packets', 'dropped', 'errors',
                                      'overrun']:
                            if rxtx not in counters:
                                counters[rxtx] = {}

                            counters[rxtx][column] = value

        if counters:
            self.cache_save(counters)
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

    def cache_load(self, namespaces=False):
        log.debug("loading network helper info from cache (namespaces=%s)",
                  namespaces)
        if namespaces:
            contents = self.cache.get('ns-interfaces')
        else:
            contents = self.cache.get('interfaces')

        if contents:
            return contents

        log.debug("network helper info not available in cache "
                  "(namespaces=%s)", namespaces)

    def cache_save(self, data, namespaces=False):
        log.debug("saving network helper info to cache (namespaces=%s)",
                  namespaces)
        if namespaces:
            self.cache.set('ns-interfaces', data)
        else:
            self.cache.set('interfaces', data)

    def _get_interfaces(self, namespaces=False):
        """
        Get all interfaces in ip address show.

        @param namespaces: if set to True will get interfaces from all
        namespaces on the host.
        @return: list of NetworkPort objects for each interface found.
        """
        interfaces = []

        interfaces_raw = self.cache_load(namespaces=namespaces) or []
        if interfaces_raw:
            for iface in interfaces_raw:
                interfaces.append(NetworkPort(**iface))

            return interfaces

        seq = SequenceSearchDef(start=SearchDef(IP_IFACE_NAME),
                                body=SearchDef([IP_IFACE_V4_ADDR,
                                                IP_IFACE_V6_ADDR,
                                                IP_IFACE_HW_ADDR,
                                                IP_IFACE_VXLAN_INFO]),
                                tag='ip_addr_show')
        search_obj = FileSearcher()
        if namespaces:
            for ns in self.cli.ip_netns():
                ns_name = ns.partition(" ")[0]
                ip_addr = self.cli.ns_ip_addr(namespace=ns_name)
                prefix = "__ns_start__{}__ns__end__".format(ns_name)
                path = mktemp_dump(''.join(ip_addr), prefix=prefix)
                search_obj.add(seq, path)
        else:
            path = mktemp_dump(''.join(self.cli.ip_addr()))
            search_obj.add(seq, path)

        if not search_obj.files:
            log.debug("no network info found (namespaces=%s)", namespaces)
            return []

        r = search_obj.run()
        for path in search_obj.files:
            # we no longer need this file so can delete it
            os.unlink(path)
            sections = r.find_sequence_sections(seq, path).values()
            for section in sections:
                addrs = []
                encap_info = None
                hwaddr = None
                name = None
                state = None
                for result in section:
                    # infer ns name from filename prefix
                    ns_name = None
                    source = search_obj.resolve_source_id(result.source_id)
                    ret = re.match(r'^__ns_start__(\S+)__ns__end__',
                                   os.path.basename(source))
                    if ret:
                        ns_name = ret.group(1)

                    if result.tag == seq.start_tag:
                        name = result.get(1)
                        state = result.get(2)
                    elif result.tag == seq.body_tag:
                        if result.get(1) in ['inet', 'inet6']:
                            addrs.append(result.get(2))
                        elif result.get(1) in ['vxlan']:
                            encap_info = {result.get(1): {
                                              'id': result.get(2),
                                              'local_ip': result.get(3),
                                              'dev': result.get(4)}}
                        else:
                            hwaddr = result.get(2)

                interfaces_raw.append({'name': name, 'addresses': addrs,
                                       'hwaddr': hwaddr, 'state': state,
                                       'encap_info': encap_info,
                                       'namespace': ns_name})

        self.cache_save(interfaces_raw, namespaces=namespaces)
        for iface in interfaces_raw:
            interfaces.append(NetworkPort(**iface))

        return interfaces

    @property
    def host_interfaces(self):
        if self._host_interfaces is not None:
            return self._host_interfaces

        self._host_interfaces = self._get_interfaces()
        return self._host_interfaces

    @property
    def host_ns_interfaces(self):
        if self._host_ns_interfaces is not None:
            return self._host_ns_interfaces

        self._host_ns_interfaces = self._get_interfaces(namespaces=True)
        return self._host_ns_interfaces

    @property
    def host_interfaces_all(self):
        return self.host_interfaces + self.host_ns_interfaces

    def get_interface_with_hwaddr(self, hwaddr):
        """ Returns first found. """
        for iface in self.host_interfaces_all:
            if iface.hwaddr == hwaddr:
                return iface

    def get_interface_with_addr(self, addr):
        for iface in self.host_interfaces_all:
            for _addr in iface.addresses:
                if _addr.startswith(addr):
                    return iface

    def get_interface_with_name(self, name):
        for iface in self.host_interfaces_all:
            if iface.name == name:
                return iface

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
