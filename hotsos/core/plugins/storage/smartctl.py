import os
import re
from collections import OrderedDict
from functools import cached_property

from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import APTPackageHelper
from hotsos.core.log import log
from hotsos.core.plugins.storage import StorageBase


class SmartctlChecks(StorageBase):
    """Base class for smartctl storage checks."""

    @classmethod
    def is_runnable(cls):
        """
        Determine whether smartctl checks should run.
        @return: True if smartctl data is available, False otherwise
        """

        # Check if smartmontools package is installed
        apt = APTPackageHelper(core_pkgs=['smartmontools'])
        if apt.core:
            log.debug("smartmontools package installed")
            return True

        # Check if smartctl output exists in sosreport
        sos_commands = os.path.join(HotSOSConfig.data_root, 'sos_commands')
        for path in [os.path.join(sos_commands, d) for d in ('nvme', 'ata')]:
            if os.path.isdir(path) and os.listdir(path):
                log.debug("smartctl data found in '%s'", path)
                return True

        log.debug("No smartctl data found")
        return False

    @cached_property
    def abnormal_disks(self):
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

        return abnormal_disks

    @staticmethod
    def _search_sosreport(directory):
        """
        Search for and read all smartctl output files in the given directory.
        """
        results = OrderedDict()
        if not os.path.isdir(directory):
            return results
        for fname in sorted(os.listdir(directory)):
            fpath = os.path.join(directory, fname)
            if os.path.isfile(fpath):
                try:
                    with open(fpath, encoding='utf-8', errors='ignore') as f:
                        results[os.path.basename(fpath)] = f.read()
                except OSError as exc:
                    log.debug('Failed to read %s: %s', fpath, exc)
        return results
