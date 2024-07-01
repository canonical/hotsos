from hotsos.core.log import log
from hotsos.core.plugins.kernel.kernlog.common import KernLogBase
from hotsos.core.search import SearchDef


class OverMTUDroppedPacketEvent():

    @property
    def searchdef(self):
        return SearchDef(r'.+\] (\S+): dropped over-mtu packet',
                         hint='dropped', tag='over-mtu-dropped')


class KernLogEvents(KernLogBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for event in [OverMTUDroppedPacketEvent()]:
            self.searcher.add(event.searchdef, self.path)

        self.results = self.searcher.run()

    @property
    def over_mtu_dropped_packets(self):
        """
        Return a tally of interfaces that have reports of over-mtu dropped
        packets in kern.log.

        Interfaces are only included in the result if they meet the following
        requirements:

          1. they are not an OpenvSwitch bridge
          2. they exist on the localhost and are not namespaced

        @return: dict of interfaces and an integer count of associated dropped
                 packet messages.
        """
        interfaces = {}
        for r in self.results.find_by_tag('over-mtu-dropped'):
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
            for name, drops in interfaces.items():
                if name in host_interfaces:
                    if name not in ovs_bridges:
                        interfaces_extant[name] = drops
                    else:
                        log.debug("excluding ovs bridge %s", name)

            if interfaces_extant:
                # sort by number of occurrences
                sorted_dict = {}
                for k, v in sorted(interfaces_extant.items(),
                                   key=lambda e: e[1], reverse=True):
                    sorted_dict[k] = v

                return sorted_dict

        return {}
