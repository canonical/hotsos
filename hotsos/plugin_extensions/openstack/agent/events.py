import datetime

import yaml
from hotsos.core.analytics import (
    LogEventStats,
    SearchResultIndices
)
from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import CLIHelper
from hotsos.core.issues import (
    IssueContext,
    IssuesManager,
    NeutronL3HAWarning,
    OpenstackWarning
)
from hotsos.core.log import log
from hotsos.core.plugins.openstack.common import (
    OpenstackEventHandlerBase,
    OpenstackEventCallbackBase,
)
from hotsos.core.plugins.openstack.neutron import NeutronHAInfo
from hotsos.core import utils
from hotsos.core.utils import sorted_dict
from hotsos.core.plugintools import (
    summary_entry,
    get_min_available_entry_index,
)

VRRP_TRANSITION_WARN_THRESHOLD = 8


class ApacheEventCallback(OpenstackEventCallbackBase):
    """ Implements Apache events callback. """
    event_group = 'apache'
    event_names = ['connection-refused']

    @staticmethod
    def _get_context_and_results(event):
        context = {}
        results = []
        for result in event.results:
            # save some context info
            path = event.searcher.resolve_source_id(result.source_id)
            if path in context:
                context[path].append(result.linenumber)
            else:
                context[path] = [result.linenumber]

            month = datetime.datetime.strptime(result.get(1), '%b').month
            day = result.get(2)
            year = result.get(3)
            addr = result.get(4)
            port = result.get(5)
            results.append({'date': f"{year}-{month}-{day}",
                            'key': f"{addr}:{port}"})

        return context, results

    def __call__(self, event):
        ports_max = {}

        context, results = self._get_context_and_results(event)

        conns_refused = self.categorise_events(event, results=results)
        for addrs in conns_refused.values():
            for addr, count in addrs.items():
                port = addr.partition(':')[2]
                # allow a small number of connection refused errors on a given
                # day
                if count < 5:
                    continue

                if port not in ports_max:
                    ports_max[port] = count
                else:
                    ports_max[port] = max(count, ports_max[port])

        if ports_max:
            msg = ('apache is reporting connection refused errors for the '
                   'following ports which could mean some services are not '
                   f"working properly - {','.join(ports_max.keys())} - please "
                   'check.')
            IssuesManager().add(OpenstackWarning(msg), IssueContext(**context))

        return sorted_dict(conns_refused)


class ApacheEventChecks(OpenstackEventHandlerBase):
    """ Implements Apache events handler. """
    summary_part_index = 8
    event_group = 'apache'

    @summary_entry('agent-checks', get_min_available_entry_index() + 101)
    def summary_agent_checks(self):
        out = self.run()
        if out:
            return {self.event_group: out}

        return None


class APIEventsCallback(OpenstackEventCallbackBase):
    """ Implements OpenStack REST API events callback. """
    event_group = 'http-requests'
    event_names = ['neutron', 'nova']

    def __call__(self, event):
        results = [{'date': r.get(1),
                    'key': r.get(2)} for r in event.results]
        ret = self.categorise_events(event, results=results)
        if ret:
            if event.name == 'nova':
                newdict = {}
                for key, value in ret.items():
                    d = datetime.datetime.strptime(key, '%d/%b/%Y')
                    newdict[d.strftime("%Y-%m-%d")] = value

                ret = newdict

            return ret

        return None


class APIEvents(OpenstackEventHandlerBase):
    """ Implements Nova API events handler. """
    summary_part_index = 9
    event_group = 'http-requests'

    @summary_entry('api-info', get_min_available_entry_index() + 100)
    def summary_api_info(self):
        out = self.run()
        if out:
            return {self.event_group: out}

        return None


class AgentEventsCallback(OpenstackEventCallbackBase):
    """ Implements agent events callback. """
    event_group = 'neutron.agents'
    ovsdbapp_event_names = ['ovsdbapp-nb-leader-reconnect',
                            'ovsdbapp-sb-leader-reconnect']
    ovn_mech_driver_events = ['ovn-resource-revision-bump',
                              'ovsdb-monitor-router-binding-transitions',
                              'ovsdb-transaction-aborted']
    event_names = ['rpc-loop', 'router-spawn-events', 'router-updates']
    event_names += ovsdbapp_event_names + ovn_mech_driver_events

    @staticmethod
    def _get_event_stats(results, tag_prefix, custom_idxs=None):
        stats = LogEventStats(results, tag_prefix, custom_idxs=custom_idxs)
        stats.run()
        top5 = stats.get_top_n_events_sorted(5)
        if not top5:
            return None

        return {"top": top5,
                "stats": stats.get_event_stats()}

    def _ovsdb_monitor_router_binding_transitions_event(self, event):
        """
        The ovsdbmonitor will print bindings which will eventually
        reflect transitions so we need to filter out contiguous bindings
        to the same chassis so that we are just left with transitions
        that we can then count.

        :param event: EventCheckResult
        """
        agent = event.section_name
        results = []
        for r in event.results:
            results.append({'date': r.get(1), 'time': r.get(2),
                            'router': r.get(3), 'key': r.get(4)})

        results = sorted(results,
                         key=lambda e:
                         datetime.datetime.strptime(
                             f"{e['date']} {e['time']}",
                             '%Y-%m-%d %H:%M:%S'))

        new_results = []
        last_known = {}
        host_key = 'key'
        for item in results:
            router = item['router']
            if router not in last_known:
                last_known[router] = item
            elif last_known[router][host_key] != item[host_key]:
                # remember hosts port transitioned from
                new_results.append(last_known[router])
                last_known[router] = item

        ret = self.categorise_events(event, results=new_results)
        if ret:
            return {event.name: ret}, agent

        return None

    def _ml2_ovs_agent_events(self, event):
        """
        :param event: EventCheckResult
        """
        agent = event.section_name
        ret = self._get_event_stats(event.results, event.search_tag)
        if ret:
            return {event.name: ret}, agent

        return None

    def __call__(self, event):
        agent = event.section_name
        if event.name == 'ovsdb-monitor-router-binding-transitions':
            return self._ovsdb_monitor_router_binding_transitions_event(event)

        if event.name in ['rpc-loop', 'router-spawn-events']:
            return self._ml2_ovs_agent_events(event)

        if event.name in ['router-updates']:
            sri = SearchResultIndices(
                event_id=4, metadata=3, metadata_key="router"
            )
            ret = self._get_event_stats(event.results, event.search_tag,
                                        custom_idxs=sri)
            if ret:
                return {event.name: ret}, agent

            return None

        # All other events should be covered by the following
        if event.name == 'ovn-resource-revision-bump':
            ret = self.categorise_events(
                event,
                options=self.EventProcessingOptions(max_results_per_date=5)
            )
        elif event.name == 'ovsdb-transaction-aborted':
            ret = {}
            for result in event.results:
                _date = result.get(1)
                if _date in ret:
                    ret[_date] += 1
                else:
                    ret[_date] = 1

            ret = sorted_dict(ret)
        else:
            ret = self.categorise_events(event)

        if ret:
            return {event.name: ret}, agent

        return None


class NeutronAgentEventChecks(OpenstackEventHandlerBase):
    """
    Loads events we want to check from definitions yaml and executes them. The
    results are sorted by date and the "top 5" are presented along with stats
    on the full set of samples.
    """
    summary_part_index = 7
    event_group = 'neutron.agents'

    @summary_entry('agent-checks', get_min_available_entry_index() + 101)
    def summary_agent_checks(self):
        # NOTE: order is important here
        agents = ['neutron-server', 'neutron-l3-agent', 'neutron-ovs-agent']
        out = self.run() or {}
        return {agent: out[agent] for agent in agents if agent in out}


class OctaviaAgentEventsCallback(OpenstackEventCallbackBase):
    """ Implements OpenStack octavia agent events callback. """
    event_group = 'octavia'
    event_names = ['lb-failover-auto', 'lb-failover-manual',
                   'amp-missed-heartbeats']

    def __call__(self, event):
        if event.name in ['lb-failover-auto', 'lb-failover-manual']:
            results = []
            for e in event.results:
                payload = yaml.safe_load(e.get(3))
                lb_id = payload.get('load_balancer_id')
                if lb_id is None:
                    continue

                results.append({'date': e.get(1), 'time': e.get(2),
                                'key': lb_id})

            ret = self.categorise_events(
                event,
                results=results,
                options=self.EventProcessingOptions(key_by_date=False)
            )
            if ret:
                failover_type = event.name.rpartition('-')[2]
                return {failover_type: ret}, 'lb-failovers'
        else:
            missed_heartbeats = self.categorise_events(
                event,
                options=self.EventProcessingOptions(key_by_date=False)
            )
            if not missed_heartbeats:
                return None

            # sort each amp by occurences
            for ts_date, amps in missed_heartbeats.items():
                amps_sorted = utils.sorted_dict(amps, key=lambda e: e[1],
                                                reverse=True)
                missed_heartbeats[ts_date] = amps_sorted

            # then sort by date
            return utils.sorted_dict(missed_heartbeats)

        return None


class OctaviaAgentEventChecks(OpenstackEventHandlerBase):
    """ Implements Octavia agent events handler. """
    summary_part_index = 10
    event_group = 'octavia'

    @summary_entry('agent-checks', get_min_available_entry_index() + 101)
    def summary_agent_checks(self):
        out = self.run()
        if out:
            return {self.event_group: out}

        return None


class NovaComputeEventCallbacks(OpenstackEventCallbackBase):
    """  Process nova-compute events. """
    event_group = 'nova.nova-compute'
    event_names = ['pci-dev-not-found', 'vm-build-times', 'lock-held-times']

    def __call__(self, event):
        if event.name == 'pci-dev-not-found':
            ret = self.categorise_events(event)
            if ret:
                return ret, 'PciDeviceNotFoundById'
        elif event.name == 'vm-build-times':
            limit = 60
            ret = self.categorise_events(event,
                                         options=self.EventProcessingOptions(
                                             tally_value_limit_min=limit,
                                             sort_tally_by_value=False,
                                             max_results_per_date=5))
            if ret:
                return {f'{event.name}-gt-{limit}s': ret}, 'nova-compute'
        else:
            # ignore times < 1s
            ret = self.categorise_events(event,
                                         options=self.EventProcessingOptions(
                                             tally_value_limit_min=1,
                                             sort_tally_by_value=False,
                                             max_results_per_date=5))
            if ret:
                return {event.name: ret}, 'nova-compute'

        return None


class NovaComputeEventChecks(OpenstackEventHandlerBase):
    """ Implements Nova Compute events handler. """
    summary_part_index = 11
    event_group = 'nova.nova-compute'

    @summary_entry('agent-checks', get_min_available_entry_index() + 101)
    def summary_agent_checks(self):
        out = self.run()
        if out:
            return {'nova': out}

        return None


class ApparmorCallback(OpenstackEventCallbackBase):
    """ Implements Apparmor events callback. """
    event_group = 'apparmor'
    event_names = ['nova', 'neutron']

    def __call__(self, event):
        # pylint: disable=duplicate-code
        results = [{'date': f"{r.get(1)} {r.get(2)}",
                    'time': r.get(3),
                    'key': r.get(4)} for r in event.results]
        ret = self.categorise_events(
            event,
            results=results,
            options=self.EventProcessingOptions(key_by_date=False),
        )
        if ret:
            # event.name must be the service name, event.section is the aa
            # action.
            return {event.name: ret}, event.section_name

        return None


class AgentApparmorChecks(OpenstackEventHandlerBase):
    """ Implements Apparmor events handler. """
    summary_part_index = 12
    event_group = 'apparmor'

    @summary_entry('agent-checks', get_min_available_entry_index() + 101)
    def summary_agent_checks(self):
        out = self.run()
        if out:
            return {self.event_group: out}

        return None


class L3HACallback(OpenstackEventCallbackBase):
    """ Implements Neutron L3HA events callback. """
    event_group = 'neutron.ml2-routers'
    event_names = ['vrrp-transitions']

    @staticmethod
    def check_vrrp_transitions(transitions):
        # there will likely be a large number of transitions if we look across
        # all time so dont run this check.
        if HotSOSConfig.use_all_logs:
            return None

        max_transitions = 0
        warn_count = 0
        threshold = VRRP_TRANSITION_WARN_THRESHOLD
        for router in transitions:
            r = transitions[router]
            _transitions = sum(t for d, t in r.items())
            if _transitions > threshold:
                max_transitions = max(_transitions, max_transitions)
                warn_count += 1

        if warn_count:
            msg = (f"{warn_count} router(s) have had more than {threshold} "
                   f"vrrp transitions (max={max_transitions}) in the last 24 "
                   "hours.")
            IssuesManager().add(NeutronL3HAWarning(msg))

        return None

    def __call__(self, event):
        results = []
        for r in event.results:
            router = NeutronHAInfo().find_router_with_vr_id(r.get(3))
            if not router:
                log.debug("could not find router with vr_id %s", r.get(3))
                continue

            results.append({'date': r.get(1), 'time': r.get(2),
                            'key': router.uuid})

        transitions = self.categorise_events(
            event,
            results=results,
            options=self.EventProcessingOptions(key_by_date=False),
        )
        if transitions:
            # run checks
            self.check_vrrp_transitions(transitions)
            # add info to summary
            return {'transitions': transitions}, 'keepalived'

        return None


class NeutronL3HAEventCheckJournalCtl():
    """ Implements Neutron L3HA event check journalctl. """
    @staticmethod
    def args():
        """ Args callback for event cli command """
        args = []
        kwargs = {'unit': 'neutron-l3-agent'}
        if not HotSOSConfig.use_all_logs:
            kwargs['date'] = CLIHelper().date(format="--iso-8601")

        return args, kwargs


class NeutronL3HAEventChecks(OpenstackEventHandlerBase):
    """ Implements Neutron L3HA events handler. """
    summary_part_index = 13
    event_group = 'neutron.ml2-routers'

    @summary_entry('agent-checks', get_min_available_entry_index() + 101)
    def summary_agent_checks(self):
        out = self.run()
        if out:
            return {'neutron-l3ha': out}

        return None
