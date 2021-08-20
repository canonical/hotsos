from common import (
    checks,
    issue_types,
    issues_utils,
)
from common.host_helpers import HostNetworkingHelper
from common.plugins.kernel import KernelChecksBase

YAML_PRIORITY = 2


class KernelNetworkChecks(KernelChecksBase, checks.EventChecksBase):

    def __init__(self):
        super().__init__(yaml_defs_label='network-checks')

    def check_mtu_dropped_packets(self, results):
        ifaces = {}
        for r in results:
            if r.get(1) in ifaces:
                ifaces[r.get(1)] += 1
            else:
                ifaces[r.get(1)] = 1

        if ifaces:
            helper = HostNetworkingHelper()

            # only report on interfaces that currently exist
            iface_names = [iface.name for iface in helper.host_interfaces_all]
            ifaces_extant = {}
            for iface in ifaces:
                if iface in iface_names:
                    ifaces_extant[iface] = ifaces[iface]

            if ifaces_extant:
                msg = ("kernel has reported over-mtu dropped packets for ({}) "
                       "interfaces".format(len(ifaces_extant)))
                issue = issue_types.NetworkWarning(msg)
                issues_utils.add_issue(issue)

                # sort by number of occurrences
                sorted_dict = {}
                for k, v in sorted(ifaces_extant.items(), key=lambda e: e[1],
                                   reverse=True):
                    sorted_dict[k] = v

                return {"over-mtu-dropped-packets": sorted_dict}

    def check_nf_conntrack_full(self, results):
        if results:
            # TODO: consider resticting this to last 24 hours
            msg = "kernel has reported nf_conntrack_full - please check"
            issue = issue_types.NetworkWarning(msg)
            issues_utils.add_issue(issue)

    def process_results(self, results):
        """ See defs/events.yaml for definitions. """
        info = {}
        for defs in self.event_definitions.values():
            for label in defs:
                _results = results.find_by_tag(label)
                if label == "over-mtu":
                    ret = self.check_mtu_dropped_packets(_results)
                    if ret:
                        info.update(ret)
                elif label == "nf-conntrack-full":
                    ret = self.check_nf_conntrack_full(_results)
                    if ret:
                        info.update(ret)

        return info

    def __call__(self):
        self.register_search_terms()
        check_results = self.process_results(self.searchobj.search())
        if check_results:
            self._output.update(check_results)
