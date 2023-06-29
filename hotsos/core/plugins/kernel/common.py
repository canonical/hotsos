import os
import re
from functools import cached_property
from datetime import datetime

from hotsos.core.host_helpers.cli import CLIHelper
from hotsos.core import host_helpers, plugintools
from hotsos.core.config import HotSOSConfig
from hotsos.core.log import log
from hotsos.core.plugins.kernel.config import KernelConfig
from hotsos.core.plugins.system import SystemBase


# NOTE(dosaboy): when updating this, refer to the kernel supported versions
# page: https://ubuntu.com/about/release-cycle#ubuntu-kernel-release-cycle
KERNEL_EOL_INFO = {
    '5.19': 
        {'22.04.5': datetime(2027, 4, 30),
         '20.04.0': datetime(2025, 4, 30)},
    '5.13': 
        {'21.10': datetime(2022, 6, 30),
         '20.04.4': datetime(2022, 6, 30)},
    '5.11': 
        {'21.04': datetime(2022, 1, 30),
         '20.04.3': datetime(2022, 1, 30)},
    '5.8': 
        {'20.10': datetime(2021, 6, 30),
         '20.04.2': datetime(2021, 6, 30),
         '18.04.5': datetime(2028, 4, 30),
         '20.04.1': datetime(2030, 4, 30),
         '20.04.0': datetime(2030, 4, 30)},
    '4.15': 
        {'16.04.5': datetime(2021, 4, 30),
         '18.04.1': datetime(2023, 4, 30),
         '18.04.0': datetime(2023, 4, 30)},
    '4.4': 
        {'16.04.1': datetime(2021, 4, 30),
         '16.04.0': datetime(2021, 4, 30),
         '14.04.5': datetime(2019, 4, 30)},
    '3.13': 
        {'14.04.1': datetime(2019, 4, 30),
         '14.04.1': datetime(2019, 4, 30)},
}


class KernelBase(object):

    @cached_property
    def version(self):
        """Returns string kernel version."""
        uname = host_helpers.CLIHelper().uname()
        if uname:
            ret = re.compile(r"^Linux\s+\S+\s+(\S+)\s+.+").match(uname)
            if ret:
                return ret[1]

        return ''

    @cached_property
    def days_to_eol(self):
        if self.version == '':
            log.warning("kernel version could not be determined.")
            return

        ret = re.match('(\d{1,2}.\d{1,2}).\d{1,2}\S+', self.version)
        if not ret:
            log.warning("unable to determine eol info for kernel "
                        "version '%s' - could not extract version",
                        self.version)
            return

        eol = KERNEL_EOL_INFO.get(ret.group(1))
        if eol is None:
            log.warning("unable to determine eol info for kernel "
                        "version '%s' (%s)", self.version, ret.group(1))
            return

        os_version = SystemBase().os_version
        eol = eol.get(os_version)
        if eol is None:
            log.warning("unable to determine eol info for kernel "
                        "version '%s' and os version '%s'", self.version,
                        os_version)
            return

        today = datetime.utcfromtimestamp(int(CLIHelper().date()))
        delta = (eol - today).days
        return delta

    @cached_property
    def isolcpus_enabled(self):
        return KernelConfig().get('isolcpus') is not None

    @cached_property
    def boot_parameters(self):
        """Returns list of boot parameters."""
        parameters = []
        path = os.path.join(HotSOSConfig.data_root, "proc/cmdline")
        if os.path.exists(path):
            with open(path) as fd:
                cmdline = fd.read().strip()
            for entry in cmdline.split():
                if entry.startswith("BOOT_IMAGE"):
                    continue

                if entry.startswith("root="):
                    continue

                parameters.append(entry)

            return parameters


class KernelChecksBase(KernelBase, plugintools.PluginPartBase):
    plugin_name = 'kernel'
    plugin_root_index = 14

    @property
    def plugin_runnable(self):
        # Always run
        return True
