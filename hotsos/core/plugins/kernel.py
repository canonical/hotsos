import os
import re

from hotsos.core.ycheck.events import YEventCheckerBase
from hotsos.core import (
    checks,
    plugintools,
)
from hotsos.core.config import HotSOSConfig
from hotsos.core.cli_helpers import CLIHelper
from hotsos.core.plugins.system import SystemBase


class SYSFSBase(object):

    def get(self, relpath):
        """
        Read a sysfs entry and return its value.

        @param relpath: path relative to DATA_ROOT/sys
        """
        path = os.path.join(HotSOSConfig.DATA_ROOT, 'sys', relpath)
        if not os.path.exists(path):
            return

        with open(path) as fd:
            value = fd.read()

        return value.strip()


class CPU(SYSFSBase):

    @property
    def vendor(self):
        out = CLIHelper().lscpu()
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
        for id in range(SystemBase().num_cpus):
            cpu_governor = self.cpufreq_scaling_governor(id)
            if cpu_governor:
                governors.add(cpu_governor)
            else:
                governors.add('unknown')

        return ','.join(list(governors))


class KernelConfig(checks.ConfigBase):
    """ Kernel configuration. """

    def __init__(self, *args, **kwargs):
        path = os.path.join(HotSOSConfig.DATA_ROOT, "proc/cmdline")
        super().__init__(path=path, *args, **kwargs)
        self._cfg = {}
        self._load()

    def get(self, key, expand_to_list=False):
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


class SystemdConfig(checks.SectionalConfigBase):
    """Systemd configuration."""

    def __init__(self, *args, **kwargs):
        path = os.path.join(HotSOSConfig.DATA_ROOT, "etc/systemd/system.conf")
        super().__init__(path=path, *args, **kwargs)

    @property
    def cpuaffinity_enabled(self):
        if self.get('CPUAffinity'):
            return True

        return False


class KernelBase(object):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._kernel_version = ""
        self._boot_parameters = []
        self._numa_nodes = []

    @property
    def buddyinfo_path(self):
        return os.path.join(HotSOSConfig.DATA_ROOT, "proc/buddyinfo")

    @property
    def slabinfo_path(self):
        return os.path.join(HotSOSConfig.DATA_ROOT, "proc/slabinfo")

    @property
    def vmstat_path(self):
        return os.path.join(HotSOSConfig.DATA_ROOT, "proc/vmstat")

    @property
    def version(self):
        """Returns string kernel version."""
        uname = CLIHelper().uname()
        if uname:
            ret = re.compile(r"^Linux\s+\S+\s+(\S+)\s+.+").match(uname)
            if ret:
                self._kernel_version = ret[1]

        return self._kernel_version

    @property
    def isolcpus_enabled(self):
        return KernelConfig().get('isolcpus') is not None

    @property
    def boot_parameters(self):
        """Returns list of boot parameters."""
        parameters = []
        path = os.path.join(HotSOSConfig.DATA_ROOT, "proc/cmdline")
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

    @property
    def numa_nodes(self):
        """Returns list of numa nodes."""
        # /proc/buddyinfo may not exist in containers/VMs
        if not os.path.exists(self.buddyinfo_path):
            return self._numa_nodes

        if self._numa_nodes:
            return self._numa_nodes

        nodes = set()
        for line in open(self.buddyinfo_path):
            nodes.add(int(line.split()[1].strip(',')))

        self._numa_nodes = list(nodes)
        return self._numa_nodes

    def get_node_zones(self, zones_type, node):
        for line in open(self.buddyinfo_path):
            if line.split()[3] == zones_type and \
                    line.startswith("Node {},".format(node)):
                line = line.split()
                return " ".join(line)

        return None

    def get_vmstat_value(self, consumer):
        """
        Look for first occurence of consumer and return its stats.
        """
        for line in open(self.vmstat_path):
            if line.partition(" ")[0] == consumer:
                return int(line.partition(" ")[2])

        return None

    def get_slabinfo(self, exclude_names=None):
        """
        Returns a list with contents of the following columns from
        /proc/slabinfo:

            name
            num_objs
            objsize

        @param exclude_names: optional list of names to exclude.
        """
        info = []
        for line in open(self.slabinfo_path):
            exclude = False
            if exclude_names:
                for name in exclude_names:
                    if re.compile("^{}".format(name)).search(line):
                        exclude = True
                        break

            if exclude:
                continue

            sections = line.split()
            if sections[0] == "#" or sections[0] == "slabinfo":
                continue

            # name, num_objs, objsize
            info.append([sections[0],
                         int(sections[2]),
                         int(sections[3])])

        return info


class KernelChecksBase(KernelBase, plugintools.PluginPartBase):

    @property
    def plugin_runnable(self):
        # Always run
        return True


class KernelEventChecksBase(KernelChecksBase, YEventCheckerBase):

    @property
    def summary(self):
        # mainline all results into summary root
        return self.run_checks()
