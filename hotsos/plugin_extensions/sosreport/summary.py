from hotsos.core.plugins.sosreport import SOSReportChecks
from hotsos.core.plugintools import summary_entry


class SOSReportSummary(SOSReportChecks):
    """ Implementation of SOSReport summary. """
    summary_part_index = 0

    @summary_entry('version', 0)
    def summary_version(self):
        if self.version is not None:
            return self.version

        return None

    @summary_entry('dpkg', 1)
    def summary_dpkg(self):
        if self.apt.core:
            return self.apt.all_formatted

        return None

    @summary_entry('plugin-timeouts', 2)
    def summary_plugin_timeouts(self):
        if self.timed_out_plugins:
            return self.timed_out_plugins

        return None
