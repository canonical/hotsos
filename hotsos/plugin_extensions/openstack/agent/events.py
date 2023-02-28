import datetime
import yaml

from hotsos.core.plugintools import summary_entry_offset as idx
from hotsos.core.config import HotSOSConfig
from hotsos.core.analytics import LogEventStats, SearchResultIndices
from hotsos.core.host_helpers import CLIHelper
from hotsos.core.ycheck.events import CallbackHelper
from hotsos.core.issues import (
    IssueContext,
    IssuesManager,
    NeutronL3HAWarning,
    OpenstackWarning
)
from hotsos.core.log import log
from hotsos.core.search import (
    FileSearcher,
    SearchConstraintSearchSince,
)
from hotsos.core import utils
from hotsos.core.plugins.openstack.common import (
    OpenstackChecksBase,
    OpenstackEventChecksBase,
)
from hotsos.core.plugins.openstack.openstack import OPENSTACK_LOGS_TS_EXPR
from hotsos.core.plugins.openstack.neutron import NeutronHAInfo
from hotsos.core.utils import sorted_dict

EVENTCALLBACKS = CallbackHelper()
VRRP_TRANSITION_WARN_THRESHOLD = 8


class ApacheEventChecks(OpenstackEventChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(EVENTCALLBACKS, *args,
                         yaml_defs_group='apache', **kwargs)

    @EVENTCALLBACKS.callback(event_group='apache')
    def connection_refused(self, event):
        ports_max = {}
        context = {}

        results = []
        for result in event.results:
            # save some context info
            path = self.searchobj.resolve_source_id(result.source_id)
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

    def __summary_apache(self):
        return self.final_event_results


class APIEvents(OpenstackEventChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(EVENTCALLBACKS, *args,
                         yaml_defs_group='http-requests', **kwargs)

    @EVENTCALLBACKS.callback(event_group='http-requests',
                             event_names=['neutron'])
    def http_requests(self, event):
        results = [{'date': r.get(1),
                    'time': r.get(2),
                    'key': r.get(3)} for r in event.results]
        ret = self.categorise_events(event, results=results)
        if ret:
            return ret

    def __summary_http_requests(self):
        out = self.final_event_results
        if out:
            return out


class NeutronAgentEventChecks(OpenstackEventChecksBase):
    """
    Loads events we want to check from definitions yaml and executes them. The
    results are sorted by date and the "top 5" are presented along with stats
    on the full set of samples.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(EVENTCALLBACKS, *args,
                         yaml_defs_group='neutron.agents', **kwargs)

    def _get_event_stats(self, results, tag_prefix, custom_idxs=None):
        stats = LogEventStats(results, tag_prefix, custom_idxs=custom_idxs)
        stats.run()
        top5 = stats.get_top_n_events_sorted(5)
        if not top5:
            return

        return {"top": top5,
                "stats": stats.get_event_stats()}

    @EVENTCALLBACKS.callback(event_group='neutron.agents')
    def router_updates(self, event):
        agent = event.section
        sri = SearchResultIndices(event_id_idx=4,
                                  metadata_idx=3,
                                  metadata_key='router')
        ret = self._get_event_stats(event.results, event.search_tag,
                                    custom_idxs=sri)
        if ret:
            return {event.name: ret}, agent

    @EVENTCALLBACKS.callback(event_group='neutron.agents',
                             event_names=['rpc-loop', 'router-spawn-events'])
    def process_events(self, event):
        agent = event.section
        ret = self._get_event_stats(event.results, event.search_tag)
        if ret:
            return {event.name: ret}, agent

    def __summary_neutron_l3_agent(self):
        out = self.final_event_results or {}
        return out.get('neutron-l3-agent')

    def __summary_neutron_ovs_agent(self):
        out = self.final_event_results or {}
        return out.get('neutron-ovs-agent')


class OctaviaAgentEventChecks(OpenstackEventChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(EVENTCALLBACKS, *args,
                         yaml_defs_group='octavia', **kwargs)

    @EVENTCALLBACKS.callback(event_group='octavia',
                             event_names=['lb-failover-auto',
                                          'lb-failover-manual'])
    def lb_failovers(self, event):
        results = []
        for e in event.results:
            payload = yaml.safe_load(e.get(2))
            lb_id = payload.get('load_balancer_id')
            if lb_id is None:
                continue

            results.append({'date': e.get(1), 'key': lb_id})

        ret = self.categorise_events(event, results=results, key_by_date=False)
        if ret:
            failover_type = event.name.rpartition('-')[2]
            return {failover_type: ret}, 'lb-failovers'

    @EVENTCALLBACKS.callback(event_group='octavia')
    def amp_missed_heartbeats(self, event):
        missed_heartbeats = self.categorise_events(event, key_by_date=False)
        if not missed_heartbeats:
            return

        # sort each amp by occurences
        for ts_date, amps in missed_heartbeats.items():
            missed_heartbeats[ts_date] = utils.sorted_dict(amps,
                                                           key=lambda e: e[1],
                                                           reverse=True)

        # then sort by date
        return utils.sorted_dict(missed_heartbeats)

    def __summary_octavia(self):
        return self.final_event_results


class NovaComputeEventChecks(OpenstackEventChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(EVENTCALLBACKS, *args,
                         yaml_defs_group='nova.nova-compute', **kwargs)

    @EVENTCALLBACKS.callback(event_group='nova.nova-compute')
    def pci_dev_not_found(self, event):
        ret = self.categorise_events(event)
        if ret:
            return ret, 'PciDeviceNotFoundById'

    def __summary_nova(self):
        return self.final_event_results


class AgentApparmorChecks(OpenstackEventChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(EVENTCALLBACKS, *args,
                         yaml_defs_group='apparmor', **kwargs)

    @EVENTCALLBACKS.callback(event_group='apparmor',
                             event_names=['nova', 'neutron'])
    def openstack_apparmor(self, event):
        results = [{'date': "{} {}".format(r.get(1), r.get(2)),
                    'time': r.get(3),
                    'key': r.get(4)} for r in event.results]
        ret = self.categorise_events(event, results=results,
                                     key_by_date=False)
        if ret:
            # event.name must be the service name, event.section is the aa
            # action.
            return {event.name: ret}, event.section

    def __summary_apparmor(self):
        return self.final_event_results


class NeutronL3HAEventChecks(OpenstackEventChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(EVENTCALLBACKS, *args,
                         yaml_defs_group='neutron.ml2-routers', **kwargs)
        self.cli = CLIHelper()
        self.ha_info = NeutronHAInfo()

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
            _transitions = sum([t for d, t in r.items()])
            if _transitions > threshold:
                max_transitions = max(_transitions, max_transitions)
                warn_count += 1

        if warn_count:
            msg = ("{} router(s) have had more than {} vrrp transitions "
                   "(max={}) in the last 24 hours.".format(warn_count,
                                                           threshold,
                                                           max_transitions))
            IssuesManager().add(NeutronL3HAWarning(msg))

    def journalctl_args(self):
        """ Args callback for event cli command """
        args = []
        kwargs = {'unit': 'neutron-l3-agent'}
        if not HotSOSConfig.use_all_logs:
            kwargs['date'] = self.cli.date(format="--iso-8601")

        return args, kwargs

    @EVENTCALLBACKS.callback(event_group='neutron.ml2-routers')
    def vrrp_transitions(self, event):
        results = []
        for r in event.results:
            router = self.ha_info.find_router_with_vr_id(r.get(2))
            if not router:
                log.debug("could not find router with vr_id %s", r.get(2))
                continue

            results.append({'date': r.get(1), 'key': router.uuid})

        transitions = self.categorise_events(event, results=results,
                                             key_by_date=False)
        if transitions:
            # run checks
            self.check_vrrp_transitions(transitions)
            # add info to summary
            return {'transitions': transitions}, 'keepalived'

    def __summary_neutron_l3ha(self):
        return self.final_event_results


class AgentEventChecks(OpenstackChecksBase):

    def _run_checks(self, checks):
        # Only run if we think Openstack is installed.
        if not self.openstack_installed:
            return

        c = SearchConstraintSearchSince(exprs=[OPENSTACK_LOGS_TS_EXPR])
        s = FileSearcher(constraint=c)
        check_objs = [c(searchobj=s) for c in checks]
        for check in check_objs:
            check.load()

        results = s.run()
        _final_results = {}
        for check in check_objs:
            check.run(results)
            check_results = check.raw_output
            if check_results:
                _final_results.update(check_results)

        return _final_results

    @idx(1)
    def __summary_api_info(self):
        checks = [APIEvents]
        results = self._run_checks(checks)
        if results:
            return results

    @idx(2)
    def __summary_agent_checks(self):
        checks = [AgentApparmorChecks,
                  ApacheEventChecks,
                  NeutronL3HAEventChecks,
                  NeutronAgentEventChecks,
                  NovaComputeEventChecks,
                  OctaviaAgentEventChecks]
        results = self._run_checks(checks)
        if results:
            return results
