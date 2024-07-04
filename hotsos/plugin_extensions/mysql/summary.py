from hotsos.core.plugins.mysql import MySQLChecksBase


class MySQLSummary(MySQLChecksBase):
    summary_part_index = 0

    def __0_summary_services(self):
        if self.systemd.services:
            return self.systemd.summary
        if self.pebble.services:
            return self.pebble.summary

        return None

    def __1_summary_dpkg(self):
        if self.apt_info.core:
            return self.apt_info.all_formatted

        return None
