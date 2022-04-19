import re

from hotsos.core.ycheck import CallbackHelper
from hotsos.core.searchtools import FileSearcher
from hotsos.core.issues import IssuesManager, OpenvSwitchWarning
from hotsos.core.plugins.openvswitch import (
    OpenvSwitchEventChecksBase,
)

EVENTCALLBACKS = CallbackHelper()


class OVSEventChecks(OpenvSwitchEventChecksBase):

    def __init__(self):
        super().__init__(yaml_defs_group='ovs',
                         searchobj=FileSearcher(),
                         callback_helper=EVENTCALLBACKS)

    @property
    def summary_subkey(self):
        return 'ovs-checks'

    @EVENTCALLBACKS.callback('bridge-no-such-device',
                             'netdev-linux-no-such-device')
    def process_vswitchd_events(self, event):
        ret = self.get_results_stats(event.results)
        if ret:
            return {event.name: ret}, 'ovs-vswitchd'

    @EVENTCALLBACKS.callback('ovsdb-server', 'ovs-vswitchd',
                             'receive-tunnel-port-not-found',
                             'rx-packet-on-unassociated-datapath-port',
                             'dpif-netlink-lost-packet-on-handler',
                             'unreasonably-long-poll-interval')
    def process_log_events(self, event):
        key_by_date = True
        if event.name in ['ovs-vswitchd', 'ovsdb-server']:
            key_by_date = False

        ret = self.get_results_stats(event.results, key_by_date=key_by_date)
        if ret:
            ret = {event.name: ret}
            return ret, event.section

    @EVENTCALLBACKS.callback()
    def deferred_action_limit_reached(self, event):
        ret = self.get_results_stats(event.results, key_by_date=False)
        output_key = "{}-{}".format(event.section, event.name)
        return ret, output_key

    @EVENTCALLBACKS.callback()
    def port_stats(self, event):
        """
        Report on interfaces that are showing packet drops or errors.

        Sometimes it is normal for an interface to have packet drops and if
        we think that is the case we ignore but otherwise we raise an issue
        to alert.

        Interfaces we currently ignore:

        OVS bridges.

        In Openstack for example when using Neutron HA routers, vrrp peers
        that are in BACKUP state may still receive packets on their external
        interface but these will be dropped since they have no where to go. In
        this case it is possible to have 100% packet drops on the interface
        if that VR has never been a vrrp MASTER. For this scenario we filter
        interfaces whose name matches e.g. qg-3ca935f4-07.
        """
        stats = {}
        all_dropped = []  # interfaces where all packets are dropped
        all_errors = []  # interfaces where all packets are errors
        for section in event.results:
            port = None
            _stats = {}
            for result in section:
                if result.tag == event.sequence_def.start_tag:
                    port = result.get(1)
                elif result.tag == event.sequence_def.body_tag:
                    key = result.get(1)
                    packets = int(result.get(2))
                    errors = int(result.get(3))
                    dropped = int(result.get(4))

                    log_stats = False
                    if packets:
                        dropped_pcent = int((100/packets) * dropped)
                        errors_pcent = int((100/packets) * errors)
                        if dropped_pcent > 1 or errors_pcent > 1:
                            log_stats = True
                    elif errors or dropped:
                        log_stats = True

                    if log_stats:
                        _stats[key] = {"packets": packets}
                        if errors:
                            _stats[key]["errors"] = errors
                        if dropped:
                            _stats[key]["dropped"] = dropped

            if port and _stats:
                # Ports to ignore - see docstring for info
                if (port in [b.name for b in self.bridges] or
                        re.compile(r"^(q|s)g-\S{11}$").match(port)):
                    continue

                for key in _stats:
                    s = _stats[key]
                    if s.get('dropped') and not s['packets']:
                        all_dropped.append(port)

                    if s.get('errors') and not s['packets']:
                        all_errors.append(port)

                stats[port] = _stats

        if stats:
            if all_dropped:
                msg = ("found {} ovs interfaces with 100% dropped packets."
                       .format(len(all_dropped)))
                IssuesManager().add(OpenvSwitchWarning(msg))

            if all_errors:
                msg = ("found {} ovs interfaces with 100% packet errors."
                       .format(len(all_errors)))
                IssuesManager().add(OpenvSwitchWarning(msg))

            stats_sorted = {}
            for k in sorted(stats):
                stats_sorted[k] = stats[k]

            output_key = "{}-port-stats".format(event.section)
            return stats_sorted, output_key


class OVNEventChecks(OpenvSwitchEventChecksBase):

    def __init__(self):
        super().__init__(yaml_defs_group='ovn',
                         searchobj=FileSearcher(),
                         callback_helper=EVENTCALLBACKS)

    @property
    def summary_subkey(self):
        return 'ovn-checks'

    @EVENTCALLBACKS.callback('ovsdb-server-nb', 'ovsdb-server-sb',
                             'ovn-northd', 'ovn-controller',
                             'unreasonably-long-poll-interval',
                             'inactivity-probe', 'bridge-not-found-for-port')
    def process_log_events(self, event):
        key_by_date = True
        if event.name in ['ovsdb-server-nb', 'ovsdb-server-sb', 'ovn-northd',
                          'ovn-controller']:
            key_by_date = False

        ret = self.get_results_stats(event.results, key_by_date=key_by_date)
        if ret:
            ret = {event.name: ret}
            return ret, event.section
