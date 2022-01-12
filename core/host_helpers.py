import os
import re

from core import cli_helpers
from core.utils import mktemp_dump
from core.searchtools import (
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


class NetworkPort(object):

    def __init__(self, name, addresses, hwaddr, state, encap_info):
        self.name = name
        self.addresses = addresses
        self.hwaddr = hwaddr
        self.state = state
        self.encap_info = encap_info
        self.cli_helper = cli_helpers.CLIHelper()
        self.f_ip_link_show = mktemp_dump(''.join(self.cli_helper.ip_link()))
        self._counters = None

    def __del__(self):
        if os.path.exists(self.f_ip_link_show):
            os.unlink(self.f_ip_link_show)

    def to_dict(self):
        return {self.name: {'addresses': self.addresses,
                            'hwaddr': self.hwaddr,
                            'state': self.state,
                            'speed': self.speed}}

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
        if self._counters is not None:
            return self._counters

        """ Get ip link info for the interface. """
        s = FileSearcher()
        seqdef = SequenceSearchDef(
                    # match start of interface
                    start=SearchDef(IP_IFACE_NAME_TEMPLATE.format(self.name)),
                    # match body of interface
                    body=SearchDef(r".+"),
                    # match next interface or EOF
                    end=SearchDef([IP_IFACE_NAME, IP_EOF]),
                    tag="ifaces")
        s.add_search_term(seqdef, path=self.f_ip_link_show)
        results = s.search()
        stats_raw = []
        for section in results.find_sequence_sections(seqdef).values():
            for result in section:
                if result.tag == seqdef.body_tag:
                    stats_raw.append(result.get(0))

        # NOTE: we only expect one match
        counters = {}
        if stats_raw:
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
            self._counters = counters

        return self._counters or {}


class HostNetworkingHelper(object):

    def __init__(self):
        self._host_interfaces = None
        self._host_ns_interfaces = None
        self.cli = cli_helpers.CLIHelper()
        self.ip_addr_dump = mktemp_dump('\n'.join(self.cli.ip_addr()))

    def __del__(self):
        if os.path.exists(self.ip_addr_dump):
            os.unlink(self.ip_addr_dump)

    def _get_interfaces(self, namespaces=False):
        """
        Get all interfaces in ip address show.

        @param namespaces: if set to True will get interfaces from all
        namespaces on the host.
        @return: list of NetworkPort objects for each interface found.
        """
        paths = []
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
                path = mktemp_dump('\n'.join(ip_addr))
                search_obj.add_search_term(seq, path)
                paths.append(path)
        else:
            paths = [self.ip_addr_dump]
            search_obj.add_search_term(seq, self.ip_addr_dump)

        r = search_obj.search()
        interfaces = []
        for path in paths:
            sections = r.find_sequence_sections(seq, path).values()
            for section in sections:
                addrs = []
                encap_info = None
                hwaddr = None
                name = None
                state = None
                for result in section:
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

                interfaces.append(NetworkPort(name, addrs, hwaddr, state,
                                              encap_info))

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
