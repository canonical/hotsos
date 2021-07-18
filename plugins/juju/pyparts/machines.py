import re
import os

from common import constants
from common.cli_helpers import CLIHelper
from common.issue_types import JujuWarning
from common.issues_utils import add_issue
from common.plugins.juju import (
    JUJU_LOG_PATH,
    JujuChecksBase,
)

YAML_PRIORITY = 0


class JujuMachineChecks(JujuChecksBase):

    def get_machine_info(self):
        machine_info = {"machines": {}}
        ps_machines = set()
        log_machines = set()
        machines_running = set()
        machines_stopped = set()

        if not os.path.exists(JUJU_LOG_PATH):
            return

        for line in CLIHelper().ps():
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
            machine_info["machines"]["running"] = list(machines_running)

        if machines_stopped:
            machine_info["machines"]["stopped"] = list(machines_stopped)

        if not machines_running and (machines_stopped or
                                     self._get_local_running_units):
            msg = ("there is no Juju machined running on this host but it "
                   "seems there should be")
            add_issue(JujuWarning(msg))

        if machine_info["machines"]:
            self._output.update(machine_info)

    def __call__(self):
        self.get_machine_info()
