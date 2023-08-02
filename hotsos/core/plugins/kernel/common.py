import os
import re
from functools import cached_property

from hotsos.core import host_helpers, plugintools
from hotsos.core.config import HotSOSConfig
from hotsos.core.plugins.kernel.config import KernelConfig


class KernelBase(object):

    @cached_property
    def version(self):
        """Returns string kernel version."""
        uname = host_helpers.CLIHelper().uname()
        if uname:
            ret = re.compile(r"^Linux\s+\S+\s+(\S+)\s+.+").match(uname)
            if ret:
                return ret[1]

        return ""

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

    @property
    def plugin_runnable(self):
        # Always run
        return True
