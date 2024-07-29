from hotsos.core.plugins.pacemaker import PacemakerChecks
from hotsos.core.plugintools import (
    summary_entry,
    get_min_available_entry_index,
)


class PacemakerSummary(PacemakerChecks):
    """ Implementation of Pacemaker summary. """
    summary_part_index = 0

    # REMINDER: common entries are implemented in the SummaryBase base class
    #           and only application plugin specific customisations are
    #           implemented here. We use the get_min_available_entry_index() to
    #           ensure that additional entries don't clobber existing ones but
    #           conversely can also replace them by re-using their indices.

    @summary_entry('nodes', get_min_available_entry_index())
    def summary_nodes(self):
        nodes = {}
        if self.online_nodes:
            nodes["online"] = self.online_nodes
        if self.offline_nodes:
            nodes["offline"] = self.offline_nodes

        return nodes or None
