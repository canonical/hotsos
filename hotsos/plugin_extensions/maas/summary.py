from hotsos.core.plugintools import summary_entry_offset as idx
from hotsos.core.plugins.maas import MAASChecksBase


class MAASSummary(MAASChecksBase):

    @idx(0)
    def __summary_services(self):
        if self.systemd.services:
            return self.systemd.summary

    @idx(1)
    def __summary_dpkg(self):
        if self.apt.core:
            return self.apt.all_formatted

    @idx(2)
    def __summary_snaps(self):
        if self.snaps.core:
            return self.snaps.all_formatted
