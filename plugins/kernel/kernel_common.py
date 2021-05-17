import os
import re

from common import (
    constants,
    cli_helpers,
)

BUDDY_INFO = os.path.join(constants.DATA_ROOT, "proc/buddyinfo")
SLABINFO = os.path.join(constants.DATA_ROOT, "proc/slabinfo")
VMSTAT = os.path.join(constants.DATA_ROOT, "proc/vmstat")


class KernelChecksBase(object):

    def __init__(self):
        self._kernel_version = ""
        self._boot_parameters = []
        self._numa_nodes = []

    @property
    def kernel_version(self):
        """Returns string kernel version."""
        uname = cli_helpers.get_uname()
        if uname:
            ret = re.compile(r"^Linux\s+\S+\s+(\S+)\s+.+").match(uname)
            if ret:
                self._kernel_version = ret[1]

        return self._kernel_version

    @property
    def boot_parameters(self):
        """Returns list of boot parameters."""
        parameters = []
        path = os.path.join(constants.DATA_ROOT, "proc/cmdline")
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
        if not os.path.exists(BUDDY_INFO):
            return self._numa_nodes

        if not self._numa_nodes:
            nodes = set()
            for line in open(BUDDY_INFO):
                nodes.add(int(line.split()[1].strip(',')))

        self._numa_nodes = list(nodes)
        return self._numa_nodes

    def get_node_zones(self, zones_type, node):
        for line in open(BUDDY_INFO):
            if line.split()[3] == zones_type and \
                    line.startswith("Node {},".format(node)):
                line = line.split()
                return " ".join(line)

        return None

    def get_vmstat_value(self, consumer):
        """
        Look for first occurence of consumer and return its stats.
        """
        for line in open(VMSTAT):
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
        for line in open(SLABINFO):
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
