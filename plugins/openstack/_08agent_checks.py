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
from common.known_bugs_utils import add_known_bug
from openstack_common import (
    OPENSTACK_AGENT_ERROR_KEY_BY_TIME as AGENT_ERROR_KEY_BY_TIME,
    AGENT_DAEMON_NAMES,
    AGENT_LOG_PATHS,
)
from openstack_exceptions import (
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


class AgentChecksBase(object):
    MAX_RESULTS = 5

    def __init__(self, searchobj):
        self.searchobj = searchobj


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


class NeutronAgentChecks(AgentChecksBase):

    def __init__(self, searchobj):
        super().__init__(searchobj)
        self.logs_path = os.path.join(constants.DATA_ROOT,
                                      AGENT_LOG_PATHS["neutron"])

        ovs_agent_base_log = 'neutron-openvswitch-agent.log'
        self.ovs_agent_data_source = os.path.join(self.logs_path,
                                                  f'{ovs_agent_base_log}')
        l3_agent_base_log = 'neutron-l3-agent.log'
        self.l3_agent_data_source = os.path.join(self.logs_path,
                                                 f'{l3_agent_base_log}')
        if constants.USE_ALL_LOGS:
            self.ovs_agent_data_source = f"{self.ovs_agent_data_source}*"
            self.l3_agent_data_source = f"{self.l3_agent_data_source}*"

        self.l3_agent_info = {}
        self.ovs_agent_info = {}

    def add_rpc_loop_search_terms(self):
        """Add search terms for start and end of a neutron openvswitch agent
        rpc loop.
        """
        for sd in RPC_LOOP_SEARCHES:
            self.searchobj.add_search_term(sd, self.ovs_agent_data_source)

    def process_rpc_loop_results(self, results):
        """Process the search results and display longest running rpc_loops
        with stats.
        """
        stats = LogSequenceStats(results, "rpc-loop",
                                 SearchResultIndices(duration_idx=4))
        stats()
        top5 = stats.get_top_n_sorted(5)
        if not top5:
            return

        info = {"top": top5,
                "stats": stats.get_stats("duration")}
        self.ovs_agent_info["rpc-loop"] = info

    def add_router_event_search_terms(self):
        for sd in ROUTER_EVENT_SEARCHES:
            self.searchobj.add_search_term(sd, self.l3_agent_data_source)

    def _get_router_update_stats(self, results):
        """Identify router updates that took the longest to complete and report
        the top longest updates.
        """
        stats = LogSequenceStats(results, "router-update",
                                 SearchResultIndices(duration_idx=4))
        stats()
        top5 = stats.get_top_n_sorted(5)
        if not top5:
            return

        info = {"top": top5,
                "stats": stats.get_stats("duration")}
        self.l3_agent_info["router-updates"] = info

    def _get_router_spawn_stats(self, results):
        """Identify HA router keepalived spawn events that took the longest
        to complete and report the top longest updates.
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
        self.l3_agent_info["router-spawn-events"] = info

    def process_router_event_results(self, results):
        self._get_router_spawn_stats(results)
        self._get_router_update_stats(results)


class CommonAgentChecks(AgentChecksBase):

    def __init__(self, searchobj):
        super().__init__(searchobj)
        self.agent_log_issues = {}

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

        # The following must be ERROR log level
        self.agent_exceptions = {"cinder": [] + agent_exceptions_common,
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
        # NOTE: only LP bugs supported for now
        self.agent_bug_search_terms = {
            "1896506": {"expr":
                        (".+Unknown configuration entry 'no_track' for "
                         "ip address - ignoring.*"),
                        "reason": ("identified in neutron-l3-agent logs by "
                                   "{}.{}".
                                   format(constants.PLUGIN_NAME,
                                          constants.PART_NAME))}
            }

    def add_agent_terms(self, service):
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
            for exc_msg in self.agent_exceptions.get(service, []):
                expr = r"^([0-9\-]+) (\S+) .+{}.*".format(exc_msg)
                self.searchobj.add_search_term(SearchDef(expr, tag=agent,
                                                         hint=exc_msg),
                                               data_source)

            for msg in self.agent_issues.get(service, []):
                expr = r"^([0-9\-]+) (\S+) .+{}.*".format(msg)
                self.searchobj.add_search_term(SearchDef(expr, tag=agent,
                                                         hint=msg),
                                               data_source)

    def add_bug_search_terms(self):
        """Add search terms for known bugs."""
        data_source = os.path.join(constants.DATA_ROOT, 'var/log/syslog')
        if constants.USE_ALL_LOGS:
            data_source = "{}*".format(data_source)

        for tag in self.agent_bug_search_terms:
            expr = self.agent_bug_search_terms[tag]["expr"]
            self.searchobj.add_search_term(SearchDef(expr, tag=tag),
                                           data_source)

    def add_agents_issues_search_terms(self):
        # Add search terms for everything at once
        for service in AGENT_DAEMON_NAMES:
            self.add_agent_terms(service)

        self.add_bug_search_terms()

    def process_bug_results(self, results):
        for tag in self.agent_bug_search_terms:
            if results.find_by_tag(tag):
                reason = self.agent_bug_search_terms[tag]["reason"]
                add_known_bug(tag, description=reason)

    def process_agent_results(self, results, service):
        for agent in AGENT_DAEMON_NAMES[service]:
            e = get_agent_exceptions(results.find_by_tag(agent),
                                     AGENT_ERROR_KEY_BY_TIME)
            if e:
                if service not in self.agent_log_issues:
                    self.agent_log_issues[service] = {}

                self.agent_log_issues[service][agent] = e

    def process_agent_issues_results(self, results):
        """
        Collect information about Openstack agents. This includes errors,
        exceptions and known bugs.
        """
        # process the results
        for service in AGENT_DAEMON_NAMES:
            self.process_agent_results(results, service)

        self.process_bug_results(results)


if __name__ == "__main__":
    s = FileSearcher()
    common_checks = CommonAgentChecks(s)
    common_checks.add_agents_issues_search_terms()
    neutron_checks = NeutronAgentChecks(s)
    neutron_checks.add_rpc_loop_search_terms()
    neutron_checks.add_router_event_search_terms()

    results = s.search()

    neutron_checks.process_rpc_loop_results(results)
    neutron_checks.process_router_event_results(results)
    common_checks.process_agent_issues_results(results)

    AGENT_CHECKS = {"agent-checks": {}}
    if common_checks.agent_log_issues:
        AGENT_CHECKS["agent-checks"]["agent-issues"] = \
            common_checks.agent_log_issues

    if neutron_checks.ovs_agent_info:
        AGENT_CHECKS["agent-checks"]["neutron-ovs-agent"] = \
            neutron_checks.ovs_agent_info

    if neutron_checks.l3_agent_info:
        AGENT_CHECKS["agent-checks"]["neutron-l3-agent"] = \
            neutron_checks.l3_agent_info

    if AGENT_CHECKS["agent-checks"]:
        plugin_yaml.dump(AGENT_CHECKS)
