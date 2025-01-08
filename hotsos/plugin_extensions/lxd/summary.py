from hotsos.core.plugins.lxd import LXD, LXDChecks
from hotsos.core.plugintools import (
    summary_entry,
    get_min_available_entry_index,
)


class LXDSummary(LXDChecks):
    """ Implementation of LXD summary. """
    summary_part_index = 0

    # REMINDER: Common entries are implemented in
    #           plugintools.ApplicationSummaryBase. Only customisations are
    #           implemented here. See
    #           plugintools.get_min_available_entry_index() for an explanation
    #           on how entry indices are managed.

    @staticmethod
    @summary_entry('instances', get_min_available_entry_index())
    def summary_instances():
        return LXD().instances or None
