import datetime

import yaml
from hotsos.core.analytics import LogEventStats, SearchResultIndices
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

VRRP_TRANSITION_WARN_THRESHOLD = 8


class ApacheEventCallback(OpenstackEventCallbackBase):
    event_group = 'apache'
    event_names = ['connection-refused']

    def __call__(self, event):
        ports_max = {}
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
            results.append({'date': "{}-{}-{}".format(year, month, day),
                            'key': "{}:{}".format(addr, port)})

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
                   'working properly - {} - please check.'.
                   format(','.join(ports_max.keys())))
            IssuesManager().add(OpenstackWarning(msg), IssueContext(**context))

        return sorted_dict(conns_refused)


class ApacheEventChecks(OpenstackEventHandlerBase):
    summary_part_index = 8
    event_group = 'apache'

    def __101_summary_agent_checks(self):
        out = self.run()
        if out:
            return {self.event_group: out}


class APIEventsCallback(OpenstackEventCallbackBase):
    event_group = 'http-requests'
    event_names = ['neutron']

    def __call__(self, event):
        results = [{'date': r.get(1),
                    'key': r.get(2)} for r in event.results]
        ret = self.categorise_events(event, results=results)
        if ret:
            return ret


class APIEvents(OpenstackEventHandlerBase):
    summary_part_index = 9
    event_group = 'http-requests'

    def __100_summary_api_info(self):
        out = self.run()
        if out:
            return {self.event_group: out}


class AgentEventsCallback(OpenstackEventCallbackBase):
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
            return

        return {"top": top5,
                "stats": stats.get_event_stats()}

    def __call__(self, event):
        agent = event.section
        if event.name == 'ovsdb-monitor-router-binding-transitions':
            # The ovsdbmonitor will print bindings which will eventually
            # reflect transitions so we need to filter out contiguous bindings
            # to the same chassis so that we are just left with transitions
            # that we can then count.
            results = []
            for r in event.results:
                results.append({'date': r.get(1), 'time': r.get(2),
                                'router': r.get(3), 'key': r.get(4)})

            results = sorted(results,
                             key=lambda e:
                             datetime.datetime.strptime(
                                 "{} {}".format(e['date'],
                                                e['time']),
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
        elif event.name in self.ovsdbapp_event_names + \
                self.ovn_mech_driver_events:
            if event.name == 'ovn-resource-revision-bump':
                ret = self.categorise_events(event, max_results_per_date=5)
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
        elif event.name in ['rpc-loop', 'router-spawn-events']:
            ret = self._get_event_stats(event.results, event.search_tag)
            if ret:
                return {event.name: ret}, agent
        else:
            sri = SearchResultIndices(event_id_idx=4,
                                      metadata_idx=3,
                                      metadata_key='router')
            ret = self._get_event_stats(event.results, event.search_tag,
                                        custom_idxs=sri)
            if ret:
                return {event.name: ret}, agent


class NeutronAgentEventChecks(OpenstackEventHandlerBase):
    """
    Loads events we want to check from definitions yaml and executes them. The
    results are sorted by date and the "top 5" are presented along with stats
    on the full set of samples.
    """
    summary_part_index = 7
    event_group = 'neutron.agents'

    def __101_summary_agent_checks(self):
        # NOTE: order is important here
        agents = ['neutron-server', 'neutron-l3-agent', 'neutron-ovs-agent']
        out = self.run() or {}
        return {agent: out[agent] for agent in agents if agent in out}


class OctaviaAgentEventsCallback(OpenstackEventCallbackBase):
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

            ret = self.categorise_events(event, results=results,
                                         key_by_date=False)
            if ret:
                failover_type = event.name.rpartition('-')[2]
                return {failover_type: ret}, 'lb-failovers'
        else:
            missed_heartbeats = self.categorise_events(event,
                                                       key_by_date=False)
            if not missed_heartbeats:
                return

            # sort each amp by occurences
            for ts_date, amps in missed_heartbeats.items():
                amps_sorted = utils.sorted_dict(amps, key=lambda e: e[1],
                                                reverse=True)
                missed_heartbeats[ts_date] = amps_sorted

            # then sort by date
            return utils.sorted_dict(missed_heartbeats)


class OctaviaAgentEventChecks(OpenstackEventHandlerBase):
    summary_part_index = 10
    event_group = 'octavia'

    def __101_summary_agent_checks(self):
        out = self.run()
        if out:
            return {self.event_group: out}


class PCINotFoundCallback(OpenstackEventCallbackBase):
    event_group = 'nova.nova-compute'
    event_names = ['pci-dev-not-found']

    def __call__(self, event):
        ret = self.categorise_events(event)
        if ret:
            return ret, 'PciDeviceNotFoundById'


class NovaComputeEventChecks(OpenstackEventHandlerBase):
    summary_part_index = 11
    event_group = 'nova.nova-compute'

    def __101_summary_agent_checks(self):
        out = self.run()
        if out:
            return {'nova': out}


class ApparmorCallback(OpenstackEventCallbackBase):
    event_group = 'apparmor'
    event_names = ['nova', 'neutron']

    def __call__(self, event):
        results = [{'date': "{} {}".format(r.get(1), r.get(2)),
                    'time': r.get(3),
                    'key': r.get(4)} for r in event.results]
        ret = self.categorise_events(event, results=results,
                                     key_by_date=False)
        if ret:
            # event.name must be the service name, event.section is the aa
            # action.
            return {event.name: ret}, event.section


class AgentApparmorChecks(OpenstackEventHandlerBase):
    summary_part_index = 12
    event_group = 'apparmor'

    def __101_summary_agent_checks(self):
        out = self.run()
        if out:
            return {self.event_group: out}


class L3HACallback(OpenstackEventCallbackBase):
    event_group = 'neutron.ml2-routers'
    event_names = ['vrrp-transitions']

    @staticmethod
    def check_vrrp_transitions(transitions):
        # there will likely be a large number of transitions if we look across
        # all time so dont run this check.
        if HotSOSConfig.use_all_logs:
            return

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
            msg = ("{} router(s) have had more than {} vrrp transitions "
                   "(max={}) in the last 24 hours.".format(warn_count,
                                                           threshold,
                                                           max_transitions))
            IssuesManager().add(NeutronL3HAWarning(msg))

    def __call__(self, event):
        results = []
        for r in event.results:
            router = NeutronHAInfo().find_router_with_vr_id(r.get(3))
            if not router:
                log.debug("could not find router with vr_id %s", r.get(3))
                continue

            results.append({'date': r.get(1), 'time': r.get(2),
                            'key': router.uuid})

        transitions = self.categorise_events(event, results=results,
                                             key_by_date=False)
        if transitions:
            # run checks
            self.check_vrrp_transitions(transitions)
            # add info to summary
            return {'transitions': transitions}, 'keepalived'


class NeutronL3HAEventCheckJournalCtl():

    @staticmethod
    def args():
        """ Args callback for event cli command """
        args = []
        kwargs = {'unit': 'neutron-l3-agent'}
        if not HotSOSConfig.use_all_logs:
            kwargs['date'] = CLIHelper().date(format="--iso-8601")

        return args, kwargs


class NeutronL3HAEventChecks(OpenstackEventHandlerBase):
    summary_part_index = 13
    event_group = 'neutron.ml2-routers'

    def __101_summary_agent_checks(self):
        out = self.run()
        if out:
            return {'neutron-l3ha': out}
