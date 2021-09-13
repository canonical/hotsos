import re

from core.cli_helpers import CLIHelper
from core.plugins.system import SystemChecksBase

YAML_PRIORITY = 0


class SystemGeneral(SystemChecksBase):

    def get_system_info(self):
        self._output["hostname"] = self.hostname
        if self.os_release_name:
            self._output["os"] = self.os_release_name

        if self.num_cpus:
            self._output["num-cpus"] = int(self.num_cpus)

        if self.loadavg:
            self._output["load"] = self.loadavg

        if self.virtualisation_type:
            self._output["virtualisation"] = self.virtualisation_type

        df_output = CLIHelper().df()
        if df_output:
            for line in df_output:
                ret = re.compile(r"(.+\/$)").match(line)
                if ret:
                    self._output["rootfs"] = ret[1]
                    break

        if self.unattended_upgrades_enabled:
            self._output['unattended-upgrades'] = "ENABLED"
        else:
            self._output['unattended-upgrades'] = "disabled"

    def __call__(self):
        self.get_system_info()
