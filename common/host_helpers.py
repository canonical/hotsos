import os
import re

from common import cli_helpers
from common.utils import mktemp_dump
from common.searchtools import (
    FileSearcher,
    SearchDef,
    SequenceSearchDef,
)

# compatible with ip addr and ip link
IP_IFACE_NAME = r"^\d+:\s+(\S+):\s+.+"
IP_IFACE_NAME_TEMPLATE = r"^\d+:\s+({}):\s+.+"
IP_IFACE_V4_ADDR = r".+(inet) ([\d\.]+)/(\d+) brd \S+ scope global (\S+)"
IP_IFACE_V6_ADDR = r".+(inet6) ([\d\:]+)/(\d+) scope global.*"
IP_IFACE_HW_ADDR = r".+(link/ether) (\S+) brd .+"
IP_IFACE_HW_ADDR_TEMPLATE = r".+link/ether {} brd .+"
IP_EOF = r"^$"


class NetworkPort(object):

    def __init__(self, name, addresses, hwaddr):
        self.name = name
        self.addresses = addresses
        self.hwaddr = hwaddr
        self.cli_helper = cli_helpers.CLIHelper()
        self.f_ip_link_show = mktemp_dump(''.join(self.cli_helper.ip_link()))

    def __del__(self):
        if os.path.exists(self.f_ip_link_show):
            os.unlink(self.f_ip_link_show)

    def to_dict(self):
        return {self.name: {"addresses": self.addresses,
                            "hwaddr": self.hwaddr}}

    def stats(self):
        """ Get ip link stats for the interface. """
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
                            for key in ["packets", "dropped", "errors",
                                        "overrun"]:
                                if column == key:
                                    if rxtx not in counters:
                                        counters[rxtx] = {}

                                    counters[rxtx][key] = value
                                    continue

        return counters


class HostNetworkingHelper(object):

    def __init__(self):
        self._host_interfaces = []
        self._host_ns_interfaces = []
        self.cli = cli_helpers.CLIHelper()
        self.ip_addr_dump = mktemp_dump('\n'.join(self.cli.ip_addr()))

    def __del__(self):
        if os.path.exists(self.ip_addr_dump):
            os.unlink(self.ip_addr_dump)

    def _get_interfaces(self, ip_addr=None):
        interfaces = []
        if ip_addr:
            ip_addr_dump = mktemp_dump('\n'.join(ip_addr))
        else:
            ip_addr_dump = self.ip_addr_dump

        self.ip_addr_seq_search = SequenceSearchDef(
                start=SearchDef(IP_IFACE_NAME),
                body=SearchDef([IP_IFACE_V4_ADDR,
                                IP_IFACE_V6_ADDR,
                                IP_IFACE_HW_ADDR]),
                tag="interfaces")
        search_obj = FileSearcher()
        search_obj.add_search_term(self.ip_addr_seq_search,
                                   ip_addr_dump)
        r = search_obj.search()
        sections = r.find_sequence_sections(self.ip_addr_seq_search).values()
        for section in sections:
            addrs = []
            hwaddr = None
            name = None
            for result in section:
                if result.tag == self.ip_addr_seq_search.start_tag:
                    name = result.get(1)
                elif result.tag == self.ip_addr_seq_search.body_tag:
                    if result.get(1) in ['inet', 'inet6']:
                        addrs.append(result.get(2))
                    else:
                        hwaddr = result.get(2)

            interfaces.append(NetworkPort(name, addrs, hwaddr))

        return interfaces

    @property
    def host_interfaces(self):
        if self._host_interfaces:
            return self._host_interfaces

        self._host_interfaces = self._get_interfaces()
        return self._host_interfaces

    @property
    def host_ns_interfaces(self):
        if self._host_ns_interfaces:
            return self._host_ns_interfaces

        for ns in self.cli.ip_netns():
            ns_name = ns.partition(" ")[0]
            ns_ip_addr = self.cli.ns_ip_addr(namespace=ns_name)
            self._host_ns_interfaces += self._get_interfaces(ns_ip_addr)

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
