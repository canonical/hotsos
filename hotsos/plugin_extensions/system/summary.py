import re

from hotsos.core.plugintools import summary_entry_offset as idx
from hotsos.core.host_helpers import CLIHelper, UptimeHelper
from hotsos.core.plugins.system import SystemChecksBase


class SystemSummary(SystemChecksBase):

    @idx(0)
    def __summary_hostname(self):
        return self.hostname

    @idx(1)
    def __summary_os(self):
        if self.os_release_name:
            return self.os_release_name

    @idx(2)
    def __summary_num_cpus(self):
        if self.num_cpus:
            return self.num_cpus

    @idx(3)
    def __summary_load(self):
        if UptimeHelper().loadavg:
            return UptimeHelper().loadavg

    @idx(4)
    def __summary_virtualisation(self):
        if self.virtualisation_type:
            return self.virtualisation_type

    @idx(5)
    def __summary_rootfs(self):
        df_output = CLIHelper().df()
        if df_output:
            for line in df_output:
                ret = re.compile(r"(.+\/$)").match(line)
                if ret:
                    return ret[1]

    @idx(6)
    def __summary_unattended_upgrades(self):
        if self.unattended_upgrades_enabled:
            return "ENABLED"
        else:
            return "disabled"

    @idx(7)
    def __summary_date(self):
        return self.date

    @idx(8)
    def __summary_ubuntu_pro(self):
        return self.ubuntu_pro_status
