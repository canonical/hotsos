from hotsos.core.plugins.maas import MAASChecks
from hotsos.core.plugintools import summary_entry


class MAASSummary(MAASChecks):
    """ Implementation of MAAS summary. """
    summary_part_index = 0

    @summary_entry('services', 0)
    def summary_services(self):
        if self.systemd.services:
            return self.systemd.summary

        return None

    @summary_entry('dpkg', 1)
    def summary_dpkg(self):
        if self.apt.core:
            return self.apt.all_formatted

        return None

    @summary_entry('snaps', 2)
    def summary_snaps(self):
        if self.snaps.core:
            return self.snaps.all_formatted

        return None
