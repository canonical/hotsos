#!/usr/bin/python3
import os
import re

from common import (
    constants,
    plugin_yaml,
)
from kernel_common import KernelChecksBase

KERNEL_INFO = {}


class KernelGeneralChecks(KernelChecksBase):

    def get_version_info(self):
        if self.kernel_version:
            KERNEL_INFO["version"] = self.kernel_version

    def get_cmdline_info(self):
        if self.boot_parameters:
            KERNEL_INFO["boot"] = " ".join(self.boot_parameters)

    def get_systemd_info(self):
        path = os.path.join(constants.DATA_ROOT, "etc/systemd/system.conf")
        if os.path.exists(path):
            KERNEL_INFO["systemd"] = {"CPUAffinity": "not set"}
            for line in open(path):
                ret = re.compile("^CPUAffinity=(.+)").match(line)
                if ret:
                    KERNEL_INFO["systemd"]["CPUAffinity"] = ret[1]

    def __call__(self):
        self.get_version_info()
        self.get_cmdline_info()
        self.get_systemd_info()


def get_kernal_general_checks():
    return KernelGeneralChecks()


if __name__ == "__main__":
    get_kernal_general_checks()()
    if KERNEL_INFO:
        plugin_yaml.save_part(KERNEL_INFO, priority=0)
