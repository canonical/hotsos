import os
import re

from hotsos.core import host_helpers, plugintools
from hotsos.core.config import HotSOSConfig
from hotsos.core.ycheck.events import YEventCheckerBase
from hotsos.core.plugins.kernel.config import KernelConfig


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
        uname = host_helpers.CLIHelper().uname()
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
