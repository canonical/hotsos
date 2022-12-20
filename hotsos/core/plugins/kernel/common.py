import os
import re

from hotsos.core.utils import cached_property
from hotsos.core import host_helpers, plugintools
from hotsos.core.config import HotSOSConfig
from hotsos.core.plugins.kernel.config import KernelConfig


class KernelBase(object):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._kernel_version = ""
        self._boot_parameters = []

    @cached_property
    def version(self):
        """Returns string kernel version."""
        uname = host_helpers.CLIHelper().uname()
        if uname:
            ret = re.compile(r"^Linux\s+\S+\s+(\S+)\s+.+").match(uname)
            if ret:
                self._kernel_version = ret[1]

        return self._kernel_version

    @cached_property
    def isolcpus_enabled(self):
        return KernelConfig().get('isolcpus') is not None

    @cached_property
    def boot_parameters(self):
        """Returns list of boot parameters."""
        parameters = []
        path = os.path.join(HotSOSConfig.data_root, "proc/cmdline")
        if os.path.exists(path):
            cmdline = open(path).read().strip()
            for entry in cmdline.split():
                if entry.startswith("BOOT_IMAGE"):
                    continue

                if entry.startswith("root="):
                    continue

                parameters.append(entry)

            self._boot_parameters = parameters

        return self._boot_parameters


class KernelChecksBase(KernelBase, plugintools.PluginPartBase):

    @property
    def plugin_runnable(self):
        # Always run
        return True
