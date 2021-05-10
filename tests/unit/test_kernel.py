import mock

import utils

# Need this for plugin imports
utils.add_sys_plugin_path("kernel")
from plugins.kernel.parts import (  # noqa E402
    kernel_info,
    kernel_memory,
)


class TestKernelPluginPartKernelInfo(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(kernel_info, "KERNEL_INFO", {})
    def test_get_cmdline_info(self):
        kernel_info.KernelGeneralChecks().get_cmdline_info()
        expected = {'boot': 'ro '
                    'console=tty0 console=ttyS0,115200 console=ttyS1,115200 '
                    'panic=30 raid=noautodetect'}
        self.assertEquals(kernel_info.KERNEL_INFO, expected)

    @mock.patch.object(kernel_info, "KERNEL_INFO", {})
    def test_get_systemd_info(self):
        kernel_info.KernelGeneralChecks().get_systemd_info()
        self.assertEquals(kernel_info.KERNEL_INFO,
                          {'systemd': {'CPUAffinity':
                                       '0-7,32-39'}})


class TestKernelPluginPartKernelMemoryInfo(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    def test_numa_nodes(self):
        ret = kernel_memory.KernelMemoryChecks().numa_nodes
        expected = [0, 1]
        self.assertEquals(ret, expected)

    def test_get_node_zones(self):
        ret = kernel_memory.KernelMemoryChecks().get_node_zones("DMA32", 0)
        expected = ("Node 0, zone DMA32 2900 1994 2422 4791 3090 1788 886 290 "
                    "21 0 0")
        self.assertEquals(ret, expected)

    @mock.patch.object(kernel_memory, "KERNEL_INFO", {})
    def test_check_mallocinfo_good_node(self):
        kernel_memory.KernelMemoryChecks().check_mallocinfo(0, "Normal",
                                                               "node0-normal")
        self.assertEquals(kernel_memory.KERNEL_INFO, {})

    @mock.patch.object(kernel_memory, "KERNEL_INFO", {})
    def test_check_mallocinfo_bad_node(self):
        kernel_memory.KernelMemoryChecks().check_mallocinfo(1, "Normal",
                                                               "node1-normal")
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
        self.assertEquals(kernel_memory.KERNEL_INFO, expected)

    @mock.patch.object(kernel_memory, "KERNEL_INFO", {})
    def test_check_nodes_memory(self):
        kernel_memory.KernelMemoryChecks().check_nodes_memory("Normal")
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
                                       format(kernel_memory.BUDDY_INFO))
                                      ]}}
        self.assertEquals(kernel_memory.KERNEL_INFO, expected)

    @mock.patch.object(kernel_memory, "KERNEL_INFO", {})
    def test_get_slab_major_consumers(self):
        kernel_memory.KernelMemoryChecks().get_slab_major_consumers()
        expected = {"memory-checks":
                    {'slab-top-consumers':
                     ['buffer_head (3714895.9453125k)',
                      'radix_tree_node (2426487.4921875k)',
                      'vm_area_struct (45507.8125k)',
                      'Acpi-Operand (14375.8125k)',
                      'anon_vma (8167.96875k)']}
                    }
        self.assertEquals(kernel_memory.KERNEL_INFO, expected)
