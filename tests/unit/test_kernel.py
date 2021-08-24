import os

import mock

import utils

from plugins.kernel.pyparts import (
    info,
    memory,
    network,
)


class TestKernelBase(utils.BaseTestCase):
    def setUp(self):
        super().setUp()
        os.environ["PLUGIN_NAME"] = "kernel"


class TestKernelPluginPartKernelInfo(TestKernelBase):

    def test_get_cmdline_info(self):
        inst = info.KernelGeneralChecks()
        inst.get_cmdline_info()
        expected = {'boot': 'ro'}
        self.assertEquals(inst.output, expected)

    def test_get_systemd_info(self):
        inst = info.KernelGeneralChecks()
        inst.get_systemd_info()
        self.assertEquals(inst.output,
                          {'systemd': {'CPUAffinity': '0-7,32-39'}})


class TestKernelPluginPartKernelMemoryInfo(TestKernelBase):

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
        expected = {'memory-checks': {
                        'node1-normal': [
                            {'zones': {
                                10: 0,
                                9: 0,
                                8: 0,
                                7: 0,
                                6: 0,
                                5: 0,
                                4: 0,
                                3: 1,
                                2: 54089,
                                1: 217700,
                                0: 220376}}]}}
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
        expected = {'memory-checks': {
                        'slab-top-consumers': [
                            'buffer_head (44081.2734375k)',
                            'anon_vma_chain (6580.0k)',
                            'anon_vma (5617.390625k)',
                            'radix_tree_node (30156.984375k)',
                            'vmap_area (1612.0k)']
                        }
                    }
        self.assertEquals(inst.output, expected)


class TestKernelPluginPartKernelNetwork(TestKernelBase):

    @mock.patch.object(network.issues_utils, "add_issue")
    def test_run_network_checks(self, mock_add_issue):
        issues = []

        def fake_add_issue(issue):
            issues.append(issue)

        mock_add_issue.side_effect = fake_add_issue
        expected = {'over-mtu-dropped-packets':
                    {'tap0906171f-17': 5}}
        inst = network.KernelNetworkChecks()
        inst()
        self.assertTrue(mock_add_issue.called)
        self.assertTrue(len(issues) == 2)
        self.assertEquals(inst.output, expected)


class TestKernelPluginPartKernelOOM(TestKernelBase):

    @mock.patch.object(memory.issues_utils, "add_issue")
    def test_run_memory_checks(self, mock_add_issue):
        issues = []

        def fake_add_issue(issue):
            issues.append(issue)

        mock_add_issue.side_effect = fake_add_issue
        expected = {'oom-event':
                    'Aug  3 08:32:23'}
        inst = memory.KernelOOMChecks()
        inst()
        self.assertTrue(mock_add_issue.called)
        self.assertTrue(len(issues) == 1)
        self.assertEquals(inst.output, expected)
