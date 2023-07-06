from hotsos.core.plugins.vault import VaultChecksBase
from hotsos.core.plugintools import summary_entry_offset as idx


class VaultSummary(VaultChecksBase):

    @idx(0)
    def __summary_services(self):
        if self.systemd.services:
            return self.systemd.summary
        if self.pebble.services:
            return self.pebble.summary

    @idx(1)
    def __summary_snaps(self):
        if self.snaps.core:
            return self.snaps.all_formatted
