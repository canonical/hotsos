from hotsos.core.plugins.pacemaker import PacemakerChecks
from hotsos.core.plugintools import summary_entry


class PacemakerSummary(PacemakerChecks):
    """ Implementation of Pacemaker summary. """
    summary_part_index = 0

    @summary_entry('services', 0)
    def summary_services(self):
        if self.systemd.services:
            return self.systemd.summary

        return None

    @summary_entry('dpkg', 1)
    def summary_dpkg(self):
        return self.apt.all_formatted or None

    @summary_entry('nodes', 2)
    def summary_nodes(self):
        nodes = {}
        if self.online_nodes:
            nodes["online"] = self.online_nodes
        if self.offline_nodes:
            nodes["offline"] = self.offline_nodes

        return nodes or None
