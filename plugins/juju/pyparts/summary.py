import re

from core.plugintools import summary_entry_offset as idx
from core.cli_helpers import CLIHelper
from core.issues import (
    issue_types,
    issue_utils,
)
from core.plugins.juju import JujuServiceChecksBase

YAML_OFFSET = 0


class JujuSummary(JujuServiceChecksBase):

    def get_nonlocal_unit_info(self):
        """ These are units that may be running on the local host i.e.
        their associated jujud process is visible but inside containers.
        """
        unit_nonlocal = []
        if self.units:
            local_units = [u.name for u in self.units]
        else:
            local_units = []

        for unit in self.ps_units:
            if unit.name in local_units:
                continue

            unit_nonlocal.append(unit)

        if unit_nonlocal:
            return list(sorted([u.name for u in unit_nonlocal]))

    def _check_machine_exists(self):
        if not self.machine:
            return

        for line in CLIHelper().ps():
            if 'jujud' in line:
                expr = r".+(jujud-machine-\d+(?:-lxd-\d+)?)"
                ret = re.compile(expr).match(line)
                if ret:
                    if ret.group(1) == self.machine.agent_service_name:
                        # all good
                        return

        msg = ("no Juju machine agent found running on this host but it "
               "seems there should be.")
        issue_utils.add_issue(issue_types.JujuWarning(msg))

    @idx(0)
    def __summary_services(self):
        if self.services:
            return {'systemd': self.service_info,
                    'ps': self.process_info}

    @idx(1)
    def __summary_version(self):
        if self.machine:
            return self.machine.version

    @idx(2)
    def __summary_machine(self):
        self._check_machine_exists()
        if self.machine:
            return self.machine.id

    @idx(3)
    def __summary_charms(self):
        if self.charms:
            charms = ["{}-{}".format(c.name, c.version) for c in self.charms]
            return sorted(charms)

    @idx(4)
    def __summary_units(self):
        unit_info = {}
        if self.units:
            unit_info["local"] = sorted([u.name for u in self.units])

        non_local = self.get_nonlocal_unit_info()
        if non_local:
            unit_info['lxd'] = non_local

        if unit_info:
            return unit_info
