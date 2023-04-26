from hotsos.core.plugintools import summary_entry_offset as idx
from hotsos.core.plugins.mysql import MySQLChecksBase


class MySQLSummary(MySQLChecksBase):

    @idx(0)
    def __summary_services(self):
        if self.systemd.services:
            return self.systemd.summary
        elif self.pebble.services:
            return self.pebble.summary

    @idx(1)
    def __summary_dpkg(self):
        if self.apt_info.core:
            return self.apt_info.all_formatted
