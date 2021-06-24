#!/usr/bin/python3
import os

from common import (
    issue_types,
    issues_utils,
)
from kernel_common import (
    KernelChecksBase,
    VMSTAT,
    BUDDY_INFO,
    SLABINFO,
)

YAML_PRIORITY = 1


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
            if "memory-checks" not in self._output:
                self._output["memory-checks"] = {node_key: []}
            elif node_key not in self._output["memory-checks"]:
                self._output["memory-checks"][node_key] = []

            self._output["memory-checks"][node_key].append(zone_info)

    def get_slab_major_consumers(self):
        top5_name = {}
        top5_num_objs = {}
        top5_objsize = {}

        # /proc/slabinfo may not exist in containers/VMs
        if not os.path.exists(SLABINFO):
            return

        # exclude kernel memory allocations
        for line in self.get_slabinfo(exclude_names=[r"\S*kmalloc"]):
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

        if "memory-checks" not in self._output:
            self._output["memory-checks"] = {}

        self._output["memory-checks"]["slab-top-consumers"] = top5

    def check_nodes_memory(self, zones_type):
        nodes = self.numa_nodes
        if not nodes:
            return

        if "memory-checks" not in self._output:
            self._output["memory-checks"] = {}

        node_zones = {}
        for node in nodes:
            msg = ("limited high order memory - check {}".
                   format(BUDDY_INFO))
            node_key = "node{}-{}".format(node, zones_type.lower())
            node_zones[node_key] = msg
            self.check_mallocinfo(node, zones_type, node_key)

            if node_key in self._output["memory-checks"]:
                self._output["memory-checks"][node_key].append(
                    node_zones[node_key])

    def get_memory_info(self):
        self.check_nodes_memory("Normal")
        if self._output.get("memory-checks") is None:
            # only check other types of no issue detected on Normal
            self.check_nodes_memory("DMA32")

        # We only report on compaction errors if there is a shortage of
        # high-order zones.
        if self._output.get("memory-checks"):
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
            self._output["memory-checks"] = "no issues found"

    def __call__(self):
        self.get_memory_info()
