import datetime
import yaml

from core import constants
from core.analytics import LogEventStats, SearchResultIndices
from core.cli_helpers import CLIHelper
from core.checks import CallbackHelper
from core.issues import (
    issue_types,
    issue_utils,
)
from core.log import log
from core.searchtools import FileSearcher
from core import utils
from core.plugins.openstack import (
    AGENT_ERROR_KEY_BY_TIME,
    NeutronHAInfo,
    OpenstackChecksBase,
    OpenstackEventChecksBase,
)
from core.utils import sorted_dict

YAML_PRIORITY = 9
EVENTCALLBACKS = CallbackHelper()
VRRP_TRANSITION_WARN_THRESHOLD = 8


class ApacheEventChecks(OpenstackEventChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, callback_helper=EVENTCALLBACKS,
                         yaml_defs_group='apache',
                         event_results_output_key='apache', **kwargs)

    @EVENTCALLBACKS.callback
    def connection_refused(self, event):
        events = {}
        ports_max = {}
        for result in event.results:
            month = datetime.datetime.strptime(result.get(1), '%b').month
            day = result.get(2)
            year = result.get(3)
            ts_date = "{}-{}-{}".format(year, month, day)
            addr = result.get(4)
            port = result.get(5)

            addr = "{}:{}".format(addr, port)
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
                   'working properly - {} - please check'.
                   format(','.join(ports_max.keys())))
            issue_utils.add_issue(issue_types.OpenstackWarning(msg))

        return sorted_dict(events)


class NeutronAgentEventChecks(OpenstackEventChecksBase):
    """
    Loads events we want to check from definitions yaml and executes them. The
    results are sorted by date and the "top 5" are presented along with stats
    on the full set of samples.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, callback_helper=EVENTCALLBACKS,
                         yaml_defs_group='neutron-agent-checks', **kwargs)

    def _get_event_stats(self, results, event_name, custom_idxs=None):
        stats = LogEventStats(results, event_name, custom_idxs=custom_idxs)
        stats.run()
        top5 = stats.get_top_n_events_sorted(5)
        if not top5:
            return

        return {"top": top5,
                "stats": stats.get_event_stats()}

    @EVENTCALLBACKS.callback
    def router_updates(self, event):
        agent = event.section
        sri = SearchResultIndices(event_id_idx=4,
                                  metadata_idx=3,
                                  metadata_key='router')
        ret = self._get_event_stats(event.results, event.name,
                                    custom_idxs=sri)
        if ret:
            return {event.name: ret}, agent

    @EVENTCALLBACKS.callback
    def router_spawn_events(self, event):
        agent = event.section
        ret = self._get_event_stats(event.results, event.name)
        if ret:
            return {event.name: ret}, agent

    @EVENTCALLBACKS.callback
    def rpc_loop(self, event):
        agent = event.section
        ret = self._get_event_stats(event.results, event.name)
        if ret:
            return {event.name: ret}, agent


class OctaviaAgentEventChecks(OpenstackEventChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, callback_helper=EVENTCALLBACKS,
                         yaml_defs_group='octavia-checks',
                         event_results_output_key='octavia', **kwargs)

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

    @EVENTCALLBACKS.callback
    def lb_failover_auto(self, event):
        ret = self._get_failovers(event.results)
        if ret:
            return {'auto': ret}, 'lb-failovers'

    @EVENTCALLBACKS.callback
    def lb_failover_manual(self, event):
        ret = self._get_failovers(event.results)
        if ret:
            return {'manual': ret}, 'lb-failovers'

    @EVENTCALLBACKS.callback
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


class NovaAgentEventChecks(OpenstackEventChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, callback_helper=EVENTCALLBACKS,
                         yaml_defs_group='nova-checks',
                         event_results_output_key='nova', **kwargs)

    @EVENTCALLBACKS.callback
    def pci_dev_not_found(self, event):
        notfounds = {}
        for result in event.results:
            ts_date = result.get(1)
            ts_time = result.get(2)
            pci_dev = result.get(3)

            if ts_date not in notfounds:
                notfounds[ts_date] = {}

            if AGENT_ERROR_KEY_BY_TIME:
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


class AgentApparmorChecks(OpenstackEventChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, callback_helper=EVENTCALLBACKS,
                         yaml_defs_group='apparmor-checks',
                         event_results_output_key='apparmor', **kwargs)

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

    @EVENTCALLBACKS.callback
    def nova(self, event):
        action = event.section
        return self._get_aa_stats(event.results, 'nova'), action

    @EVENTCALLBACKS.callback
    def neutron(self, event):
        action = event.section
        return self._get_aa_stats(event.results, 'neutron'), action


class NeutronL3HAEventChecks(OpenstackEventChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, callback_helper=EVENTCALLBACKS,
                         yaml_defs_group='neutron-router-checks',
                         event_results_output_key='neutron-l3ha', **kwargs)
        self.cli = CLIHelper()
        self.ha_info = NeutronHAInfo()

    def check_vrrp_transitions(self, transitions):
        # there will likely be a large number of transitions if we look across
        # all time so dont run this check.
        if constants.USE_ALL_LOGS:
            return

        max_transitions = 0
        warn_count = 0
        threshold = VRRP_TRANSITION_WARN_THRESHOLD
        for router in transitions:
            r = transitions[router]
            transitions = sum([t for d, t in r.items()])
            if transitions > threshold:
                max_transitions = max(transitions, max_transitions)
                warn_count += 1

        if warn_count:
            msg = ("{} router(s) have had more than {} vrrp transitions "
                   "(max={}) in the last 24 hours".format(warn_count,
                                                          threshold,
                                                          max_transitions))
            issue_utils.add_issue(issue_types.NeutronL3HAWarning(msg))

    def journalctl_args(self):
        """ Args callback for event cli command """
        args = []
        kwargs = {'unit': 'neutron-l3-agent'}
        if not constants.USE_ALL_LOGS:
            kwargs['date'] = self.cli.date(format="--iso-8601").rstrip()

        return args, kwargs

    @EVENTCALLBACKS.callback
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


class AgentEventChecks(OpenstackChecksBase):

    def __call__(self):
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
            check.register_search_terms()

        results = s.search()
        output = {}
        for check in checks:
            check_results = check.process_results(results)
            if check_results:
                output.update(check_results)

        if output:
            self._output = {"agent-checks": output}
