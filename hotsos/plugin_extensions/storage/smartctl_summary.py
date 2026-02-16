""" Plugin for analyzing disk health using smartctl output. """

import re
import os

from hotsos.core.config import HotSOSConfig
from hotsos.core.log import log
from hotsos.core.plugins.storage.smartctl import SmartctlChecks
from hotsos.core.plugintools import get_min_available_entry_index
from hotsos.core.plugintools import summary_entry


class SmartctlSummary(SmartctlChecks):
    """Analyze disk health using smartctl output."""
    summary_part_index = 3

    @summary_entry('disk_health', index=get_min_available_entry_index())
    def disk_health(self):
        """ Summarize disk health from smartctl output. """

        results = {}
        for directory in ['nvme', 'ata']:
            smartctl_dir = os.path.join(
                HotSOSConfig.data_root,
                'sos_commands',
                directory,
            )
            results.update(self._search_sosreport(smartctl_dir))

        if not results:
            log.debug('No smartctl output found in sosreport')
            return None

        # Strong indicators of problems that require immediate attention
        failure_counters = [
            'Current_Pending_Sector',
            'Offline_Uncorrectable',
        ]

        # Informational counters that may indicate issues but require
        # further analysis for proper interpretation
        info_counters = [
            'Reallocated_Sector_Ct',
            'UDMA_CRC_Error_Count',
            'Spin_Retry_Count',
            'End-to-End_Error',
            'Command_Timeout',
        ]

        abnormal_disks = {}
        for path, content in results.items():
            # Check overall health status
            disk_issues = ({'health_status': 'FAILED'} if re.search(
                r'SMART overall-health self-assessment test result: FAILED',
                content
            ) else {})

            # Match SMART attribute lines format:
            # ID# ATTRIBUTE_NAME FLAG VALUE WORST THRESH TYPE UPDATED
            # WHEN_FAILED RAW_VALUE
            failure_issues = {}
            info_issues = {}

            for counter in failure_counters:
                pattern = rf'^\s*\d+\s+{re.escape(counter)}\b.*?(\d+)\s*$'
                match = re.search(pattern, content, re.MULTILINE)
                if match and int(match.group(1)) > 0:
                    failure_issues[counter] = int(match.group(1))

            for counter in info_counters:
                pattern = rf'^\s*\d+\s+{re.escape(counter)}\b.*?(\d+)\s*$'
                match = re.search(pattern, content, re.MULTILINE)
                if match and int(match.group(1)) > 0:
                    info_issues[counter] = int(match.group(1))

            disk_issues.update({
                key: value for key, value in {
                    'failure_counters': failure_issues,
                    'info_counters': info_issues,
                }.items() if value
            })

            # Only report disk if there are issues
            if disk_issues:
                abnormal_disks[path] = disk_issues

        if abnormal_disks:
            return {
                'abnormal_disks': abnormal_disks,
                'message': ('Some disks reported SMART health failures or '
                            'abnormal error counters.'),
            }

        return {
            'message': ('No SMART health failures or abnormal error counters '
                        'detected.'),
        }

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
