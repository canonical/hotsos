import mock

from importlib.util import spec_from_loader, module_from_spec
from importlib.machinery import SourceFileLoader

import utils

# need this for non-standard import
specs = {}
for plugin in ["01kernel"]:
    loader = SourceFileLoader("kern_{}".format(plugin),
                              "plugins/kernel/{}".format(plugin))
    specs[plugin] = spec_from_loader("kern_{}".format(plugin), loader)

kern_01kernel = module_from_spec(specs["01kernel"])
specs["01kernel"].loader.exec_module(kern_01kernel)


class TestKernelPlugin01kernel(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(kern_01kernel, "KERNEL_INFO", {})
    def test_get_cmdline_info(self):
        kern_01kernel.get_cmdline_info()
        expected = {'boot': 'ro '
                    'console=tty0 console=ttyS0,115200 console=ttyS1,115200 '
                    'panic=30 raid=noautodetect'}
        self.assertEquals(kern_01kernel.KERNEL_INFO, expected)

    def test_get_node_zones(self):
        ret = kern_01kernel.get_node_zones("DMA32", 0)
        expected = ("Node 0, zone DMA32 2900 1994 2422 4791 3090 1788 886 290 "
                    "21 0 0")
        self.assertEquals(ret, expected)

    def test_get_numa_nodes(self):
        ret = kern_01kernel.get_numa_nodes()
        expected = [0, 1]
        self.assertEquals(ret, expected)

    @mock.patch.object(kern_01kernel, "KERNEL_INFO", {})
    def test_get_systemd_info(self):
        kern_01kernel.get_systemd_info()
        self.assertEquals(kern_01kernel.KERNEL_INFO,
                          {'systemd': {'CPUAffinity':
                                       '0-7,32-39'}})

    @mock.patch.object(kern_01kernel, "KERNEL_INFO", {})
    def test_check_mallocinfo_good_node(self):
        kern_01kernel.check_mallocinfo(0, "Normal", "node0-normal")
        self.assertEquals(kern_01kernel.KERNEL_INFO, {})

    @mock.patch.object(kern_01kernel, "KERNEL_INFO", {})
    def test_check_mallocinfo_bad_node(self):
        kern_01kernel.check_mallocinfo(1, "Normal", "node1-normal")
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
        self.assertEquals(kern_01kernel.KERNEL_INFO, expected)

    @mock.patch.object(kern_01kernel, "KERNEL_INFO", {})
    def test_check_nodes_memory(self):
        kern_01kernel.check_nodes_memory("Normal")
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
                                       format(kern_01kernel.BUDDY_INFO))
                                      ]}}
        self.assertEquals(kern_01kernel.KERNEL_INFO, expected)

    @mock.patch.object(kern_01kernel, "KERNEL_INFO", {})
    def test_get_slab_major_consumers(self):
        kern_01kernel.get_slab_major_consumers()
        expected = {"memory-checks":
                    {'slab (top 5)': ['buffer_head (3714895.9453125k)',
                                      'radix_tree_node (2426487.4921875k)',
                                      'vm_area_struct (45507.8125k)',
                                      'Acpi-Operand (14375.8125k)',
                                      'anon_vma (8167.96875k)']}
                    }
        self.assertEquals(kern_01kernel.KERNEL_INFO, expected)
