from hotsos.core.plugins.mysql import MySQLChecks
from hotsos.core.plugintools import summary_entry


class MySQLSummary(MySQLChecks):
    """ Implementation of MySQL summary. """
    summary_part_index = 0

    @summary_entry('services', 0)
    def summary_services(self):
        if self.systemd.services:
            return self.systemd.summary
        if self.pebble.services:
            return self.pebble.summary

        return None

    @summary_entry('dpkg', 1)
    def summary_dpkg(self):
        if self.apt_info.core:
            return self.apt_info.all_formatted

        return None
