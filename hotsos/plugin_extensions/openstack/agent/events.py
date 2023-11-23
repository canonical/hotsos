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
    OpenstackChecksBase,
    OpenstackEventHandlerBase,
    OpenstackEventCallbackBase,
)
from hotsos.core.plugins.openstack.neutron import NeutronHAInfo
from hotsos.core.search import (
    FileSearcher,
    SearchConstraintSearchSince,
)
from hotsos.core import utils
from hotsos.core.utils import sorted_dict
from hotsos.core.ycheck.engine.properties.search import CommonTimestampMatcher

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
    event_group = 'apache'

    def __104_summary_apache(self):
        return self.final_event_results


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
    event_group = 'http-requests'

    def __105_summary_http_requests(self):
        out = self.final_event_results
        if out:
            return out


class AgentEventsCallback(OpenstackEventCallbackBase):
    event_group = 'neutron.agents'
    ovsdbapp_event_names = ['ovsdbapp-nb-leader-reconnect',
                            'ovsdbapp-sb-leader-reconnect']
    event_names = ['rpc-loop', 'router-spawn-events', 'router-updates']
    event_names += ovsdbapp_event_names

    def _get_event_stats(self, results, tag_prefix, custom_idxs=None):
        stats = LogEventStats(results, tag_prefix, custom_idxs=custom_idxs)
        stats.run()
        top5 = stats.get_top_n_events_sorted(5)
        if not top5:
            return

        return {"top": top5,
                "stats": stats.get_event_stats()}

    def __call__(self, event):
        agent = event.section
        if event.name in self.ovsdbapp_event_names:
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
    event_group = 'neutron.agents'

    # NOTE: can share summary index with l3 agent since they will never be
    #       colocated.
    def __102_summary_neutron_server(self):
        out = self.final_event_results or {}
        return out.get('neutron-server')

    def __102_summary_neutron_l3_agent(self):
        out = self.final_event_results or {}
        return out.get('neutron-l3-agent')

    def __103_summary_neutron_ovs_agent(self):
        out = self.final_event_results or {}
        return out.get('neutron-ovs-agent')


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
    event_group = 'octavia'

    def __106_summary_octavia(self):
        return self.final_event_results


class PCINotFoundCallback(OpenstackEventCallbackBase):
    event_group = 'nova.nova-compute'
    event_names = ['pci-dev-not-found']

    def __call__(self, event):
        ret = self.categorise_events(event)
        if ret:
            return ret, 'PciDeviceNotFoundById'


class NovaComputeEventChecks(OpenstackEventHandlerBase):
    event_group = 'nova.nova-compute'

    def __107_summary_nova(self):
        return self.final_event_results


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
    event_group = 'apparmor'

    def __108_summary_apparmor(self):
        return self.final_event_results


class L3HACallback(OpenstackEventCallbackBase):
    event_group = 'neutron.ml2-routers'
    event_names = ['vrrp-transitions']

    def check_vrrp_transitions(self, transitions):
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


class NeutronL3HAEventChecks(OpenstackEventHandlerBase):
    event_group = 'neutron.ml2-routers'

    def journalctl_args(self):
        """ Args callback for event cli command """
        args = []
        kwargs = {'unit': 'neutron-l3-agent'}
        if not HotSOSConfig.use_all_logs:
            kwargs['date'] = CLIHelper().date(format="--iso-8601")

        return args, kwargs

    def __109_summary_neutron_l3ha(self):
        return self.final_event_results


class AgentEventChecks(OpenstackChecksBase):
    summary_part_index = 7

    def _run_checks(self, checks):
        # Only run if we think Openstack is installed.
        if not self.openstack_installed:
            return

        searcher = FileSearcher(constraint=SearchConstraintSearchSince(
                                        ts_matcher_cls=CommonTimestampMatcher))
        check_objs = [c(searcher=searcher) for c in checks]
        for check in check_objs:
            check.load()

        results = searcher.run()
        _final_results = {}
        for check in check_objs:
            check.run(results)
            check_results = check.raw_output
            if check_results:
                _final_results.update(check_results)

        return _final_results

    def __100_summary_api_info(self):
        checks = [APIEvents]
        results = self._run_checks(checks)
        if results:
            return results

    def __101_summary_agent_checks(self):
        checks = [AgentApparmorChecks,
                  ApacheEventChecks,
                  NeutronL3HAEventChecks,
                  NeutronAgentEventChecks,
                  NovaComputeEventChecks,
                  OctaviaAgentEventChecks]
        results = self._run_checks(checks)
        if results:
            return results
