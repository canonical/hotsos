import os

from common import cli_helpers
from common.utils import mktemp_dump
from common.searchtools import (
    FileSearcher,
    SearchDef,
    SequenceSearchDef,
)

IP_ADDR_IFACE_NAME = r"^[0-9]+:\s+(\S+):\s+.+"
IP_ADDR_IFACE_V4_ADDR = (r".+inet ([\d\.]+)/(\d+) brd [\d\.]+ scope global "
                         r"(\S+)")
IP_ADDR_IFACE_V6_ADDR = (r".+inet ([\d\:]+)/(\d+) scope global.*")


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
                start=SearchDef(IP_ADDR_IFACE_NAME),
                body=SearchDef([IP_ADDR_IFACE_V4_ADDR,
                                IP_ADDR_IFACE_V6_ADDR]),
                tag="interfaces")
        search_obj = FileSearcher()
        search_obj.add_search_term(self.ip_addr_seq_search,
                                   ip_addr_dump)
        r = search_obj.search()
        sections = r.find_sequence_sections(self.ip_addr_seq_search).values()
        for section in sections:
            addrs = []
            name = None
            for result in section:
                if result.tag == self.ip_addr_seq_search.start_tag:
                    name = result.get(1)
                elif result.tag == self.ip_addr_seq_search.body_tag:
                    addrs.append(result.get(1))

            interfaces.append({"name": name, "addresses": addrs})

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

    def get_interface_with_addr(self, addr):
        for iface in self.host_interfaces_all:
            for _addr in iface.get('addresses', []):
                if _addr.startswith(addr):
                    return iface

    def host_interface_exists(self, name, check_namespaces=True):
        names = [_iface["name"] for _iface in self.host_interfaces]
        if name in names:
            return True

        if not check_namespaces:
            return False

        names = [_iface["name"] for _iface in self.host_ns_interfaces]
        if name in names:
            return True

        return False
