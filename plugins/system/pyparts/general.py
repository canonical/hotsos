import re
import os

from core import (
    constants,
    plugintools,
)
from core.cli_helpers import CLIHelper


YAML_PRIORITY = 0


class SystemGeneral(plugintools.PluginPartBase):

    @property
    def unattended_upgrades_enabled(self):
        apt_config_dump = CLIHelper().apt_config_dump()
        if not apt_config_dump:
            return

        for line in apt_config_dump:
            ret = re.compile(r"^APT::Periodic::Unattended-Upgrade\s+"
                             "\"([0-9]+)\";").match(line)
            if ret:
                if int(ret[1]) == 0:
                    return False
                else:
                    return True

        return False

    def get_system_info(self):
        hostname = CLIHelper().hostname()
        if not hostname:
            hostname = "unavailable"

        self._output["hostname"] = hostname

        data_source = os.path.join(constants.DATA_ROOT, "etc/lsb-release")
        if os.path.exists(data_source):
            for line in open(data_source).read().split():
                ret = re.compile(r"^DISTRIB_CODENAME=(.+)").match(line)
                if ret:
                    self._output["os"] = "ubuntu {}".format(ret[1])
                    break

        lscpu_output = CLIHelper().lscpu()
        if lscpu_output:
            for line in lscpu_output:
                ret = re.compile(r"^CPU\(s\):\s+([0-9]+)\s*.*").match(line)
                if ret:
                    self._output["num-cpus"] = int(ret[1])
                    break

        uptime = CLIHelper().uptime()
        if uptime:
            ret = re.compile(r".+load average:\s+(.+)").match(uptime)
            if ret:
                self._output["load"] = ret[1]

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
