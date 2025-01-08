from hotsos.core.plugins.pacemaker import PacemakerChecks
from hotsos.core.plugintools import (
    summary_entry,
    get_min_available_entry_index,
)


class PacemakerSummary(PacemakerChecks):
    """ Implementation of Pacemaker summary. """
    summary_part_index = 0

    # REMINDER: Common entries are implemented in
    #           plugintools.ApplicationSummaryBase. Only customisations are
    #           implemented here. See
    #           plugintools.get_min_available_entry_index() for an explanation
    #           on how entry indices are managed.

    @summary_entry('nodes', get_min_available_entry_index())
    def summary_nodes(self):
        nodes = {}
        if self.online_nodes:
            nodes["online"] = self.online_nodes
        if self.offline_nodes:
            nodes["offline"] = self.offline_nodes

        return nodes or None
