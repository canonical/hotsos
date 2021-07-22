from common import (
    checks,
    issue_types,
    issues_utils,
)
from common.host_helpers import HostNetworkingHelper
from common.searchtools import FileSearcher
from common.plugins.kernel import (
    KernelChecksBase,
)

YAML_PRIORITY = 2


class KernLogEventChecks(checks.EventChecksBase):

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


class KernelNetworkChecks(KernelChecksBase):

    def __call__(self):
        s = FileSearcher()
        check = KernLogEventChecks(s, "network-checks")
        check.register_search_terms()
        results = s.search()
        check_results = check.process_results(results)
        if check_results:
            self._output.update(check_results)
