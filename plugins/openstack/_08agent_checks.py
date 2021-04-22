#!/usr/bin/python3
import os

import statistics

from datetime import datetime

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
    NOVA_EXCEPTIONS,
    OCTAVIA_EXCEPTIONS,
    OSLO_DB_EXCEPTIONS,
    OSLO_MESSAGING_EXCEPTIONS,
    PYTHON_BUILTIN_EXCEPTIONS,
)
from openstack_utils import (
    get_agent_exceptions,
)


class AgentChecksBase(object):
    MAX_RESULTS = 5

    def __init__(self, searchobj):
        self.searchobj = searchobj


class NeutronAgentChecks(AgentChecksBase):

    def __init__(self, searchobj):
        super().__init__(searchobj)
        logs_path = AGENT_LOG_PATHS["neutron"]
        if constants.USE_ALL_LOGS:
            self.data_source = os.path.join(constants.DATA_ROOT, logs_path,
                                            'neutron-openvswitch-agent.log*')
        else:
            self.data_source = os.path.join(constants.DATA_ROOT, logs_path,
                                            'neutron-openvswitch-agent.log')

        self.l3_agent_info = {}
        self.ovs_agent_info = {}

    def add_rpc_loop_search_terms(self):
        """Add search terms for start and end of a neutron openvswitch agent
        rpc loop.
        """
        expr = (r"^([0-9\-]+) (\S+) .+ Agent rpc_loop - iteration:([0-9]+) "
                "started.*")
        self.searchobj.add_search_term(SearchDef(expr, tag="rpc-loop-start",
                                                 hint="Agent rpc_loop"),
                                       self.data_source)
        expr = (r"^([0-9\-]+) (\S+) .+ Agent rpc_loop - iteration:([0-9]+) "
                "completed..+Elapsed:([0-9.]+).+")
        self.searchobj.add_search_term(SearchDef(expr, tag="rpc-loop-end",
                                                 hint="Agent rpc_loop"),
                                       self.data_source)

    def process_rpc_loop_results(self, results):
        """Process the search results and display longest running rpc_loops
        with stats.
        """
        rpc_loops = {}
        stats = {"min": 0,
                 "max": 0,
                 "stdev": 0,
                 "avg": 0,
                 "samples": []}

        for result in results.find_by_tag("rpc-loop-end"):
            day = result.get(1)
            secs = result.get(2)
            iteration = int(result.get(3))
            duration = float(result.get(4))
            # iteration ids get reset when agent is restarted so need to do
            # this for it to be unique.
            iteration_key = "{}_{}".format(os.path.basename(result.source),
                                           iteration)
            end = "{} {}".format(day, secs)
            end = datetime.strptime(end, "%Y-%m-%d %H:%M:%S.%f")
            rpc_loops[iteration_key] = {"end": end,
                                        "duration": duration}

        for result in results.find_by_tag("rpc-loop-start"):
            day = result.get(1)
            secs = result.get(2)
            iteration = int(result.get(3))
            start = "{} {}".format(day, secs)
            start = datetime.strptime(start, "%Y-%m-%d %H:%M:%S.%f")
            iteration_key = "{}_{}".format(os.path.basename(result.source),
                                           iteration)
            if iteration_key in rpc_loops:
                stats['samples'].append(rpc_loops[iteration_key]["duration"])
                rpc_loops[iteration_key]["start"] = start

        if not rpc_loops:
            return

        count = 0
        top_n = {}
        top_n_sorted = {}

        for k, v in sorted(rpc_loops.items(),
                           key=lambda x: x[1].get("duration", 0),
                           reverse=True):
            # skip unterminated entries (e.g. on file wraparound)
            if "start" not in v:
                continue

            if count >= self.MAX_RESULTS:
                break

            count += 1
            top_n[k] = v

        for k, v in sorted(top_n.items(), key=lambda x: x[1]["start"],
                           reverse=True):
            iteration = int(k.partition('_')[2])
            top_n_sorted[iteration] = {"start": v["start"],
                                       "end": v["end"],
                                       "duration": v["duration"]}

        stats['min'] = round(min(stats['samples']), 2)
        stats['max'] = round(max(stats['samples']), 2)
        stats['stdev'] = round(statistics.pstdev(stats['samples']), 2)
        stats['avg'] = round(statistics.mean(stats['samples']), 2)
        num_samples = len(stats['samples'])
        stats['samples'] = num_samples

        self.ovs_agent_info["rpc-loop"] = {"top": top_n_sorted,
                                           "stats": stats}

    def get_router_update_stats(self, results):
        router_updates = {}
        stats = {"min": 0,
                 "max": 0,
                 "stdev": 0,
                 "avg": 0,
                 "samples": []}

        event_seq_ids = {}
        for result in results.find_by_tag("router-update-finish"):
            day = result.get(1)
            secs = result.get(2)
            router = result.get(3)
            update_id = result.get(4)
            etime = float(result.get(5))
            end = "{} {}".format(day, secs)
            end = datetime.strptime(end, "%Y-%m-%d %H:%M:%S.%f")

            # router may have many updates over time across many files so we
            # need to have a way to make them unique.
            key = "{}_{}".format(os.path.basename(result.source), update_id)
            if key not in event_seq_ids:
                event_seq_ids[key] = 0
            else:
                event_seq_ids[key] += 1

            event_key = "{}_{}".format(key, event_seq_ids[key])
            while event_key in router_updates:
                event_seq_ids[key] += 1
                event_key = "{}_{}".format(key, event_seq_ids[key])

            router_updates[event_key] = {"end": end, "router": router,
                                         "etime": etime}

        event_seq_ids2 = {}
        for result in results.find_by_tag("router-update-start"):
            day = result.get(1)
            secs = result.get(2)
            router = result.get(3)
            update_id = result.get(4)
            start = "{} {}".format(day, secs)
            start = datetime.strptime(start, "%Y-%m-%d %H:%M:%S.%f")

            key = "{}_{}".format(os.path.basename(result.source), update_id)
            if key not in event_seq_ids:
                continue

            if key not in event_seq_ids2:
                event_seq_ids2[key] = 0
            else:
                event_seq_ids2[key] += 1

            event_key = "{}_{}".format(key, event_seq_ids2[key])
            if event_key in router_updates:
                etime = router_updates[event_key]["etime"]
                router_updates[event_key]["duration"] = etime
                stats['samples'].append(etime)
                router_updates[event_key]["start"] = start

        if not stats['samples']:
            return

        count = 0
        top_n = {}
        top_n_sorted = {}

        for k, v in sorted(router_updates.items(),
                           key=lambda x: x[1].get("duration", 0),
                           reverse=True):
            # skip unterminated entries (e.g. on file wraparound)
            if "start" not in v:
                continue

            if count >= self.MAX_RESULTS:
                break

            count += 1
            top_n[k] = v

        for k, v in sorted(top_n.items(), key=lambda x: x[1]["start"],
                           reverse=True):
            top_n_sorted[v["router"]] = {"start": v["start"],
                                         "end": v["end"],
                                         "duration": v["duration"]}

        stats['min'] = round(min(stats['samples']), 2)
        stats['max'] = round(max(stats['samples']), 2)
        stats['stdev'] = round(statistics.pstdev(stats['samples']), 2)
        stats['avg'] = round(statistics.mean(stats['samples']), 2)
        num_samples = len(stats['samples'])
        stats['samples'] = num_samples

        self.l3_agent_info["router-updates"] = {"top": top_n_sorted,
                                                "stats": stats}

    def get_router_spawn_stats(self, results):
        spawn_events = {}
        stats = {"min": 0,
                 "max": 0,
                 "stdev": 0,
                 "avg": 0,
                 "samples": []}

        event_seq_ids = {}
        for result in results.find_by_tag("router-spawn2"):
            day = result.get(1)
            secs = result.get(2)
            router = result.get(3)
            end = "{} {}".format(day, secs)
            end = datetime.strptime(end, "%Y-%m-%d %H:%M:%S.%f")

            # router may have many updates over time across many files so we
            # need to have a way to make them unique.
            key = "{}_{}".format(os.path.basename(result.source), router)
            if key not in event_seq_ids:
                event_seq_ids[key] = 0
            else:
                event_seq_ids[key] += 1

            event_key = "{}_{}".format(key, event_seq_ids[key])
            while event_key in spawn_events:
                event_seq_ids[key] += 1
                event_key = "{}_{}".format(key, event_seq_ids[key])

            spawn_events[event_key] = {"end": end}

        event_seq_ids2 = {}
        for result in results.find_by_tag("router-spawn1"):
            day = result.get(1)
            secs = result.get(2)
            router = result.get(3)
            start = "{} {}".format(day, secs)
            start = datetime.strptime(start, "%Y-%m-%d %H:%M:%S.%f")

            key = "{}_{}".format(os.path.basename(result.source), router)
            if key not in event_seq_ids:
                continue

            if key not in event_seq_ids2:
                event_seq_ids2[key] = 0
            else:
                event_seq_ids2[key] += 1

            event_key = "{}_{}".format(key, event_seq_ids2[key])
            if event_key in spawn_events:
                etime = spawn_events[event_key]["end"] - start
                if etime.total_seconds() < 0:
                    continue

                spawn_events[event_key]["start"] = start
                spawn_events[event_key]["duration"] = etime.total_seconds()
                stats['samples'].append(etime.total_seconds())

        if not stats['samples']:
            return

        count = 0
        top_n = {}
        top_n_sorted = {}

        for k, v in sorted(spawn_events.items(),
                           key=lambda x: x[1].get("duration", 0),
                           reverse=True):
            # skip unterminated entries (e.g. on file wraparound)
            if "start" not in v:
                continue

            if count >= self.MAX_RESULTS:
                break

            count += 1
            top_n[k] = v

        for k, v in sorted(top_n.items(), key=lambda x: x[1]["start"],
                           reverse=True):
            router = k.rpartition('_')[0]
            router = router.partition('_')[2]
            top_n_sorted[router] = {"start": v["start"],
                                    "end": v["end"],
                                    "duration": v["duration"]}

        stats['min'] = round(min(stats['samples']), 2)
        stats['max'] = round(max(stats['samples']), 2)
        stats['stdev'] = round(statistics.pstdev(stats['samples']), 2)
        stats['avg'] = round(statistics.mean(stats['samples']), 2)
        num_samples = len(stats['samples'])
        stats['samples'] = num_samples

        self.l3_agent_info["router-spawn-events"] = {"top": top_n_sorted,
                                                     "stats": stats}

    def add_router_event_search_terms(self):
        logs_path = AGENT_LOG_PATHS["neutron"]
        if constants.USE_ALL_LOGS:
            data_source = os.path.join(constants.DATA_ROOT, logs_path,
                                       'neutron-l3-agent.log*')
        else:
            data_source = os.path.join(constants.DATA_ROOT, logs_path,
                                       'neutron-l3-agent.log')

        # router updates
        expr = (r"^([0-9-]+) (\S+) .+ Starting router update for "
                "([0-9a-z-]+), .+ update_id ([0-9a-z-]+). .+")
        self.searchobj.add_search_term(SearchDef(expr,
                                                 tag="router-update-start",
                                                 hint="router update"),
                                       data_source)

        expr = (r"^([0-9-]+) (\S+) .+ Finished a router update for "
                "([0-9a-z-]+), update_id ([0-9a-z-]+). Time elapsed: "
                "([0-9.]+)")
        self.searchobj.add_search_term(SearchDef(expr,
                                                 tag="router-update-finish",
                                                 hint="router update"),
                                       data_source)

        # router state_change_monitor + keepalived spawn
        expr = (r"^([0-9-]+) (\S+) .+ Router ([0-9a-z-]+) .+ "
                "spawn_state_change_monitor")
        self.searchobj.add_search_term(SearchDef(expr,
                                                 tag="router-spawn1",
                                                 hint="spawn_state_change"),
                                       data_source)

        expr = (r"^([0-9-]+) (\S+) .+ Keepalived spawned with config "
                "/var/lib/neutron/ha_confs/([0-9a-z-]+)/keepalived.conf .+")
        self.searchobj.add_search_term(SearchDef(expr,
                                                 tag="router-spawn2",
                                                 hint="Keepalived"),
                                       data_source)

    def process_router_event_results(self, results):
        self.get_router_spawn_stats(results)
        self.get_router_update_stats(results)


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

        # The following must be ERROR log level
        self.agent_exceptions = {"cinder": [] + agent_exceptions_common,
                                 "glance": [] + agent_exceptions_common,
                                 "heat": [] + agent_exceptions_common,
                                 "keystone": [] + agent_exceptions_common,
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
            for exc_msg in self.agent_exceptions[service]:
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
