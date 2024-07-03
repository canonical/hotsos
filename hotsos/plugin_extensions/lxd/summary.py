from hotsos.core.plugins.lxd import LXD, LXDChecksBase


class LXDSummary(LXDChecksBase):
    summary_part_index = 0

    def __0_summary_services(self):
        if self.systemd.services:
            return self.systemd.summary

        return None

    def __1_summary_snaps(self):
        if self.snaps:
            return self.snaps.all_formatted

        return None

    def __2_summary_dpkg(self):
        if self.apt:
            return self.apt.all_formatted

        return None

    @staticmethod
    def __3_summary_instances():
        return LXD().instances or None
