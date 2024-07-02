import os
import re

from hotsos.core.config import HotSOSConfig
from hotsos.core import host_helpers
from hotsos.core.plugins.system.system import SystemBase


class SYSFSBase():

    @staticmethod
    def get(relpath):
        """
        Read a sysfs entry and return its value.

        @param relpath: path relative to <data_root>sys
        """
        path = os.path.join(HotSOSConfig.data_root, 'sys', relpath)
        if not os.path.exists(path):
            return

        with open(path) as fd:
            value = fd.read()

        return value.strip()


class CPU(SYSFSBase):

    @property
    def model(self):
        out = host_helpers.CLIHelper().lscpu()
        if not out:
            return

        for line in out:
            if line.startswith("Model name:"):
                return re.search(r'Model name:\s+(.+)', line).group(1)

    @property
    def vendor(self):
        out = host_helpers.CLIHelper().lscpu()
        if not out:
            return

        for line in out:
            if line.startswith("Vendor ID:"):
                return re.search(r'Vendor ID:\s+(.+)', line).group(1).lower()

    @property
    def isolated(self):
        """ This means that isolcpus is configured. """
        return self.get('devices/system/cpu/isolated')

    @property
    def smt(self):
        smt = self.get('devices/system/cpu/smt/active')
        if smt is None:
            return

        if smt == '1':
            return True

        return False

    def cpufreq_scaling_governor(self, cpu_id):
        return self.get('devices/system/cpu/cpu{}/cpufreq/scaling_governor'.
                        format(cpu_id))

    @property
    def cpufreq_scaling_governor_all(self):
        governors = set()
        for cpu_id in range(SystemBase().num_cpus):
            cpu_governor = self.cpufreq_scaling_governor(cpu_id)
            if cpu_governor:
                governors.add(cpu_governor)
            else:
                governors.add('unknown')

        return ','.join(list(governors))
