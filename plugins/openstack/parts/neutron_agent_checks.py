#!/usr/bin/python3
from common import plugin_yaml
from common.searchtools import FileSearcher
from common.analytics import LogSequenceStats
from common import checks

AGENT_CHECKS_RESULTS = {"agent-checks": {}}


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


def run_agent_checks():
    s = FileSearcher()
    checks = [NeutronAgentEventChecks(s, root="neutron-agent-checks"),
              NeutronAgentBugChecks(s, root="neutron")]
    for check in checks:
        check.register_search_terms()

    results = s.search()
    for check in checks:
        check_results = check.process_results(results)
        if check_results:
            AGENT_CHECKS_RESULTS["agent-checks"] = check_results


if __name__ == "__main__":
    run_agent_checks()
    if AGENT_CHECKS_RESULTS["agent-checks"]:
        plugin_yaml.save_part(AGENT_CHECKS_RESULTS, priority=9)
