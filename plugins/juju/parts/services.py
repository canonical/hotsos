#!/usr/bin/python3
import re
import os

from common import (
    constants,
    cli_helpers,
    plugin_yaml,
)
from common.issue_types import JujuWarning
from common.issues_utils import add_issue
from juju_common import (
    JUJU_LOG_PATH,
    JujuChecksBase,
)

JUJU_MACHINE_INFO = {"machines": {}}


class JujuMachineChecks(JujuChecksBase):

    def get_machine_info(self):
        ps_machines = set()
        log_machines = set()
        machines_running = set()
        machines_stopped = set()

        if not os.path.exists(JUJU_LOG_PATH):
            return

        for line in cli_helpers.get_ps():
            if "machine-" in line:
                ret = re.compile(r".+machine-([0-9]+).*").match(line)
                if ret:
                    ps_machines.add(ret[1])

        for f in os.listdir(JUJU_LOG_PATH):
            ret = re.compile(r"machine-([0-9]+)\.log.*").match(f)
            if ret:
                log_machines.add(ret[1])

        combined_machines = ps_machines.union(log_machines)
        for machine in combined_machines:
            conf_path = ("var/lib/juju/agents/machine-{}/agent.conf".
                         format(machine))
            agent_conf = os.path.join(constants.DATA_ROOT, conf_path)
            version = "unknown"
            if os.path.exists(agent_conf):
                for line in open(agent_conf).readlines():
                    ret = re.compile(r"upgradedToVersion:\s+(.+)").match(line)
                    if ret:
                        version = ret[1]

            if machine in ps_machines:
                machines_running.add("{} (version={})".format(machine,
                                                              version))
            else:
                machines_stopped.add(machine)

        if machines_running:
            JUJU_MACHINE_INFO["machines"]["running"] = list(machines_running)

        if machines_stopped:
            JUJU_MACHINE_INFO["machines"]["stopped"] = list(machines_stopped)

        if not machines_running and (machines_stopped or
                                     self.get_local_running_units):
            msg = ("there is no Juju machined running on this host but it "
                   "seems there should be")
            add_issue(JujuWarning(msg))

    def __call__(self):
        self.get_machine_info()


def get_machine_checks():
    return JujuMachineChecks()


if __name__ == "__main__":
    get_machine_checks()()
    if JUJU_MACHINE_INFO["machines"]:
        plugin_yaml.save_part(JUJU_MACHINE_INFO, priority=0)
