""" Plugin for analyzing disk health using smartctl output. """
from hotsos.core.plugins.storage.smartctl import SmartctlChecks
from hotsos.core.plugintools import get_min_available_entry_index
from hotsos.core.plugintools import summary_entry


class SmartctlSummary(SmartctlChecks):
    """Analyze disk health using smartctl output."""
    summary_part_index = 3

    @summary_entry('smartctl', index=get_min_available_entry_index())
    def smartctl_summary(self):
        summary = {}
        if self.abnormal_disks:
            summary['unhealthy-disks'] = self.abnormal_disks

        return summary
