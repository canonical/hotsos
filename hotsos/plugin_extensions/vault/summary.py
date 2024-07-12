from hotsos.core.plugins.vault import VaultChecks
from hotsos.core.plugintools import summary_entry


class VaultSummary(VaultChecks):
    """ Implementation of Vault summary. """
    summary_part_index = 0

    @summary_entry('services', 0)
    def summary_services(self):
        if self.systemd.services:
            return self.systemd.summary
        if self.pebble.services:
            return self.pebble.summary

        return None

    @summary_entry('snaps', 1)
    def summary_snaps(self):
        if self.snaps.core:
            return self.snaps.all_formatted

        return None
