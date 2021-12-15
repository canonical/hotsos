import re

from core.cli_helpers import CLIHelper
from core.issues import (
    issue_types,
    issue_utils,
)
from core.plugins.juju import JujuChecksBase

YAML_PRIORITY = 1


class JujuMachineChecks(JujuChecksBase):

    def get_machine_info(self):
        if not self.machine:
            return

        machine_info = {'version': self.machine.version,
                        'machine': self.machine.id}

        agent_running = False
        for line in CLIHelper().ps():
            if 'jujud' in line:
                expr = r".+(jujud-machine-\d+(?:-lxd-\d+)?)"
                ret = re.compile(expr).match(line)
                if ret:
                    if ret.group(1) == self.machine.agent_service_name:
                        agent_running = True
                        break

        if not agent_running:
            msg = ("no Juju machine agent found running on this host but it "
                   "seems there should be.")
            issue_utils.add_issue(issue_types.JujuWarning(msg))

        if machine_info["machine"]:
            self._output.update(machine_info)

    def __call__(self):
        self.get_machine_info()
