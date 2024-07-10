from hotsos.core.plugins.vault import VaultChecks


class VaultSummary(VaultChecks):
    """ Implementation of Vault summary. """
    summary_part_index = 0

    def __0_summary_services(self):
        if self.systemd.services:
            return self.systemd.summary
        if self.pebble.services:
            return self.pebble.summary

        return None

    def __1_summary_snaps(self):
        if self.snaps.core:
            return self.snaps.all_formatted

        return None
