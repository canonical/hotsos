import os

from hotsos.core.log import log
from hotsos.core.issues import IssuesManager, MemoryWarning
from hotsos.core.plugins.kernel import KernelChecksBase


class KernelMemoryChecks(KernelChecksBase):

    def check_mallocinfo(self, node, zones_type):
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
            return zone_info

    def get_slab_major_consumers(self):
        top5_name = {}
        top5_num_objs = {}
        top5_objsize = {}

        # /proc/slabinfo may not exist in containers/VMs
        if not os.path.exists(self.slabinfo_path):
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

        return top5

    def check_nodes_memory(self, zones_type):
        log.debug("checking memory zone_type=%s", zones_type)
        nodes = self.numa_nodes
        if not nodes:
            log.debug("no nodes found for zone_type=%s", zones_type)
            return

        node_results = {}
        node_zones = {}
        for node in nodes:
            msg = ("limited high order memory - check {}".
                   format(self.buddyinfo_path))
            node_key = "node{}-{}".format(node, zones_type.lower())
            node_zones[node_key] = msg
            zone_info = self.check_mallocinfo(node, zones_type)
            if zone_info:
                node_results[node_key] = [zone_info, node_zones[node_key]]

        return node_results

    def __summary_memory_checks(self):
        _mem_info = {}
        node_results = self.check_nodes_memory("Normal")
        if not node_results:
            # only check other types of no issue detected on Normal
            node_results = self.check_nodes_memory("DMA32")

        if node_results:
            _mem_info = node_results

        # We only report on compaction errors if there is a shortage of
        # high-order zones.
        if _mem_info:
            fail_count = self.get_vmstat_value("compact_fail")
            success_count = self.get_vmstat_value("compact_success")
            # we use an arbitrary threshold of 10k to suggest that a lot of
            # compaction has occurred but noting that this is a rolling counter
            # and is not necessarily representative of current state.
            if success_count > 10000:
                pcent = int(fail_count / (success_count / 100))
                if pcent > 10:
                    msg = ("compaction failures are at {}% of successes "
                           "(see {}).".format(pcent, self.vmstat_path))
                    IssuesManager().add(MemoryWarning(msg))

            top5 = self.get_slab_major_consumers()
            if top5:
                _mem_info["slab-top-consumers"] = top5
        else:
            _mem_info = "no issues found"

        return _mem_info
