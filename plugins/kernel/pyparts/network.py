import os

from common import (
    constants,
    issue_types,
    issues_utils,
)
from common.host_helpers import HostNetworkingHelper
from common.searchtools import (
    FileSearcher,
    SearchDef,
)
from common.plugins.kernel import (
    KernelChecksBase,
)

YAML_PRIORITY = 2


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

            # only report on interfaces that currently exist
            host_interfaces = helper.get_host_interfaces(
                                                       include_namespaces=True)
            ifaces_extant = {}
            for iface in ifaces:
                if iface in host_interfaces:
                    ifaces_extant[iface] = ifaces[iface]

            if ifaces_extant:
                msg = ("kernel has reported over-mtu dropped packets for ({}) "
                       "interfaces".format(len(ifaces_extant)))
                issue = issue_types.NetworkWarning(msg)
                issues_utils.add_issue(issue)

            # sort by nuber of occurences
            sorted_dict = {}
            for k, v in sorted(ifaces_extant.items(), key=lambda e: e[1],
                               reverse=True):
                sorted_dict[k] = v

            self._output["over-mtu-dropped-packets"] = sorted_dict

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
