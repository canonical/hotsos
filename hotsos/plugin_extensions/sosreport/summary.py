from hotsos.core.plugins.sosreport import SOSReportChecks
from hotsos.core.plugintools import (
    summary_entry,
    get_min_available_entry_index,
)


class SOSReportSummary(SOSReportChecks):
    """ Implementation of SOSReport summary. """
    summary_part_index = 0

    # REMINDER: common entries are implemented in the SummaryBase base class
    #           and only application plugin specific customisations are
    #           implemented here. We use the get_min_available_entry_index() to
    #           ensure that additional entries don't clobber existing ones but
    #           conversely can also replace them by re-using their indices.

    @summary_entry('plugin-timeouts', get_min_available_entry_index())
    def summary_plugin_timeouts(self):
        if self.timed_out_plugins:
            return self.timed_out_plugins

        return None
