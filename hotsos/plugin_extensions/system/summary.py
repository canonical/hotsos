import re

from hotsos.core.host_helpers import CLIHelper, UptimeHelper
from hotsos.core.plugins.system import SystemChecksBase


class SystemSummary(SystemChecksBase):
    summary_part_index = 0

    def __0_summary_hostname(self):
        return self.hostname

    def __1_summary_os(self):
        return self.os_release_name or None

    def __2_summary_num_cpus(self):
        return self.num_cpus or None

    @staticmethod
    def __3_summary_load():
        return UptimeHelper().loadavg or None

    def __4_summary_virtualisation(self):
        return self.virtualisation_type or None

    @staticmethod
    def __5_summary_rootfs():
        df_output = CLIHelper().df()
        if df_output:
            for line in df_output:
                ret = re.compile(r"(.+\/$)").match(line)
                if ret:
                    return ret[1]

        return None

    def __6_summary_unattended_upgrades(self):
        if self.unattended_upgrades_enabled:
            return "ENABLED"
        return "disabled"

    def __7_summary_date(self):
        return self.date

    def __8_summary_ubuntu_pro(self):
        return self.ubuntu_pro_status

    def __9_summary_uptime(self):
        return self.uptime
