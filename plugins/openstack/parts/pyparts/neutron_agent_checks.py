#!/usr/bin/python3
from common.searchtools import FileSearcher
from common.analytics import LogSequenceStats, SearchResultIndices
from common import checks, plugintools

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


class NeutronAgentChecks(plugintools.PluginPartBase):

    def __call__(self):
        s = FileSearcher()
        checks = [NeutronAgentEventChecks(s, "neutron-agent-checks"),
                  NeutronAgentBugChecks(s, "neutron")]
        for check in checks:
            check.register_search_terms()

        results = s.search()
        for check in checks:
            check_results = check.process_results(results)
            if check_results:
                self._output["agent-checks"] = check_results
