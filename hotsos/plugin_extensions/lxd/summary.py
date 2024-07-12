from hotsos.core.plugins.lxd import LXD, LXDChecks
from hotsos.core.plugintools import summary_entry


class LXDSummary(LXDChecks):
    """ Implementation of LXD summary. """
    summary_part_index = 0

    @summary_entry('services', 0)
    def summary_services(self):
        if self.systemd.services:
            return self.systemd.summary

        return None

    @summary_entry('snaps', 1)
    def summary_snaps(self):
        if self.snaps:
            return self.snaps.all_formatted

        return None

    @summary_entry('dpkg', 2)
    def summary_dpkg(self):
        if self.apt:
            return self.apt.all_formatted

        return None

    @staticmethod
    @summary_entry('instances', 3)
    def summary_instances():
        return LXD().instances or None
