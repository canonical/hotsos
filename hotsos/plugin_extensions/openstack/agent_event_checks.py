import datetime
import yaml

from hotsos.core.config import HotSOSConfig
from hotsos.core.analytics import LogEventStats, SearchResultIndices
from hotsos.core.cli_helpers import CLIHelper
from hotsos.core.ycheck import CallbackHelper
from hotsos.core.issues import (
    IssueContext,
    IssuesManager,
    NeutronL3HAWarning,
    OpenstackWarning
)
from hotsos.core.log import log
from hotsos.core.searchtools import FileSearcher
from hotsos.core import utils
from hotsos.core.plugins.openstack import (
    NeutronHAInfo,
    OpenstackChecksBase,
    OpenstackEventChecksBase,
)
from hotsos.core.utils import sorted_dict

EVENTCALLBACKS = CallbackHelper()
VRRP_TRANSITION_WARN_THRESHOLD = 8


class ApacheEventChecks(OpenstackEventChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, callback_helper=EVENTCALLBACKS,
                         yaml_defs_group='apache', **kwargs)

    @EVENTCALLBACKS.callback()
    def connection_refused(self, event):
        events = {}
        ports_max = {}
        context = {}
        for result in event.results:
            month = datetime.datetime.strptime(result.get(1), '%b').month
            day = result.get(2)
            year = result.get(3)
            ts_date = "{}-{}-{}".format(year, month, day)
            addr = result.get(4)
            port = result.get(5)
            addr = "{}:{}".format(addr, port)
            if result.source in context:
                context[result.source].append(result.linenumber)
            else:
                context[result.source] = [result.linenumber]

            if ts_date not in events:
                events[ts_date] = {}

            if addr not in events[ts_date]:
                events[ts_date][addr] = 1
            else:
                events[ts_date][addr] += 1

        for addrs in events.values():
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

        return sorted_dict(events)

    def __summary_apache(self):
        return self.final_event_results


class NeutronAgentEventChecks(OpenstackEventChecksBase):
    """
    Loads events we want to check from definitions yaml and executes them. The
    results are sorted by date and the "top 5" are presented along with stats
    on the full set of samples.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, callback_helper=EVENTCALLBACKS,
                         yaml_defs_group='neutron-agent-checks', **kwargs)

    def _get_event_stats(self, results, tag_prefix, custom_idxs=None):
        stats = LogEventStats(results, tag_prefix, custom_idxs=custom_idxs)
        stats.run()
        top5 = stats.get_top_n_events_sorted(5)
        if not top5:
            return

        return {"top": top5,
                "stats": stats.get_event_stats()}

    @EVENTCALLBACKS.callback()
    def router_updates(self, event):
        agent = event.section
        sri = SearchResultIndices(event_id_idx=4,
                                  metadata_idx=3,
                                  metadata_key='router')
        tag_prefix = "{}.{}".format(event.section, event.name)
        ret = self._get_event_stats(event.results, tag_prefix, custom_idxs=sri)
        if ret:
            return {event.name: ret}, agent

    @EVENTCALLBACKS.callback('rpc-loop', 'router-spawn-events')
    def process_events(self, event):
        agent = event.section
        tag_prefix = "{}.{}".format(event.section, event.name)
        ret = self._get_event_stats(event.results, tag_prefix)
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
        super().__init__(*args, callback_helper=EVENTCALLBACKS,
                         yaml_defs_group='octavia-checks', **kwargs)

    def _get_failover(self, result):
        ts_date = result.get(1)
        payload = yaml.safe_load(result.get(2))
        lb_id = payload.get("load_balancer_id")
        if lb_id is None:
            return None, None

        return ts_date, lb_id

    def _get_failovers(self, results):
        failovers = {}
        for r in results:
            ts_date, lb_id = self._get_failover(r)
            if ts_date is None:
                continue

            if ts_date not in failovers:
                failovers[ts_date] = {}

            if lb_id not in failovers[ts_date]:
                failovers[ts_date][lb_id] = 1
            else:
                failovers[ts_date][lb_id] += 1

        return failovers

    @EVENTCALLBACKS.callback('lb-failover-auto', 'lb-failover-manual')
    def lb_failovers(self, event):
        ret = self._get_failovers(event.results)
        if ret:
            failover_type = event.name.rpartition('-')[2]
            return {failover_type: ret}, 'lb-failovers'

    @EVENTCALLBACKS.callback()
    def amp_missed_heartbeats(self, event):
        missed_heartbeats = {}
        for r in event.results:
            ts_date = r.get(1)
            amp_id = r.get(2)

            if ts_date not in missed_heartbeats:
                missed_heartbeats[ts_date] = {}

            if amp_id not in missed_heartbeats[ts_date]:
                missed_heartbeats[ts_date][amp_id] = 1
            else:
                missed_heartbeats[ts_date][amp_id] += 1

        # sort each amp by occurences
        for ts_date, amps in missed_heartbeats.items():
            missed_heartbeats[ts_date] = utils.sorted_dict(amps,
                                                           key=lambda e: e[1],
                                                           reverse=True)

        if not missed_heartbeats:
            return

        # then sort by date
        return utils.sorted_dict(missed_heartbeats)

    def __summary_octavia(self):
        return self.final_event_results


class NovaAgentEventChecks(OpenstackEventChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, callback_helper=EVENTCALLBACKS,
                         yaml_defs_group='nova-checks', **kwargs)

    @EVENTCALLBACKS.callback()
    def pci_dev_not_found(self, event):
        notfounds = {}
        for result in event.results:
            ts_date = result.get(1)
            ts_time = result.get(2)
            pci_dev = result.get(3)

            if ts_date not in notfounds:
                notfounds[ts_date] = {}

            if self.agent_error_key_by_time:
                if ts_time not in notfounds:
                    notfounds[ts_date][ts_time] = {pci_dev: 1}
                elif pci_dev not in notfounds[ts_date][ts_time]:
                    notfounds[ts_date][ts_time][pci_dev] = 1
                else:
                    notfounds[ts_date][ts_time][pci_dev] += 1
            else:
                if pci_dev not in notfounds[ts_date]:
                    notfounds[ts_date][pci_dev] = 1
                else:
                    notfounds[ts_date][pci_dev] += 1

        return notfounds, 'PciDeviceNotFoundById'

    def __summary_nova(self):
        return self.final_event_results


class AgentApparmorChecks(OpenstackEventChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, callback_helper=EVENTCALLBACKS,
                         yaml_defs_group='apparmor-checks', **kwargs)

    def _get_aa_stats(self, results, service):
        info = {}
        for r in results:
            ts = r.get(1)
            profile = r.get(2)
            if service not in info:
                info[service] = {}

            if ts not in info[service]:
                info[service][ts] = {}

            if profile not in info[service][ts]:
                info[service][ts][profile] = 1
            else:
                info[service][ts][profile] += 1

        if info:
            return info

    @EVENTCALLBACKS.callback('nova', 'neutron')
    def openstack_apparmor(self, event):
        action = event.section
        return self._get_aa_stats(event.results, event.name), action

    def __summary_apparmor(self):
        return self.final_event_results


class NeutronL3HAEventChecks(OpenstackEventChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, callback_helper=EVENTCALLBACKS,
                         yaml_defs_group='neutron-router-checks', **kwargs)
        self.cli = CLIHelper()
        self.ha_info = NeutronHAInfo()

    def check_vrrp_transitions(self, transitions):
        # there will likely be a large number of transitions if we look across
        # all time so dont run this check.
        if HotSOSConfig.USE_ALL_LOGS:
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
        if not HotSOSConfig.USE_ALL_LOGS:
            kwargs['date'] = self.cli.date(format="--iso-8601")

        return args, kwargs

    @EVENTCALLBACKS.callback()
    def vrrp_transitions(self, event):
        transitions = {}
        for r in event.results:
            ts_date = r.get(1)
            vr_id = r.get(2)
            router = self.ha_info.find_router_with_vr_id(vr_id)
            if not router:
                log.debug("no router found with vr_id %s", vr_id)
                continue

            uuid = router.uuid
            if uuid not in transitions:
                transitions[uuid] = {ts_date: 1}
            elif ts_date in transitions[uuid]:
                transitions[uuid][ts_date] += 1
            else:
                transitions[uuid][ts_date] = 1

        if transitions:
            # run checks
            self.check_vrrp_transitions(transitions)
            # add info to summary
            return {'transitions': transitions}, 'keepalived'

    def __summary_neutron_l3ha(self):
        return self.final_event_results


class AgentEventChecks(OpenstackChecksBase):

    def __summary_agent_checks(self):
        # Only run if we think Openstack is installed.
        if not self.openstack_installed:
            return

        s = FileSearcher()
        checks = [AgentApparmorChecks(searchobj=s),
                  ApacheEventChecks(searchobj=s),
                  NeutronL3HAEventChecks(searchobj=s),
                  NeutronAgentEventChecks(searchobj=s),
                  NovaAgentEventChecks(searchobj=s),
                  OctaviaAgentEventChecks(searchobj=s)]
        for check in checks:
            check.load()

        results = s.search()
        _final_results = {}
        for check in checks:
            check.run(results)
            check_results = check.raw_output
            if check_results:
                _final_results.update(check_results)

        if _final_results:
            return _final_results
