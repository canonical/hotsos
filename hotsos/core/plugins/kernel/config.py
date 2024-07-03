import os
import re

from hotsos.core.config import HotSOSConfig
from hotsos.core import host_helpers


class KernelConfig(host_helpers.ConfigBase):
    """ Kernel configuration. """

    def __init__(self, *args, **kwargs):
        path = os.path.join(HotSOSConfig.data_root, "proc/cmdline")
        super().__init__(path=path, *args, **kwargs)
        self._cfg = {}
        self._load()

    def get(self, key, section=None, expand_to_list=False):
        value = self._cfg.get(key)
        if expand_to_list and value is not None:
            return self.expand_value_ranges(value)

        return value

    def _load(self):
        """
        Currently only supports extracting isolcpus

        TODO: make more general
        """
        if not self.exists:
            return

        with open(self.path) as fd:
            for line in fd:
                expr = r'.*\s+isolcpus=([0-9\-,]+)\s*.*'
                ret = re.compile(expr).match(line)
                if ret:
                    self._cfg["isolcpus"] = ret[1]
                    break


class SystemdConfig(host_helpers.IniConfigBase):
    """Systemd configuration."""

    def __init__(self, *args, **kwargs):
        path = os.path.join(HotSOSConfig.data_root, "etc/systemd/system.conf")
        super().__init__(path=path, *args, **kwargs)

    @property
    def cpuaffinity_enabled(self):
        if self.get('CPUAffinity'):
            return True

        return False
