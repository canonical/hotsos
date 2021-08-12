import re
import os

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
        machines_running = set()
        machines_stopped = set()

        if not os.path.exists(JUJU_LOG_PATH):
            return

        machine = self.machine.agent_service_name
        machine_unit = machine.partition("jujud-machine-")[2]
        for line in CLIHelper().ps():
            if "jujud-machine-" in line:
                expr = r".+jujud-machine-(\d+(?:-lxd-\d+)?).*"
                ret = re.compile(expr).match(line)
                if ret:
                    ps_machines.add("jujud-machine-{}".format(ret[1]))

        if machine in ps_machines:
            machines_running.add("{} (version={})".
                                 format(machine_unit, self.machine.version))
        else:
            machines_stopped.add(machine_unit)

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
