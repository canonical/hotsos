#!/usr/bin/python3
import os

from common import (
    constants,
    plugin_yaml,
)
from common.searchtools import (
    SearchDef,
    FileSearcher,
)
from common.known_bugs_utils import (
    BugSearchDef,
    add_known_bug,
)
from openstack_common import (
    OPENSTACK_AGENT_ERROR_KEY_BY_TIME as AGENT_ERROR_KEY_BY_TIME,
    AGENT_DAEMON_NAMES,
    AGENT_LOG_PATHS,
)
from openstack_exceptions import (
    BARBICAN_EXCEPTIONS,
    CASTELLAN_EXCEPTIONS,
    CINDER_EXCEPTIONS,
    MANILA_EXCEPTIONS,
    NOVA_EXCEPTIONS,
    OCTAVIA_EXCEPTIONS,
    OSLO_DB_EXCEPTIONS,
    OSLO_MESSAGING_EXCEPTIONS,
    PYTHON_BUILTIN_EXCEPTIONS,
)
from openstack_utils import (
    get_agent_exceptions,
)

from common.analytics import (
    LogSequenceStats,
    SearchResultIndices,
)

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
        reason=("identified in neutron-l3-agent logs by {}.{}".
                format(constants.PLUGIN_NAME, constants.PART_NAME)),
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
                                      AGENT_LOG_PATHS["neutron"])

        l3_agent_base_log = 'neutron-l3-agent.log'
        self.l3_agent_data_source = os.path.join(self.logs_path,
                                                 f'{l3_agent_base_log}')
        if constants.USE_ALL_LOGS:
            self.l3_agent_data_source = f"{self.l3_agent_data_source}*"

        self._l3_agent_info = {}

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
                                      AGENT_LOG_PATHS["neutron"])

        ovs_agent_base_log = 'neutron-openvswitch-agent.log'
        self.ovs_agent_data_source = os.path.join(self.logs_path,
                                                  f'{ovs_agent_base_log}')
        if constants.USE_ALL_LOGS:
            self.ovs_agent_data_source = f"{self.ovs_agent_data_source}*"

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
                add_known_bug(bugsearch.tag, description=bugsearch.reason)


class CommonAgentChecks(AgentChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs, master_results_key="agent-issues")
        self._agent_log_issues = {}

        agent_exceptions_common = [
            r"(AMQP server on .+ is unreachable)",
            r"(amqp.exceptions.ConnectionForced):",
            r"(OSError: Server unexpectedly closed connection)",
            r"(ConnectionResetError: .+)",
            ]

        # assume all agents use these so add to all
        for exc in OSLO_DB_EXCEPTIONS + OSLO_MESSAGING_EXCEPTIONS + \
                PYTHON_BUILTIN_EXCEPTIONS:
            agent_exceptions_common.append(r"({})".format(exc))

        nova_exceptions_all = [r"(nova.exception.\S+):"]
        nova_exceptions_all.extend(agent_exceptions_common)

        for exc in NOVA_EXCEPTIONS:
            nova_exceptions_all.append(r" ({}):".format(exc))

        octavia_exceptions_all = [] + agent_exceptions_common
        for exc in OCTAVIA_EXCEPTIONS:
            octavia_exceptions_all.append(r" ({}):".format(exc))

        manila_exceptions_all = [] + agent_exceptions_common
        for exc in MANILA_EXCEPTIONS:
            manila_exceptions_all.append(r" ({}):".format(exc))

        barbican_exceptions_all = [] + agent_exceptions_common
        for exc in BARBICAN_EXCEPTIONS:
            barbican_exceptions_all.append(r" ({}):".format(exc))

        cinder_exceptions_all = [] + agent_exceptions_common
        for exc in CINDER_EXCEPTIONS:
            cinder_exceptions_all.append(r" ({}):".format(exc))

        # Whis is a client/interface implemenation not a service so we add it
        # to services that implement it. We print the long form of the
        # exception to indicate it is a non-native exception.
        for exc in CASTELLAN_EXCEPTIONS:
            barbican_exceptions_all.append(r" (\S*\.?{}):".format(exc))
            cinder_exceptions_all.append(r" (\S*\.?{}):".format(exc))

        # The following must be ERROR log level
        self.agent_exceptions = {"barbican": barbican_exceptions_all,
                                 "cinder": cinder_exceptions_all,
                                 "glance": [] + agent_exceptions_common,
                                 "heat": [] + agent_exceptions_common,
                                 "keystone": [] + agent_exceptions_common,
                                 "manila": manila_exceptions_all,
                                 "nova": nova_exceptions_all,
                                 "neutron": [] + agent_exceptions_common,
                                 "octavia": octavia_exceptions_all,
                                 }

        # The following can be any log level
        self.agent_issues = {
            "neutron": [r"(OVS is dead).", r"(RuntimeError):"]
            }

    def _add_terms(self, service, issue_definitions):
        """
        Add search terms for warning, exceptions, errors etc i.e. anything that
        could count as an "issue" of interest.
        """
        data_source_template = os.path.join(constants.DATA_ROOT,
                                            AGENT_LOG_PATHS[service], '{}.log')
        if constants.USE_ALL_LOGS:
            data_source_template = "{}*".format(data_source_template)

        for agent in AGENT_DAEMON_NAMES[service]:
            data_source = data_source_template.format(agent)
            for msg in issue_definitions.get(service, []):
                expr = r"^([0-9\-]+) (\S+) .+{}.*".format(msg)
                self.searchobj.add_search_term(SearchDef(expr, tag=agent,
                                                         hint=msg),
                                               data_source)

    def register_search_terms(self):
        """Register searches for exceptions as well as any other type of issue
        we might want to catch like warning etc which may not be errors or
        exceptions.
        """
        for service in AGENT_DAEMON_NAMES:
            self._add_terms(service, self.agent_exceptions)
            self._add_terms(service, self.agent_issues)

    def _process_agent_results(self, results, service, agent):
        e = get_agent_exceptions(results.find_by_tag(agent),
                                 AGENT_ERROR_KEY_BY_TIME)
        if e:
            if service not in self._agent_log_issues:
                self._agent_log_issues[service] = {}

            self._agent_log_issues[service][agent] = e

    def process_results(self, results):
        """Process search results to see if we got any hits."""
        for service in AGENT_DAEMON_NAMES:
            for agent in AGENT_DAEMON_NAMES[service]:
                self._process_agent_results(results, service, agent)

        return self._agent_log_issues


def run_agent_checks():
    s = FileSearcher()
    checks = [CommonAgentChecks(s),
              NeutronL3AgentEventChecks(s),
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
        plugin_yaml.save_part(AGENT_CHECKS_RESULTS, priority=7)
