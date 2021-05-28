#!/usr/bin/python3
import os
import re

from common import (
    constants,
    cli_helpers,
    issue_types,
    issues_utils,
    plugin_yaml,
)
from common.searchtools import (
    SearchDef,
    FileSearcher,
)
from common.utils import mktemp_dump
from openstack_common import (
    NEUTRON_HA_PATH,
)

L3HA_CHECKS = {}
ROUTER_VR_IDS = {}
VRRP_TRANSITION_WARN_THRESHOLD = 8


class NeutronL3HAChecks(object):

    def __init__(self):
        self.searcher = FileSearcher()
        self.f_journalctl = None
        self.router_vrrp_pids = {}

    def __del__(self):
        if self.f_journalctl and os.path.exists(self.f_journalctl):
            os.unlink(self.f_journalctl)

    def _get_journalctl_l3_agent(self):
        if not constants.USE_ALL_LOGS:
            date = cli_helpers.get_date(format="--iso-8601").rstrip()
        else:
            date = None

        out = cli_helpers.get_journalctl(unit="neutron-l3-agent", date=date)
        self.f_journalctl = mktemp_dump(''.join(out))

    def get_neutron_ha_info(self):
        ha_state_path = os.path.join(constants.DATA_ROOT, NEUTRON_HA_PATH)
        if not os.path.exists(ha_state_path):
            return

        router_states = {}
        for entry in os.listdir(ha_state_path):
            entry = os.path.join(ha_state_path, entry)
            if os.path.isdir(entry):
                pid_path = "{}{}".format(entry, ".pid.keepalived-vrrp")
                keepalived_conf_path = os.path.join(entry, "keepalived.conf")
                state_path = os.path.join(entry, "state")
                if os.path.exists(state_path):
                    with open(state_path) as fd:
                        router = os.path.basename(entry)
                        state = fd.read().strip()
                        if state in router_states:
                            router_states[state].append(router)
                        else:
                            router_states[state] = [router]

                    if os.path.isfile(keepalived_conf_path):
                        with open(keepalived_conf_path) as fd:
                            for line in fd:
                                expr = ".+ virtual_router_id ([0-9]+)"
                                ret = re.compile(expr).search(line)
                                if ret:
                                    ROUTER_VR_IDS[router] = ret.group(1)

                    if os.path.isfile(pid_path):
                        with open(pid_path) as fd:
                            pid = fd.read().strip()
                            self.router_vrrp_pids[router] = pid

        if router_states:
            L3HA_CHECKS["agent"] = router_states

    def get_vrrp_transitions(self):
        """
        List routers that have had a vrrp state transition along with the
        number of transitions. Excludes routers that have not had any change of
        state.
        """
        if not self.router_vrrp_pids:
            return

        self._get_journalctl_l3_agent()
        transitions = {}
        for router in self.router_vrrp_pids:
            vr_id = ROUTER_VR_IDS[router]
            expr = (r"^([0-9-]+)T\S+ \S+ Keepalived_vrrp"
                    r"\[([0-9]+)\]: VRRP_Instance\(VR_{}\) .+ (\S+) "
                    "STATE.*".format(vr_id))
            d = SearchDef(expr, tag=router)
            self.searcher.add_search_term(d, self.f_journalctl)

        results = self.searcher.search()
        for router in self.router_vrrp_pids:
            t_count = len(results.find_by_tag(router))
            if not t_count:
                continue

            for r in results.find_by_tag(router):
                ts_date = r.get(1)
                if router not in transitions:
                    transitions[router] = {}

                if ts_date in transitions[router]:
                    transitions[router][ts_date] += 1
                else:
                    transitions[router][ts_date] = 1

        if transitions:
            L3HA_CHECKS["keepalived"] = {"transitions": transitions}

    def check_vrrp_transitions(self):
        if "transitions" not in L3HA_CHECKS.get("keepalived", {}):
            return

        max_transitions = 0
        warn_count = 0
        threshold = VRRP_TRANSITION_WARN_THRESHOLD
        for router in L3HA_CHECKS["keepalived"]["transitions"]:
            r = L3HA_CHECKS["keepalived"]["transitions"][router]
            transitions = sum([t for d, t in r.items()])
            if transitions > threshold:
                max_transitions = max(transitions, max_transitions)
                warn_count += 1

        if warn_count:
            msg = ("{} router(s) have had more than {} vrrp transitions "
                   "(max={}) in the last 24 hours".format(warn_count,
                                                          threshold,
                                                          max_transitions))
            issues_utils.add_issue(issue_types.NeutronL3HAWarning(msg))

    def __call__(self):
        self.get_neutron_ha_info()
        self.get_vrrp_transitions()

        # there will likely be a large number of transitions if we look across
        # all time so dont run this check.
        if not constants.USE_ALL_LOGS:
            self.check_vrrp_transitions()


def run_checks():
    return NeutronL3HAChecks()


if __name__ == "__main__":
    run_checks()()
    if L3HA_CHECKS:
        plugin_yaml.save_part({"neutron-l3ha": L3HA_CHECKS}, priority=8)
