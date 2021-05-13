#!/usr/bin/python3
import os

from common import (
    constants,
    issue_types,
    issues_utils,
    plugin_yaml,
)
from common.host_helpers import HostNetworkingHelper
from common.searchtools import (
    FileSearcher,
    SearchDef,
)
from kernel_common import (
    KernelChecksBase,
)

KERNEL_INFO = {}


class KernelNetworkChecks(KernelChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.search_obj = None

    def check_mtu_dropped_packets(self):
        ifaces = {}
        for r in self.results.find_by_tag("over-mtu"):
            if r.get(1) in ifaces:
                ifaces[r.get(1)] += 1
            else:
                ifaces[r.get(1)] = 1

        if ifaces:
            helper = HostNetworkingHelper()
            # only report the issue if the interfaces actually exist
            raise_issue = False
            host_interfaces = helper.get_host_interfaces(
                                                       include_namespaces=True)

            ifaces_extant = []
            for iface in ifaces:
                if iface in host_interfaces:
                    raise_issue = True
                    ifaces_extant.append(iface)

            if raise_issue:
                msg = ("kernel has reported over-mtu dropped packets for ({}) "
                       "interfaces".format(len(ifaces_extant)))
                issue = issue_types.NetworkWarning(msg)
                issues_utils.add_issue(issue)

            # sort by nuber of occurences
            sorted_dict = {}
            for k, v in sorted(ifaces.items(), key=lambda e: e[1],
                               reverse=True):
                sorted_dict[k] = v

            KERNEL_INFO["over-mtu-dropped-packets"] = sorted_dict

    def register_mtu_dropped_packets_search(self):
        path = os.path.join(constants.DATA_ROOT, 'var/log/kern.log')
        if constants.USE_ALL_LOGS:
            path = path + "*"

        sdef = SearchDef(r".+\] (\S+): dropped over-mtu packet",
                         hint="dropped", tag="over-mtu")
        self.search_obj.add_search_term(sdef, path)

    def __call__(self):
        self.search_obj = FileSearcher()
        self.register_mtu_dropped_packets_search()
        self.results = self.search_obj.search()
        self.check_mtu_dropped_packets()


def get_kernal_network_checks():
    return KernelNetworkChecks()


if __name__ == "__main__":
    get_kernal_network_checks()()
    if KERNEL_INFO:
        plugin_yaml.save_part(KERNEL_INFO, priority=2)
