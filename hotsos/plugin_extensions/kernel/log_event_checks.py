from hotsos.core.issues import IssuesManager, NetworkWarning
from hotsos.core.ycheck import CallbackHelper
from hotsos.core.cli_helpers import CLIHelper
from hotsos.core.host_helpers import HostNetworkingHelper
from hotsos.core.plugins.kernel import KernelEventChecksBase
from hotsos.core.searchtools import FileSearcher

EVENTCALLBACKS = CallbackHelper()


class KernelLogEventChecks(KernelEventChecksBase):

    def __init__(self):
        super().__init__(yaml_defs_group='kernlog',
                         searchobj=FileSearcher(),
                         callback_helper=EVENTCALLBACKS)
        self.cli_helper = CLIHelper()
        self.hostnet_helper = HostNetworkingHelper()

    @EVENTCALLBACKS.callback()
    def over_mtu_dropped_packets(self, event):
        interfaces = {}
        for r in event.results:
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
                       "interfaces.".format(len(interfaces_extant)))
                issue = NetworkWarning(msg)
                IssuesManager().add(issue)

                # sort by number of occurrences
                sorted_dict = {}
                for k, v in sorted(interfaces_extant.items(),
                                   key=lambda e: e[1], reverse=True):
                    sorted_dict[k] = v

                return sorted_dict
