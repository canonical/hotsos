import re

from hotsos.core.log import log
from hotsos.core.issues import IssuesManager, OpenvSwitchWarning
from hotsos.core.plugins.openvswitch import OpenvSwitchBase, OVSDB
from hotsos.core.plugins.openvswitch.common import (
    OpenvSwitchEventHandlerBase,
    OpenvSwitchEventCallbackBase,
)
from hotsos.core.utils import sorted_dict


class OVSEventCallbackVSwitchd(OpenvSwitchEventCallbackBase):
    event_group = 'ovs'
    event_names = ['bridge-no-such-device', 'netdev-linux-no-such-device']

    def __call__(self, event):
        ret = self.categorise_events(event, max_results_per_date=5)
        if ret:
            return {event.name: ret}, 'ovs-vswitchd'


class OVSEventCallbackLogs(OpenvSwitchEventCallbackBase):
    event_group = 'ovs'
    event_names = ['ovsdb-server', 'ovs-vswitchd',
                   'receive-tunnel-port-not-found',
                   'rx-packet-on-unassociated-datapath-port',
                   'dpif-netlink-lost-packet-on-handler',
                   'assertion-failures',
                   'unreasonably-long-poll-interval']

    def __call__(self, event):
        key_by_date = True
        if event.name in ['ovs-vswitchd', 'ovsdb-server']:
            key_by_date = False

        ret = self.categorise_events(event, key_by_date=key_by_date,
                                     squash_if_none_keys=True)
        if ret:
            return {event.name: ret}, event.section


class OVSEventCallbackDALR(OpenvSwitchEventCallbackBase):
    event_group = 'ovs'
    event_names = ['deferred-action-limit-reached']

    def __call__(self, event):
        results = [{'date': "{} {}".format(r.get(1), r.get(2)),
                    'time': r.get(3),
                    'key': r.get(4)} for r in event.results]
        ret = self.categorise_events(event, results=results, key_by_date=False)
        if ret:
            return {event.name: ret}, event.section


class OVSEventCallbackPortStats(OpenvSwitchEventCallbackBase):
    event_group = 'ovs'
    event_names = ['port-stats']

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
        """
        stats = {}
        all_dropped = []  # interfaces where all packets are dropped
        all_errors = []  # interfaces where all packets are errors
        ovs = OpenvSwitchBase()
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
                        dropped_pcent = int((100 / packets) * dropped)
                        errors_pcent = int((100 / packets) * errors)
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
                if (port in [b.name for b in ovs.bridges] or
                        re.compile(r"^(q|s)g-\S{11}$").match(port)):
                    continue

                for _, s in _stats.items():
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


class OVSEventCallbackBFD(OpenvSwitchEventCallbackBase):
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


class OVSEventCallback4(OpenvSwitchEventCallbackBase):
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

        return {event.name: aggregated}, event.section


class OVSEventChecks(OpenvSwitchEventHandlerBase):
    event_group = 'ovs'

    @property
    def summary_subkey(self):
        return 'ovs-checks'


class OVNEventCallbackLogs(OpenvSwitchEventCallbackBase):
    event_group = 'ovn'
    event_names = ['ovsdb-server-nb', 'ovsdb-server-sb', 'ovn-northd',
                   'ovn-controller', 'unreasonably-long-poll-interval',
                   'inactivity-probe', 'bridge-not-found-for-port',
                   'leadership-transfers', 'compactions']

    def __call__(self, event):
        key_by_date = True
        if event.name in ['ovsdb-server-nb', 'ovsdb-server-sb', 'ovn-northd',
                          'ovn-controller']:
            key_by_date = False

        ret = self.categorise_events(event, key_by_date=key_by_date,
                                     squash_if_none_keys=True)
        if ret:
            return {event.name: ret}, event.section


class OVNEventCallbackContextSwitches(OpenvSwitchEventCallbackBase):
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

        return {event.name: sorted_dict(aggregated)}, event.section


class OVNEventCallbackNorthdVersionMismatch(OpenvSwitchEventCallbackBase):
    event_group = 'ovn'
    event_names = ['northd-version-mismatch']

    def __call__(self, event):
        """
        If the versions in the mismatch are both from the same major release
        and ovn-match-northd-version is set to 'true' we can avoid the error
        by setting ovn-match-northd-version='false' since the mismatch is not
        a problem for minor release upgrades.
        """
        vfrom = event.results[-1].get(2)
        vto = event.results[-1].get(3)

        major_match = r'(\d+\.\d+)'
        from_major = re.match(major_match, vfrom)
        to_major = re.match(major_match, vto)
        if not all([from_major, to_major]):
            log.info("could not match versions in northd mismatch log")
        elif from_major.group(1) == to_major.group(1):
            dbkey = 'ovn-match-northd-version'
            dbval = OVSDB().external_ids.get('ovn-match-northd-version')
            if dbval and dbval.lower() == 'true':
                msg = ("ovn-controller is reporting northd version mismatch "
                       "errors and the versions it is reporting ({vfrom} and "
                       "{vto}) are from the same major release. This is "
                       "failing because you have '{dbkey}' set to "
                       "'true' in the local ovsdb which is only required if "
                       "performing a major release upgrade. You can safely do "
                       "the following to workaround the problem: 'ovs-vsctl "
                       "set Open_vSwitch . external-ids:{dbkey}=\"false\"'".
                       format(vfrom=vfrom, vto=vto, dbkey=dbkey))
                IssuesManager().add(OpenvSwitchWarning(msg))


class OVNEventChecks(OpenvSwitchEventHandlerBase):
    event_group = 'ovn'

    @property
    def summary_subkey(self):
        return 'ovn-checks'
