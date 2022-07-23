from hotsos.core.plugintools import summary_entry_offset as idx
from hotsos.core.plugins.sosreport import SOSReportChecksBase


class SOSReportSummary(SOSReportChecksBase):

    @idx(0)
    def __summary_version(self):
        if self.version is not None:
            return self.version

    @idx(1)
    def __summary_dpkg(self):
        if self.apt.core:
            return self.apt.all_formatted

    @idx(2)
    def __summary_plugin_timeouts(self):
        if self.timed_out_plugins:
            return self.timed_out_plugins
