import os

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
