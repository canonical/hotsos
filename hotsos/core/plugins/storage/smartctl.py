import os
import re
from functools import cached_property

from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import CLIHelper, APTPackageHelper
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

    @staticmethod
    def get_system_disks():
        """
        Get physical disks available in this host. Ignores virtual devices e.g.
        loop devices.

        @return: list of devices
        """
        devs = []
        out = CLIHelper().ls_lanR_sys_block()
        for line in out:
            if re.search(r'\s->\s\.\./devices/virtual', line):
                continue

            ret = re.search(r'\s(\S+)\s->', line)
            if ret:
                devs.append(ret.group(1))

        return devs

    @cached_property
    def abnormal_disks(self):
        """ Summarize disk health from smartctl output. """
        results = {}
        for dev in self.get_system_disks():
            out = CLIHelper().smartctl_all(device=dev)
            if out:
                results[dev] = '\n'.join([line.strip() for line in out])

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
        for dev, content in results.items():
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
                abnormal_disks[dev] = disk_issues

        return abnormal_disks
