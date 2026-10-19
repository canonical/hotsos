""" Plugin for analyzing un-used disk space and un-used disks. """
from hotsos.core.plugins.storage.disks import DiskChecks
from hotsos.core.plugintools import get_min_available_entry_index
from hotsos.core.plugintools import summary_entry


class DisksSummary(DiskChecks):
    """Analyze un-used disk space."""
    summary_part_index = 4

    @summary_entry('disks', index=get_min_available_entry_index())
    def disks_summary(self):
        """Return un-used disks information."""
        summary = {}
        if self.unused_disks:
            summary['unused-disks'] = self.unused_disks
        if self.empty_partitions:
            summary['empty-partitions'] = self.empty_partitions
        if self.unallocated_disks:
            summary['unallocated-disks'] = self.unallocated_disks

        return summary
