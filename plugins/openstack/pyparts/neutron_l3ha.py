import os
import re

from core.log import log
from core import constants
from core.cli_helpers import CLIHelper
from core.checks import CallbackHelper
from core.issues import (
    issue_types,
    issue_utils,
)
from core.plugins.openstack import (
    NEUTRON_HA_PATH,
    OpenstackEventChecksBase,
)

VRRP_TRANSITION_WARN_THRESHOLD = 8
YAML_PRIORITY = 8
EVENTCALLBACKS = CallbackHelper()


class NeutronL3HAChecks(OpenstackEventChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, callback_helper=EVENTCALLBACKS,
                         yaml_defs_group='neutron-router-checks',
                         **kwargs)
        self.vr_id_to_router = {}
        self.cli = CLIHelper()

    @property
    def output(self):
        if self._output:
            return {"neutron-l3ha": self._output}

    def get_neutron_ha_info(self):
        ha_state_path = os.path.join(constants.DATA_ROOT, NEUTRON_HA_PATH)
        if not os.path.exists(ha_state_path):
            return

        router_states = {}
        for entry in os.listdir(ha_state_path):
            entry = os.path.join(ha_state_path, entry)
            if os.path.isdir(entry):
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
                                expr = r".+ virtual_router_id (\d+)"
                                ret = re.compile(expr).search(line)
                                if ret:
                                    vr_id = ret.group(1)
                                    self.vr_id_to_router[vr_id] = router

        if router_states:
            self._output["agent"] = router_states

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
        self.get_neutron_ha_info()
        transitions = {}
        for r in event.results:
            ts_date = r.get(1)
            vr_id = r.get(2)
            router = self.vr_id_to_router.get(vr_id)
            if not router:
                log.debug("no router found with vr_id %s", vr_id)
                continue

            if router not in transitions:
                transitions[router] = {ts_date: 1}
            elif ts_date in transitions[router]:
                transitions[router][ts_date] += 1
            else:
                transitions[router][ts_date] = 1

        if transitions:
            self.check_vrrp_transitions(transitions)
            return {'transitions': transitions}, 'keepalived'
