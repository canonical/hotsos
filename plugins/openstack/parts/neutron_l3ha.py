#!/usr/bin/python3
import os
import re
import tempfile

from common import (
    constants,
    helpers,
    plugin_yaml,
)
from common.searchtools import (
    SearchDef,
    FileSearcher,
)
from openstack_common import (
    NEUTRON_HA_PATH,
)

L3HA_CHECKS = {}
ROUTER_VR_IDS = {}


class NeutronL3HAChecks(object):

    def __init__(self):
        self.searcher = FileSearcher()

    def get_neutron_ha_info(self):
        ha_state_path = os.path.join(constants.DATA_ROOT, NEUTRON_HA_PATH)
        if not os.path.exists(ha_state_path):
            return

        vrrp_states = {}
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

                    with open(keepalived_conf_path) as fd:
                        for line in fd:
                            expr = ".+ virtual_router_id ([0-9]+)"
                            ret = re.compile(expr).search(line)
                            if ret:
                                ROUTER_VR_IDS[router] = ret.group(1)

                    if os.path.isfile(pid_path):
                        with open(pid_path) as fd:
                            pid = fd.read().strip()
                            vrrp_states[router] = pid

        if router_states:
            L3HA_CHECKS["agent"] = router_states

        if vrrp_states:
            L3HA_CHECKS["keepalived"] = vrrp_states

    def get_vrrp_transitions(self):
        if "keepalived" not in L3HA_CHECKS:
            return

        transitions = {}
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as ftmp:
            if not constants.USE_ALL_LOGS:
                date = helpers.get_date(format="--iso-8601").rstrip()
            else:
                date = None

            out = helpers.get_journalctl(unit="neutron-l3-agent", date=date)
            ftmp.write(''.join(out))
            ftmp.close()

            for router in L3HA_CHECKS["keepalived"]:
                vr_id = ROUTER_VR_IDS[router]
                expr = (r"^(\S+) [0-9]+ [0-9:]+ \S+ Keepalived_vrrp"
                        r"\[([0-9]+)\]: VRRP_Instance\(VR_{}\) .+ (\S+) "
                        "STATE.*".format(vr_id))
                d = SearchDef(expr, tag=router)
                self.searcher.add_search_term(d, ftmp.name)

            results = self.searcher.search()
            for router in L3HA_CHECKS["keepalived"]:
                transitions[router] = len(results.find_by_tag(router))

            os.unlink(ftmp.name)

        if transitions:
            L3HA_CHECKS["keepalived"] = {"transitions": {}}
            for k, v in sorted(transitions.items(), key=lambda x: x[1],
                               reverse=True):
                L3HA_CHECKS["keepalived"]["transitions"][k] = v

    def __call__(self):
        self.get_neutron_ha_info()
        self.get_vrrp_transitions()


def run_checks():
    return NeutronL3HAChecks()


if __name__ == "__main__":
    run_checks()()
    if L3HA_CHECKS:
        plugin_yaml.save_part({"neutron-l3ha": L3HA_CHECKS}, priority=8)
