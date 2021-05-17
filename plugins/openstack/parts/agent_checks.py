#!/usr/bin/python3
import os

from common import (
    constants,
    plugin_yaml,
)
from common.searchtools import (
    FilterDef,
    SearchDef,
    FileSearcher,
)
from common.known_bugs_utils import (
    BugSearchDef,
    add_known_bug,
)
from common.analytics import (
    LogSequenceStats,
    SearchResultIndices,
)
from openstack_common import SERVICE_RESOURCES

AGENT_CHECKS_RESULTS = {"agent-checks": {}}

# search terms are defined here to make them easier to read.
RPC_LOOP_SEARCHES = [
    SearchDef(
        r"^([0-9\-]+) (\S+) .+ Agent rpc_loop - iteration:([0-9]+) started.*",
        tag="rpc-loop-start",
        hint="Agent rpc_loop"),
    SearchDef(
        (r"^([0-9\-]+) (\S+) .+ Agent rpc_loop - iteration:([0-9]+) "
         "completed..+Elapsed:([0-9.]+).+"),
        tag="rpc-loop-end",
        hint="Agent rpc_loop"),
]
ROUTER_EVENT_SEARCHES = [
    # router updates
    SearchDef(
        (r"^([0-9-]+) (\S+) .+ Starting router update for (\S+), .+ "
         r"update_id \S+. .+"),
        tag="router-update-start",
        hint="router update"),
    SearchDef(
        (r"^([0-9-]+) (\S+) .+ Finished a router update for (\S+), "
         r"update_id \S+. Time elapsed: ([0-9.]+)"),
        tag="router-update-end",
        hint="router update"),
    # router state_change_monitor + keepalived spawn
    SearchDef(
        (r"^([0-9-]+) (\S+) .+ Router (\S+) .+ spawn_state_change_monitor"),
        tag="router-spawn-start",
        hint="spawn_state_change"),
    SearchDef(
        (r"^([0-9-]+) (\S+) .+ Keepalived spawned with config "
         r"\S+/ha_confs/([0-9a-z-]+)/keepalived.conf .+"),
        tag="router-spawn-end",
        hint="Keepalived"),
]

# NOTE: only LP bugs supported for now
AGENT_BUG_SEARCHES = [
    BugSearchDef(
        (".+Unknown configuration entry 'no_track' for ip address - "
         "ignoring.*"),
        bug_id="1896506",
        hint="no_track",
        reason=("identified in neutron-l3-agent logs"),
        ),
]


class AgentChecksBase(object):
    MAX_RESULTS = 5

    def __init__(self, searchobj, master_results_key=None):
        """
        @param searchobj: FileSearcher object used for searches.
        @param master_results_key: optional - key into which results
                                   will be stored in master yaml.
        """
        self.searchobj = searchobj
        if master_results_key:
            self.master_results_key = master_results_key

    def register_search_terms(self):
        raise NotImplementedError

    def process_results(self, results):
        raise NotImplementedError


class NeutronL3AgentEventChecks(AgentChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs,
                         master_results_key="neutron-l3-agent")
        self.logs_path = os.path.join(constants.DATA_ROOT,
                                      SERVICE_RESOURCES["neutron"]["logs"])

        l3_agent_base_log = 'neutron-l3-agent.log'
        self.l3_agent_data_source = os.path.join(self.logs_path,
                                                 f'{l3_agent_base_log}')
        if constants.USE_ALL_LOGS:
            self.l3_agent_data_source = f"{self.l3_agent_data_source}*"

        self._l3_agent_info = {}

        # the logs we are looking for are DEBUG/INFO only
        fd = FilterDef(" (INFO|DEBUG) ")
        self.searchobj.add_filter_term(fd, self.l3_agent_data_source)

    def register_search_terms(self):
        for sd in ROUTER_EVENT_SEARCHES:
            self.searchobj.add_search_term(sd, self.l3_agent_data_source)

    def _get_router_update_stats(self, results):
        """Identify router updates that took the longest to complete and report
        the longest updates.
        """
        stats = LogSequenceStats(results, "router-update",
                                 SearchResultIndices(duration_idx=4))
        stats()
        top5 = stats.get_top_n_sorted(5)
        if not top5:
            return

        info = {"top": top5,
                "stats": stats.get_stats("duration")}
        self._l3_agent_info["router-updates"] = info

    def _get_router_spawn_stats(self, results):
        """Identify HA router keepalived spawn events that took the longest
        to complete and report the longest updates.
        """
        # no duration info available so we tell the checker to calculate etime
        # from date+secs.
        stats = LogSequenceStats(results, "router-spawn")
        stats()
        top5 = stats.get_top_n_sorted(5)
        if not top5:
            return

        info = {"top": top5,
                "stats": stats.get_stats("duration")}
        self._l3_agent_info["router-spawn-events"] = info

    def process_results(self, results):
        self._get_router_spawn_stats(results)
        self._get_router_update_stats(results)
        return self._l3_agent_info


class NeutronOVSAgentEventChecks(AgentChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs,
                         master_results_key="neutron-ovs-agent")
        self.logs_path = os.path.join(constants.DATA_ROOT,
                                      SERVICE_RESOURCES["neutron"]["logs"])

        ovs_agent_base_log = 'neutron-openvswitch-agent.log'
        self.ovs_agent_data_source = os.path.join(self.logs_path,
                                                  f'{ovs_agent_base_log}')
        if constants.USE_ALL_LOGS:
            self.ovs_agent_data_source = f"{self.ovs_agent_data_source}*"

        # the logs we are looking for are INFO only
        fd = FilterDef(" INFO ")
        self.searchobj.add_filter_term(fd, self.ovs_agent_data_source)

    def register_search_terms(self):
        """Add search terms for start and end of a neutron openvswitch agent
        rpc loop.
        """
        for sd in RPC_LOOP_SEARCHES:
            self.searchobj.add_search_term(sd, self.ovs_agent_data_source)

    def process_results(self, results):
        """Process the search results and display longest running rpc_loops
        with stats.
        """
        stats = LogSequenceStats(results, "rpc-loop",
                                 SearchResultIndices(duration_idx=4))
        stats()
        top5 = stats.get_top_n_sorted(5)
        if not top5:
            return

        info = {"rpc-loop": {"top": top5,
                             "stats": stats.get_stats("duration")}}
        return info


class NeutronAgentBugChecks(AgentChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def register_search_terms(self):
        """Add search terms for known bugs."""
        data_source = os.path.join(constants.DATA_ROOT, 'var/log/syslog')
        if constants.USE_ALL_LOGS:
            data_source = "{}*".format(data_source)

        for bugsearch in AGENT_BUG_SEARCHES:
            self.searchobj.add_search_term(bugsearch, data_source)

    def process_results(self, results):
        for bugsearch in AGENT_BUG_SEARCHES:
            if results.find_by_tag(bugsearch.tag):
                add_known_bug(bugsearch.tag, bugsearch.reason)


def run_agent_checks():
    s = FileSearcher()
    checks = [NeutronL3AgentEventChecks(s),
              NeutronOVSAgentEventChecks(s),
              NeutronAgentBugChecks(s),
              ]

    for check in checks:
        check.register_search_terms()

    results = s.search()

    for check in checks:
        check_results = check.process_results(results)
        if check_results:
            key = check.master_results_key
            AGENT_CHECKS_RESULTS["agent-checks"][key] = check_results


if __name__ == "__main__":
    run_agent_checks()
    if AGENT_CHECKS_RESULTS["agent-checks"]:
        plugin_yaml.save_part(AGENT_CHECKS_RESULTS, priority=9)
