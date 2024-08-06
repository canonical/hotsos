import re
from functools import cached_property

from hotsos.core.issues import IssuesManager, OpenvSwitchWarning
from hotsos.core.plugins.openvswitch import OpenvSwitchBase
from hotsos.core.plugins.openvswitch.common import (
    OpenvSwitchEventHandlerBase,
    OpenvSwitchEventCallbackBase,
)
from hotsos.core.utils import sorted_dict


class OVSEventCallbackVSwitchd(OpenvSwitchEventCallbackBase):
    """ Events callback for OVS vswitchd events """
    event_group = 'ovs'
    event_names = ['bridge-no-such-device', 'netdev-linux-no-such-device']

    def __call__(self, event):
        ret = self.categorise_events(
            event,
            options=self.EventProcessingOptions(max_results_per_date=5)
        )
        if ret:
            return {event.name: ret}, 'ovs-vswitchd'

        return None


class OVSEventCallbackLogs(OpenvSwitchEventCallbackBase):
    """ Events callback for OVS log events """
    event_group = 'ovs'
    event_names = ['ovsdb-server', 'ovs-vswitchd',
                   'receive-tunnel-port-not-found',
                   'rx-packet-on-unassociated-datapath-port',
                   'dpif-netlink-lost-packet-on-handler',
                   'assertion-failures',
                   'unreasonably-long-poll-interval']

    def __call__(self, event):
        options = self.EventProcessingOptions(squash_if_none_keys=True)

        if event.name in ['ovs-vswitchd', 'ovsdb-server']:
            options.key_by_date = False

        ret = self.categorise_events(event, options=options)
        if ret:
            return {event.name: ret}, event.section_name

        return None


class OVSEventCallbackDALR(OpenvSwitchEventCallbackBase):
    """ Events callback for OVS dalr events """
    event_group = 'ovs'
    event_names = ['deferred-action-limit-reached']

    def __call__(self, event):
        # pylint: disable=duplicate-code
        results = [{'date': f"{r.get(1)} {r.get(2)}",
                    'time': r.get(3),
                    'key': r.get(4)} for r in event.results]
        ret = self.categorise_events(
            event,
            results=results,
            options=self.EventProcessingOptions(key_by_date=False)
        )
        if ret:
            return {event.name: ret}, event.section_name

        return None


class OVSEventCallbackPortStats(OpenvSwitchEventCallbackBase):
    """ Events callback for OVS portstat events """
    event_group = 'ovs'
    event_names = ['port-stats']

    @cached_property
    def ovs(self):
        return OpenvSwitchBase()

    def _get_port_stats(self, section, sequence_def):
        """
        Extract stats info from port section.

        @param section: searchkit.SearchResult object that is part of a
                        sequence section and is expected to have a tag matching
                        the start or body of a section.
        @param sequence_def: the searchkit.SequenceSearchDef object used to
                             define the search used for this event. This object
                             contains a unique id that is used to identify
                             results.
        @return: if successful returns a tuple of (portname, stats) where stats
                 is a dictionary of key network statistics info about the port.
        """
        port = None
        stats = {}
        for result in section:
            if result.tag == sequence_def.start_tag:
                port = result.get(1)
                continue

            if result.tag != sequence_def.body_tag:
                continue

            key = result.get(1)  # this is rx/tx
            packets = int(result.get(2))
            errors = int(result.get(3))
            dropped = int(result.get(4))

            log_stats = errors or dropped
            if packets:
                dropped_pcent = int((100 / packets) * dropped)
                errors_pcent = int((100 / packets) * errors)
                if max([dropped_pcent, errors_pcent]) <= 1:
                    log_stats = False

            if log_stats:
                stats[key] = {"packets": packets}
                if errors:
                    stats[key]["errors"] = errors
                if dropped:
                    stats[key]["dropped"] = dropped

        if not (port and stats):
            return None, None

        # Ports to ignore - see docstring for info
        if (port in [b.name for b in self.ovs.bridges] or
                re.compile(r"^(q|s)g-\S{11}$").match(port)):
            return None, None

        return port, stats

    def __call__(self, event):
        """
        Report on interfaces that are showing packet drops or errors.

        Sometimes it is normal for an interface to have packet drops and if
        we think that is the case we ignore but otherwise we raise an issue
        to alert.

        Interfaces we currently ignore:

        OVS bridges.

        Neutron HA gateway ports:
        In Openstack for example when using Neutron HA routers, vrrp peers
        that are in BACKUP state may still receive packets on their external
        interface but these will be dropped since they have no where to go. In
        this case it is possible to have 100% packet drops on the interface
        if that VR has never been a vrrp MASTER. For this scenario we filter
        interfaces whose name matches e.g. qg-3ca935f4-07.

        @param event: EventCheckResult object
        """
        port_stats = {}
        global_stats = {'all_dropped': [],  # all interfaces with 100% dropped
                        'all_errors': []}  # all interfaces with 100% errors
        for section in event.results:
            port, _stats = self._get_port_stats(section, event.sequence_def)
            if not _stats:
                continue

            for key in ['dropped', 'errors']:
                for _, s in _stats.items():
                    if s.get(key) and not s['packets']:
                        global_stats['all_' + key].append(port)

            port_stats[port] = _stats

        if not port_stats:
            return None

        ports = global_stats['all_' + 'dropped']
        if ports:
            msg = (f"found {len(ports)} ovs interfaces with 100% "
                   "dropped packets.")
            IssuesManager().add(OpenvSwitchWarning(msg))

        ports = global_stats['all_' + 'errors']
        if ports:
            msg = (f"found {len(ports)} ovs interfaces with 100% "
                   "packet errors.")
            IssuesManager().add(OpenvSwitchWarning(msg))

        stats_sorted = {}
        for k in sorted(port_stats):
            stats_sorted[k] = port_stats[k]

        output_key = f"{event.section_name}-port-stats"
        return stats_sorted, output_key


class OVSEventCallbackBFD(OpenvSwitchEventCallbackBase):
    """ Events callback for OVS BFD events """
    event_group = 'ovs'
    event_names = ['bfd-state-changes']

    def __call__(self, event):
        state_changes = {}
        for r in event.results:
            date = r.get(1)
            port = r.get(2)
            statechange = r.get(3)

            if date not in state_changes:
                state_changes[date] = {}

            if port not in state_changes[date]:
                state_changes[date][port] = []

            state_changes[date][port].append(statechange)

        stats = {}
        if state_changes:
            stats['all-ports-day-avg'] = {}
            stats['per-port-day-total'] = {}
            for date, ports in state_changes.items():
                port_sum = 0
                if date not in stats['per-port-day-total']:
                    stats['per-port-day-total'][date] = {}

                port_totals = {}
                for port, state_changes in ports.items():
                    num_changes = len(state_changes)
                    port_totals[port] = num_changes
                    port_sum += num_changes

                # sort by value
                port_totals = sorted_dict(port_totals, key=lambda e: e[1],
                                          reverse=True)
                stats['per-port-day-total'][date] = port_totals
                day_avg = int(port_sum / len(ports))
                stats['all-ports-day-avg'][date] = day_avg

        stats['all-ports-day-avg'] = sorted_dict(stats['all-ports-day-avg'])
        if stats:
            return {'bfd': {'state-change-stats': stats}}, 'ovs-vswitchd'

        return None


class OVSEventCallbackInvoluntaryContextSwitches(OpenvSwitchEventCallbackBase):
    """ Events callback for OVS involuntary context switch events """
    event_group = 'ovs'
    event_names = ['involuntary-context-switches']

    def __call__(self, event):
        aggregated = {}
        for r in event.results:
            key = r.get(1)
            hour = r.get(2)
            count = int(r.get(3))
            if key not in aggregated:
                aggregated[key] = {}

            if hour in aggregated[key]:
                aggregated[key][hour] += count
            else:
                aggregated[key][hour] = count

        for key, value in aggregated.items():
            aggregated[key] = sorted_dict(value)

        return {event.name: aggregated}, event.section_name


class OVSEventChecks(OpenvSwitchEventHandlerBase):
    """ Events handler for OVS events """
    event_group = 'ovs'
    summary_part_index = 1

    @property
    def summary_subkey(self):
        return 'ovs-checks'


class OVNEventCallbackLogs(OpenvSwitchEventCallbackBase):
    """ Events callback for OVS log events """
    event_group = 'ovn'
    event_names = ['ovsdb-server-nb', 'ovsdb-server-sb', 'ovn-northd',
                   'ovn-controller', 'unreasonably-long-poll-interval',
                   'inactivity-probe', 'bridge-not-found-for-port',
                   'leadership-transfers', 'compactions',
                   'leadership-acquired']

    def __call__(self, event):
        options = self.EventProcessingOptions(squash_if_none_keys=True)

        if event.name in ['ovsdb-server-nb', 'ovsdb-server-sb', 'ovn-northd',
                          'ovn-controller']:
            options.key_by_date = False

        ret = self.categorise_events(event, options=options)
        if ret:
            return {event.name: ret}, event.section_name

        return None


class OVNEventCallbackContextSwitches(OpenvSwitchEventCallbackBase):
    """ Events callback for OVN involuntary context switch events """
    event_group = 'ovn'
    event_names = ['involuntary-context-switches']

    def __call__(self, event):
        aggregated = {}
        for r in event.results:
            key = r.get(1)
            hour = r.get(2)
            count = int(r.get(3))
            if key not in aggregated:
                aggregated[key] = {}

            if hour in aggregated[key]:
                aggregated[key][hour] += count
            else:
                aggregated[key][hour] = count

        for key, value in aggregated.items():
            aggregated[key] = sorted_dict(value)

        return {event.name: sorted_dict(aggregated)}, event.section_name


class OVNEventChecks(OpenvSwitchEventHandlerBase):
    """ Events handler for OVN events """
    event_group = 'ovn'
    summary_part_index = 2

    @property
    def summary_subkey(self):
        return 'ovn-checks'
