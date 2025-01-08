from hotsos.core.plugins.sosreport import SOSReportChecks
from hotsos.core.plugintools import (
    summary_entry,
    get_min_available_entry_index,
)


class SOSReportSummary(SOSReportChecks):
    """ Implementation of SOSReport summary. """
    summary_part_index = 0

    # REMINDER: Common entries are implemented in
    #           plugintools.ApplicationSummaryBase. Only customisations are
    #           implemented here. See
    #           plugintools.get_min_available_entry_index() for an explanation
    #           on how entry indices are managed.

    @summary_entry('plugin-timeouts', get_min_available_entry_index())
    def summary_plugin_timeouts(self):
        if self.timed_out_plugins:
            return self.timed_out_plugins

        return None
