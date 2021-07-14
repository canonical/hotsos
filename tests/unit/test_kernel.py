import utils

from plugins.kernel.pyparts import (
    info,
    memory,
    network,
)


class TestKernelPluginPartKernelInfo(utils.BaseTestCase):

    def test_get_cmdline_info(self):
        inst = info.KernelGeneralChecks()
        inst.get_cmdline_info()
        expected = {'boot': 'ro '
                    'console=tty0 console=ttyS0,115200 console=ttyS1,115200 '
                    'panic=30 raid=noautodetect'}
        self.assertEquals(inst.output, expected)

    def test_get_systemd_info(self):
        inst = info.KernelGeneralChecks()
        inst.get_systemd_info()
        self.assertEquals(inst.output,
                          {'systemd': {'CPUAffinity': '0-7,32-39'}})


class TestKernelPluginPartKernelMemoryInfo(utils.BaseTestCase):

    def test_numa_nodes(self):
        ret = memory.KernelMemoryChecks().numa_nodes
        expected = [0, 1]
        self.assertEquals(ret, expected)

    def test_get_node_zones(self):
        inst = memory.KernelMemoryChecks()
        ret = inst.get_node_zones("DMA32", 0)
        expected = ("Node 0, zone DMA32 2900 1994 2422 4791 3090 1788 886 290 "
                    "21 0 0")
        self.assertEquals(ret, expected)

    def test_check_mallocinfo_good_node(self):
        inst = memory.KernelMemoryChecks()
        inst.check_mallocinfo(0, "Normal", "node0-normal")
        self.assertIsNone(inst.output)

    def test_check_mallocinfo_bad_node(self):
        inst = memory.KernelMemoryChecks()
        inst.check_mallocinfo(1, "Normal", "node1-normal")
        expected = {'memory-checks': {'node1-normal': [{'zones': {0: 220376,
                                                                  1: 217700,
                                                                  2: 54089,
                                                                  3: 1,
                                                                  4: 0,
                                                                  5: 0,
                                                                  6: 0,
                                                                  7: 0,
                                                                  8: 0,
                                                                  9: 0,
                                                                  10: 0}}]}}
        self.assertEquals(inst.output, expected)

    def test_check_nodes_memory(self):
        inst = memory.KernelMemoryChecks()
        inst.check_nodes_memory("Normal")
        expected = {'memory-checks':
                    {'node1-normal': [{'zones': {0: 220376,
                                                 1: 217700,
                                                 2: 54089,
                                                 3: 1,
                                                 4: 0,
                                                 5: 0,
                                                 6: 0,
                                                 7: 0,
                                                 8: 0,
                                                 9: 0,
                                                 10: 0}},
                                      ("limited high order memory - check {}".
                                       format(memory.BUDDY_INFO))
                                      ]}}
        self.assertEquals(inst.output, expected)

    def test_get_slab_major_consumers(self):
        inst = memory.KernelMemoryChecks()
        inst.get_slab_major_consumers()
        expected = {"memory-checks":
                    {'slab-top-consumers':
                     ['buffer_head (3714895.9453125k)',
                      'radix_tree_node (2426487.4921875k)',
                      'vm_area_struct (45507.8125k)',
                      'Acpi-Operand (14375.8125k)',
                      'anon_vma (8167.96875k)']}
                    }
        self.assertEquals(inst.output, expected)


class TestKernelPluginPartKernelNetwork(utils.BaseTestCase):

    def test_run_network_checks(self):
        expected = {'over-mtu-dropped-packets':
                    {'tap40f8453b-31': 5}}
        inst = network.KernelNetworkChecks()
        inst()
        self.assertEquals(inst.output, expected)
