from hotsos.core.plugins.lxd import LXD, LXDChecks
from hotsos.core.plugintools import (
    summary_entry,
    get_min_available_entry_index,
)


class LXDSummary(LXDChecks):
    """ Implementation of LXD summary. """
    summary_part_index = 0

    # REMINDER: common entries are implemented in the SummaryBase base class
    #           and only application plugin specific customisations are
    #           implemented here. We use the get_min_available_entry_index() to
    #           ensure that additional entries don't clobber existing ones but
    #           conversely can also replace them by re-using their indices.

    @staticmethod
    @summary_entry('instances', get_min_available_entry_index())
    def summary_instances():
        return LXD().instances or None
