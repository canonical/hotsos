from hotsos.core.plugins.lxd import LXD, LXDChecksBase
from hotsos.core.plugintools import summary_entry_offset as idx


class LXDSummary(LXDChecksBase):

    @idx(0)
    def __summary_services(self):
        if self.systemd.services:
            return self.systemd.summary

    @idx(1)
    def __summary_snaps(self):
        if self.snaps:
            return self.snaps.all_formatted

    @idx(2)
    def __summary_dpkg(self):
        if self.apt:
            return self.apt.all

    @idx(3)
    def __summary_instances(self):
        instances = LXD().instances
        if instances:
            return instances
