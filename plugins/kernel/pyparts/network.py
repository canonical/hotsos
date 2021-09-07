from core.issues import (
    issue_types,
    issue_utils,
)
from core.checks import CallbackHelper
from core.cli_helpers import CLIHelper
from core.host_helpers import HostNetworkingHelper
from core.plugins.kernel import KernelEventChecksBase

YAML_PRIORITY = 2
EVENTCALLBACKS = CallbackHelper()


class KernelNetworkChecks(KernelEventChecksBase):

    def __init__(self):
        super().__init__(yaml_defs_group='network-checks',
                         callback_helper=EVENTCALLBACKS)
        self.cli_helper = CLIHelper()
        self.hostnet_helper = HostNetworkingHelper()

    @EVENTCALLBACKS.callback
    def over_mtu_dropped_packets(self, event):
        results = event['results']
        if not results:
            return

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
            # strip trailing newline chars
            ovs_bridges = [br.strip() for br in ovs_bridges]

            interfaces_extant = {}
            for iface in interfaces:
                if iface in host_interfaces:
                    if iface not in ovs_bridges:
                        interfaces_extant[iface] = interfaces[iface]

            if interfaces_extant:
                msg = ("kernel has reported over-mtu dropped packets for ({}) "
                       "interfaces".format(len(interfaces_extant)))
                issue = issue_types.NetworkWarning(msg)
                issue_utils.add_issue(issue)

                # sort by number of occurrences
                sorted_dict = {}
                for k, v in sorted(interfaces_extant.items(),
                                   key=lambda e: e[1], reverse=True):
                    sorted_dict[k] = v

                return sorted_dict

    @EVENTCALLBACKS.callback
    def nf_conntrack_full(self, event):
        results = event['results']
        if not results:
            return

        # TODO: consider resticting this to last 24 hours
        msg = "kernel has reported nf_conntrack_full - please check"
        issue = issue_types.NetworkWarning(msg)
        issue_utils.add_issue(issue)
