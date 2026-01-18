
"""
Plugin for analyzing disk health using smartctl output.
"""

import re

from hotsos.core.plugintools import summary_entry
from hotsos.core.ycheck.scenarios import YScenarioChecker
from hotsos.core.log import log
from hotsos.core.ycheck.common import GlobalSearcher


class SmartctlSummary(YScenarioChecker):
    """Analyze disk health using smartctl output."""
    def __init__(self, global_searcher=None):
        if global_searcher is None:
            global_searcher = GlobalSearcher()
        super().__init__(global_searcher)

    @summary_entry('disk_health')
    def disk_health(self):
        """Summarize disk health and error counters from smartctl output."""
        smartctl_path = 'sos_commands/smartctl/smartctl_-a_*'
        results = self._search_sosreport(smartctl_path)
        if not results:
            log.debug('No smartctl output found in sosreport')
            return None

        error_counters = [
            'Reallocated_Sector_Ct',
            'Current_Pending_Sector',
            'Offline_Uncorrectable',
            'Reported_Uncorrect',
            'UDMA_CRC_Error_Count',
            'Seek_Error_Rate',
            'Spin_Retry_Count',
            'End-to-End_Error',
            'Command_Timeout',
            'Hardware_ECC_Recovered',
            'Raw_Read_Error_Rate',
        ]
        abnormal_disks = {}
        for path, content in results.items():
            disk_issues = {}
            # Look for common failure indicators
            if re.search(
                r'FAILED|SMART overall-health self-assessment test result: '
                r'FAILED',
                content
            ):
                disk_issues['health_status'] = 'FAILED'
            # Check error counters
            for counter in error_counters:
                # Match lines like:
                #   5 Reallocated_Sector_Ct   0x0033   100   100   036
                #   Pre-fail  Always - 0
                m = re.search(
                    rf'{counter}\s+\S+\s+\d+\s+\d+\s+\d+\s+\S+\s+'
                    rf'\S+\s+\S+\s+(\d+)',
                    content
                )
                if m:
                    value = int(m.group(1))
                    if value > 0:
                        disk_issues[counter] = value
            if disk_issues:
                abnormal_disks[path] = disk_issues

        result = {}
        if abnormal_disks:
            result['abnormal_disks'] = abnormal_disks
            result['message'] = (
                'Some disks reported SMART health failures or abnormal error '
                'counters.'
            )
        else:
            result['message'] = (
                'No SMART health failures or abnormal error counters '
                'detected.'
            )
        return result

    @staticmethod
    def _search_sosreport(_pattern):
        # Placeholder: Implement actual sosreport file search logic
        # Should return a dict {path: content}
        return {}
