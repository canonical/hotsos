from hotsos.core.plugins.sosreport import SOSReportChecksBase


class SOSReportSummary(SOSReportChecksBase):
    summary_part_index = 0

    def __0_summary_version(self):
        if self.version is not None:
            return self.version

        return None

    def __1_summary_dpkg(self):
        if self.apt.core:
            return self.apt.all_formatted

        return None

    def __2_summary_plugin_timeouts(self):
        if self.timed_out_plugins:
            return self.timed_out_plugins

        return None
