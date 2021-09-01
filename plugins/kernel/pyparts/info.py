import os

from core import constants
from core.plugins.kernel import (
    KernelChecksBase,
    SystemdConfig,
)

YAML_PRIORITY = 0


class KernelGeneralChecks(KernelChecksBase):

    def get_version_info(self):
        if self.kernel_version:
            self._output["version"] = self.kernel_version

    def get_cmdline_info(self):
        if self.boot_parameters:
            self._output["boot"] = " ".join(self.boot_parameters)

    def get_systemd_info(self):
        cfg = SystemdConfig()
        if cfg.exists:
            if cfg.get("CPUAffinity") is None:
                self._output["systemd"] = {"CPUAffinity": "not set"}
            else:
                value = cfg.get("CPUAffinity")
                self._output["systemd"] = {"CPUAffinity": value}

    def _get_system_entry(self, path):
        if not os.path.exists(path):
            return

        with open(path) as fd:
            value = fd.read()

        return value.strip()

    def get_cpu_info(self):
        """
        If isolcpus is set on the proc/cmdline this should equal that value
        otherwise it has not taken effect.
        """
        path = os.path.join(constants.DATA_ROOT,
                            "sys/devices/system/cpu/isolated")
        isolated = self._get_system_entry(path)
        if isolated:
            self._output["cpu"] = {"isolated": isolated}

        path = os.path.join(constants.DATA_ROOT,
                            "sys/devices/system/cpu/smt/active")
        smt = self._get_system_entry(path)
        if smt is not None:
            if smt == "1":
                self._output["cpu"] = {"smt": "enabled"}
            else:
                self._output["cpu"] = {"smt": "disabled"}

    def __call__(self):
        self.get_version_info()
        self.get_cmdline_info()
        self.get_systemd_info()
        self.get_cpu_info()
