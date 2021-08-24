from common import (
    checks,
    issue_types,
    issues_utils,
)
from common.cli_helpers import CLIHelper
from common.host_helpers import HostNetworkingHelper
from common.plugins.kernel import KernelChecksBase

YAML_PRIORITY = 2


class KernelNetworkChecks(KernelChecksBase, checks.EventChecksBase):

    def __init__(self):
        super().__init__(yaml_defs_group='network-checks')
        self.cli_helper = CLIHelper()
        self.hostnet_helper = HostNetworkingHelper()

    def check_mtu_dropped_packets(self, results):
        interfaces = {}
        for r in results:
            if r.get(1) in interfaces:
                interfaces[r.get(1)] += 1
            else:
                interfaces[r.get(1)] = 1

        if interfaces:
            # only report on interfaces that currently exist
            host_interfaces = [iface.name for iface in
                               self.hostnet_helper.host_interfaces_all]
            # filter out interfaces that are actually ovs bridge aliases
            ovs_bridges = self.cli_helper.ovs_vsctl_list_br()

            interfaces_extant = {}
            for iface in interfaces:
                if iface in host_interfaces:
                    if iface not in ovs_bridges:
                        interfaces_extant[iface] = interfaces[iface]

            if interfaces_extant:
                msg = ("kernel has reported over-mtu dropped packets for ({}) "
                       "interfaces".format(len(interfaces_extant)))
                issue = issue_types.NetworkWarning(msg)
                issues_utils.add_issue(issue)

                # sort by number of occurrences
                sorted_dict = {}
                for k, v in sorted(interfaces_extant.items(),
                                   key=lambda e: e[1], reverse=True):
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
        for section in self.event_definitions.values():
            for event in section:
                _results = results.find_by_tag(event)
                if event == "over-mtu":
                    ret = self.check_mtu_dropped_packets(_results)
                    if ret:
                        info.update(ret)
                elif event == "nf-conntrack-full":
                    ret = self.check_nf_conntrack_full(_results)
                    if ret:
                        info.update(ret)

        return info

    def __call__(self):
        self.register_search_terms()
        check_results = self.process_results(self.searchobj.search())
        if check_results:
            self._output.update(check_results)
