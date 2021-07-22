import yaml

from common.searchtools import FileSearcher
from common.analytics import LogSequenceStats, SearchResultIndices
from common import checks, plugintools, utils

YAML_PRIORITY = 9


class NeutronAgentEventChecks(checks.EventChecksBase):
    """
    Loads events we want to check from definitions yaml and executes them. The
    results are sorted by date and the "top 5" are presented along with stats
    on the full set of samples.
    """

    def process_results(self, results):
        """ See defs/events.yaml for definitions. """
        agent_info = {}
        for agent, defs in self.event_definitions.items():
            for label in defs:
                # TODO: find a way to get rid of the need to provide this
                if label == "rpc-loop" or label == "router-updates":
                    sri = SearchResultIndices(duration_idx=4)
                    stats = LogSequenceStats(results, label, sri)
                else:
                    stats = LogSequenceStats(results, label)

                stats()
                top5 = stats.get_top_n_sorted(5)
                if not top5:
                    break

                info = {"top": top5,
                        "stats": stats.get_stats("duration")}
                if agent not in agent_info:
                    agent_info[agent] = {}

                agent_info[agent][label] = info

        return agent_info


class NeutronAgentBugChecks(checks.BugChecksBase):
    """ See defs/bugs.yaml for definitions. """


class OctaviaAgentEventChecks(checks.EventChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

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

    def _get_missed_heartbeats(self, results):
        missed_heartbeats = {}
        for r in results:
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

        # then sort by date
        return utils.sorted_dict(missed_heartbeats)

    def process_results(self, results):
        """ See defs/events.yaml for definitions. """
        failovers = {}
        missed_heartbeats = {}
        for defs in self.event_definitions.values():
            for label in defs:
                _results = results.find_by_tag(label)
                if label.startswith("lb-failover-"):
                    fo_type = label.partition("lb-failover-")[2]
                    f = self._get_failovers(_results)
                    if f:
                        failovers[fo_type] = f
                elif label == "amp-missed-heartbeats":
                    missed_heartbeats = self._get_missed_heartbeats(_results)
                else:
                    raise Exception("unknown label {}".format(label))

        output = {}
        if missed_heartbeats:
            output["amp-missed-heartbeats"] = missed_heartbeats

        if failovers:
            output["lb-failovers"] = failovers

        if output:
            return {"octavia": output}


class AgentApparmorChecks(checks.EventChecksBase):

    def process_results(self, results):
        """ See defs/events.yaml for definitions. """
        info = {}
        for action, defs in self.event_definitions.items():
            for label in defs:
                _results = results.find_by_tag(label)
                for r in _results:
                    ts = r.get(1)
                    profile = r.get(2)
                    if action not in info:
                        info[action] = {}

                    if label not in info[action]:
                        info[action][label] = {}

                    if ts not in info[action][label]:
                        info[action][label][ts] = {}

                    if profile not in info[action][label][ts]:
                        info[action][label][ts][profile] = 1
                    else:
                        info[action][label][ts][profile] += 1

        if info:
            return {"apparmor": info}


class AgentChecks(plugintools.PluginPartBase):

    def __call__(self):
        s = FileSearcher()
        checks = [NeutronAgentEventChecks(s, "neutron-agent-checks"),
                  NeutronAgentBugChecks(s, "neutron"),
                  OctaviaAgentEventChecks(s, "octavia-checks"),
                  AgentApparmorChecks(s, "apparmor-checks")]
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
