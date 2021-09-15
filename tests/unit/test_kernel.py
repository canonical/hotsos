import os

import mock

import utils

from plugins.kernel.pyparts import (
    info,
    memory,
    log_event_checks,
)
from core.host_helpers import NetworkPort
from core.issues import issue_types


class TestKernelBase(utils.BaseTestCase):
    def setUp(self):
        super().setUp()
        os.environ["PLUGIN_NAME"] = "kernel"


class TestKernelPluginPartKernelInfo(TestKernelBase):

    def test_info(self):
        inst = info.KernelGeneralChecks()
        inst()
        expected = {'boot': 'ro',
                    'systemd': {'CPUAffinity': '0-7,32-39'},
                    'version': '5.4.0-80-generic'}
        self.assertTrue(inst.plugin_runnable)
        self.assertEqual(inst.output, expected)


class TestKernelPluginPartKernelMemoryInfo(TestKernelBase):

    def test_numa_nodes(self):
        ret = memory.KernelMemoryChecks().numa_nodes
        expected = [0, 1]
        self.assertEqual(ret, expected)

    def test_get_node_zones(self):
        inst = memory.KernelMemoryChecks()
        ret = inst.get_node_zones("DMA32", 0)
        expected = ("Node 0, zone DMA32 2900 1994 2422 4791 3090 1788 886 290 "
                    "21 0 0")
        self.assertTrue(inst.plugin_runnable)
        self.assertEqual(ret, expected)

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
        self.assertEqual(inst.output, expected)

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
        self.assertEqual(inst.output, expected)

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
        self.assertEqual(inst.output, expected)


class TestKernelPluginPartKernelLogEventChecks(TestKernelBase):

    @mock.patch.object(log_event_checks.issue_utils, "add_issue")
    def test_run_log_event_checks(self, mock_add_issue):
        issues = []

        def fake_add_issue(issue):
            issues.append(issue)

        mock_add_issue.side_effect = fake_add_issue
        expected = {'over-mtu-dropped-packets':
                    {'tap0906171f-17': 5},
                    'oom-killer-invoked': 'Aug  3 08:32:23'}
        inst = log_event_checks.KernelLogEventChecks()
        inst()
        self.assertTrue(mock_add_issue.called)
        types = {}
        for issue in issues:
            t = type(issue)
            if t in types:
                types[t] += 1
            else:
                types[t] = 1

        self.assertEqual(len(issues), 4)
        self.assertEqual(types[issue_types.KernelError], 1)
        self.assertEqual(types[issue_types.MemoryWarning], 1)
        self.assertEqual(types[issue_types.NetworkWarning], 2)
        self.assertTrue(inst.plugin_runnable)
        self.assertEqual(inst.output, expected)

    @mock.patch.object(log_event_checks, 'CLIHelper')
    @mock.patch.object(log_event_checks, 'HostNetworkingHelper')
    def test_over_mtu_dropped_packets(self, mock_nethelper, mock_clihelper):
        mock_ch = mock.MagicMock()
        mock_clihelper.return_value = mock_ch
        # include trailing newline since cli would give that
        mock_ch.ovs_vsctl_list_br.return_value = ['br-int\n']

        mock_nh = mock.MagicMock()
        mock_nethelper.return_value = mock_nh
        p1 = NetworkPort('br-int', None, None, None, None)
        p2 = NetworkPort('tap7e105503-64', None, None, None, None)
        mock_nh.host_interfaces_all = [p1, p2]

        expected = {'tap7e105503-64': 1}
        inst = log_event_checks.KernelLogEventChecks()

        mock_result1 = mock.MagicMock()
        mock_result1.get.return_value = 'br-int'
        mock_result2 = mock.MagicMock()
        mock_result2.get.return_value = 'tap7e105503-64'

        event = {'results': [mock_result1, mock_result2]}
        ret = inst.over_mtu_dropped_packets(event)
        self.assertTrue(inst.plugin_runnable)
        self.assertEqual(ret, expected)
