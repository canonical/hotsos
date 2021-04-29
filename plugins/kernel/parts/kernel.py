#!/usr/bin/python3
import os
import re

from common import (
    constants,
    helpers,
    issue_types,
    issues_utils,
    plugin_yaml,
)

KERNEL_INFO = {}

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
        uname = helpers.get_uname()
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

    def get_vmstat_value(self, key):
        for line in open(VMSTAT):
            if line.partition(" ")[0] == key:
                return int(line.partition(" ")[2])

        return None

    def get_slabinfo(self):
        info = []
        skip = 2
        for line in open(SLABINFO):
            if skip:
                skip -= 1
                continue

            if line.startswith("kmalloc"):
                continue

            sections = line.split()
            # name, num_objs, objsize
            info.append([sections[0],
                         int(sections[2]),
                         int(sections[3])])

        return info


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


class KernelMemoryChecks(KernelChecksBase):

    def check_mallocinfo(self, node, zones_type, node_key):
        empty_zone_tally = 0
        high_order_seq = 0
        zone_info = {"zones": {}}

        node_zones = self.get_node_zones(zones_type, node)
        if node_zones is None:
            return

        # start from highest order zone (10) and work down to 0
        contiguous_empty_zones = True
        for zone in range(10, -1, -1):
            free = int(node_zones.split()[5 + zone - 1])
            zone_info["zones"][zone] = free
            if free == 0:
                empty_zone_tally += zone
            else:
                contiguous_empty_zones = False

            if contiguous_empty_zones:
                high_order_seq += 1

        report_problem = False

        # 0+1+...10 is 55 so threshold is this minus the max order
        if empty_zone_tally >= 45 and high_order_seq:
            report_problem = True

        # this implies that top 5 orders are unavailable
        if high_order_seq > 5:
            report_problem = True

        if report_problem:
            if "memory-checks" not in KERNEL_INFO:
                KERNEL_INFO["memory-checks"] = {node_key: []}
            elif node_key not in KERNEL_INFO["memory-checks"]:
                KERNEL_INFO["memory-checks"][node_key] = []

            KERNEL_INFO["memory-checks"][node_key].append(zone_info)

    def get_slab_major_consumers(self):
        top5_name = {}
        top5_num_objs = {}
        top5_objsize = {}

        # /proc/slabinfo may not exist in containers/VMs
        if not os.path.exists(SLABINFO):
            return

        # name, num_objs, objsize
        for line in self.get_slabinfo():
            name = line[0]
            num_objs = line[1]
            objsize = line[2]

            for i in range(5):
                if num_objs > top5_num_objs.get(i, 0):
                    top5_num_objs[i] = num_objs
                    top5_name[i] = name
                    top5_objsize[i] = objsize
                    break

        top5 = []
        for i in range(5):
            if top5_name.get(i):
                kbytes = top5_num_objs.get(i) * top5_objsize.get(i) / 1024
                top5.append("{} ({}k)".format(top5_name.get(i), kbytes))

        if "memory-checks" not in KERNEL_INFO:
            KERNEL_INFO["memory-checks"] = {}

        KERNEL_INFO["memory-checks"]["slab-top-consumers"] = top5

    def check_nodes_memory(self, zones_type):
        nodes = self.numa_nodes
        if not nodes:
            return

        if "memory-checks" not in KERNEL_INFO:
            KERNEL_INFO["memory-checks"] = {}

        node_zones = {}
        for node in nodes:
            msg = ("limited high order memory - check {}".
                   format(BUDDY_INFO))
            node_key = "node{}-{}".format(node, zones_type.lower())
            node_zones[node_key] = msg
            self.check_mallocinfo(node, zones_type, node_key)

            if node_key in KERNEL_INFO["memory-checks"]:
                KERNEL_INFO["memory-checks"][node_key].append(
                    node_zones[node_key])

    def get_memory_info(self):
        self.check_nodes_memory("Normal")
        if KERNEL_INFO.get("memory-checks") is None:
            # only check other types of no issue detected on Normal
            self.check_nodes_memory("DMA32")

        # We only report on compaction errors if there is a shortage of
        # high-order zones.
        if KERNEL_INFO.get("memory-checks"):
            fail_count = self.get_vmstat_value("compact_fail")
            success_count = self.get_vmstat_value("compact_success")
            # we use an arbitrary threshold of 10k to suggest that a lot of
            # compaction has occurred but noting that this is a rolling counter
            # and is not necessarily representative of current state.
            if success_count > 10000:
                pcent = int(fail_count / (success_count / 100))
                if pcent > 10:
                    msg = ("failures are at {}% of successes (see {})"
                           .format(pcent, VMSTAT))
                    issue = issue_types.MemoryWarning("compaction " + msg)
                    issues_utils.add_issue(issue)

            self.get_slab_major_consumers()
        else:
            KERNEL_INFO["memory-checks"] = "no issues found"

    def __call__(self):
        self.get_memory_info()


def get_kernal_general_checks():
    return KernelGeneralChecks()


def get_kernal_memory_checks():
    return KernelMemoryChecks()


if __name__ == "__main__":
    get_kernal_general_checks()()
    get_kernal_memory_checks()()
    if KERNEL_INFO:
        plugin_yaml.save_part(KERNEL_INFO, priority=0)
