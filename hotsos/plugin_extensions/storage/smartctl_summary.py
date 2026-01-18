"""
Plugin for analyzing disk health using smartctl output.
"""

import re
import os

from hotsos.core.config import HotSOSConfig
from hotsos.core.log import log
from hotsos.core.plugins.storage.smartctl import SmartctlChecks
from hotsos.core.plugintools import get_min_available_entry_index
from hotsos.core.plugintools import summary_entry


class SmartctlSummary(SmartctlChecks):
    """Analyze disk health using smartctl output."""

    summary_part_index = get_min_available_entry_index()

    @summary_entry('disk_health', index=get_min_available_entry_index())
    def disk_health(self):
        """Summarize disk health and error counters from smartctl output."""
        smartctl_dir = os.path.join(
            HotSOSConfig.data_root,
            'sos_commands',
            'smartctl',
        )
        results = self._search_sosreport(smartctl_dir)
        if not results:
            log.debug('No smartctl output found in sosreport')
            return None

        # Only include counters that are meaningful for RAW_VALUE > 0
        # Exclude counters like Seek_Error_Rate, Raw_Read_Error_Rate, and
        # Hardware_ECC_Recovered, which are not reliable for error detection
        error_counters = [
            'Reallocated_Sector_Ct',
            'Current_Pending_Sector',
            'Offline_Uncorrectable',
            'Reported_Uncorrect',
            'UDMA_CRC_Error_Count',
            'Spin_Retry_Count',
            'End-to-End_Error',
            'Command_Timeout',
        ]
        abnormal_disks = {}
        for path, content in results.items():
            disk_issues = {}
            # Only match the full health status phrase
            if re.search(
                r'SMART overall-health self-assessment test result: FAILED',
                content
            ):
                disk_issues['health_status'] = 'FAILED'
            # Match lines like (smartctl attributes format):
            # 5 Reallocated_Sector_Ct 0x0033 100 100 036 Pre-fail Always - 2
            # where columns are:
            # ID# ATTRIBUTE_NAME FLAG VALUE WORST THRESH TYPE UPDATED
            # WHEN_FAILED RAW_VALUE
            for counter in error_counters:
                # Allow for variable whitespace and capture RAW_VALUE
                # (last column)
                pattern = rf'^\s*\d+\s+{re.escape(counter)}\b.*?(\d+)\s*$'
                m = re.search(pattern, content, re.MULTILINE)
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
    def _search_sosreport(directory):
        """
        Search for and read all smartctl output files in the given directory.
        """
        results = {}
        if not os.path.isdir(directory):
            return results
        for fname in os.listdir(directory):
            fpath = os.path.join(directory, fname)
            if os.path.isfile(fpath):
                try:
                    with open(fpath, encoding='utf-8', errors='ignore') as f:
                        results[fpath] = f.read()
                except OSError as exc:
                    log.debug('Failed to read %s: %s', fpath, exc)
        return results
