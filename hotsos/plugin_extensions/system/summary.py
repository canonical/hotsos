import re

from hotsos.core.host_helpers import CLIHelper, UptimeHelper
from hotsos.core.plugins.system import SystemChecks
from hotsos.core.plugintools import summary_entry


class SystemSummary(SystemChecks):
    """ Implementation of System summary. """
    summary_part_index = 0

    @summary_entry('hostname', 0)
    def summary_hostname(self):
        return self.hostname

    @summary_entry('os', 1)
    def summary_os(self):
        return self.os_release_name or None

    @summary_entry('num-cpus', 2)
    def summary_num_cpus(self):
        return self.num_cpus or None

    @staticmethod
    @summary_entry('load', 3)
    def summary_load():
        return UptimeHelper().loadavg or None

    @summary_entry('virtualisation', 4)
    def summary_virtualisation(self):
        return self.virtualisation_type or None

    @staticmethod
    @summary_entry('rootfs', 5)
    def summary_rootfs():
        df_output = CLIHelper().df()
        if df_output:
            for line in df_output:
                ret = re.compile(r"(.+\/$)").match(line)
                if ret:
                    return ret[1]

        return None

    @summary_entry('unattended-upgrades', 6)
    def summary_unattended_upgrades(self):
        if self.unattended_upgrades_enabled:
            return "ENABLED"
        return "disabled"

    @summary_entry('date', 7)
    def summary_date(self):
        return self.date

    @summary_entry('ubuntu-pro', 8)
    def summary_ubuntu_pro(self):
        return self.ubuntu_pro_status

    @summary_entry('uptime', 9)
    def summary_uptime(self):
        return self.uptime
