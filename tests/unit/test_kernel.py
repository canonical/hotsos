from unittest import mock

from . import utils

from hotsos.plugin_extensions.kernel import summary
from hotsos.core.config import setup_config
from hotsos.core.issues.utils import IssuesStore
from hotsos.core.plugins.kernel.config import SystemdConfig
from hotsos.core.plugins.kernel import CallTraceManager
from hotsos.core.ycheck.scenarios import YScenarioChecker

from hotsos.core.host_helpers.network import NetworkPort
from hotsos.core.plugins.kernel.memory import (
    BuddyInfo,
    SlabInfo,
    MallocInfo,
    MemoryChecks,
)


EVENTS_KERN_LOG = r"""
May  6 10:49:21 compute4 kernel: [13502680.515977] tap0e778df8-ca: dropped over-mtu packet: 8950 > 1450
May  6 10:49:21 compute4 kernel: [13502680.516145] tap0e778df8-ca: dropped over-mtu packet: 8950 > 1450
May  6 10:49:21 compute4 kernel: [13502680.519706] tap0e778df8-ca: dropped over-mtu packet: 8950 > 1450
May  6 10:49:21 compute4 kernel: [13502680.523590] tap0e778df8-ca: dropped over-mtu packet: 8950 > 1450
May  6 10:49:21 compute4 kernel: [13502680.524071] tap0e778df8-ca: dropped over-mtu packet: 8950 > 1450
May  6 17:24:13 compute4 kernel: [13526370.254883] tape901c8af-fb: dropped over-mtu packet: 2776 > 1450
May  6 17:24:13 compute4 kernel: [13526370.254940] tape901c8af-fb: dropped over-mtu packet: 2776 > 1450
May  6 17:24:13 compute4 kernel: [13526370.489870] tape901c8af-fb: dropped over-mtu packet: 1580 > 1450
May  6 17:24:13 compute4 kernel: [13526370.528055] tape901c8af-fb: dropped over-mtu packet: 4170 > 1450
May  6 17:24:13 compute4 kernel: [13526370.528138] tape901c8af-fb: dropped over-mtu packet: 4170 > 1450
May  6 17:24:13 compute4 kernel: [13526370.528408] tape901c8af-fb: dropped over-mtu packet: 2059 > 1450
May  6 17:24:13 compute4 kernel: [13526370.730586] tape901c8af-fb: dropped over-mtu packet: 1460 > 1450
May  6 17:24:13 compute4 kernel: [13526370.730634] tape901c8af-fb: dropped over-mtu packet: 1460 > 1450
May  6 17:24:13 compute4 kernel: [13526370.730659] tape901c8af-fb: dropped over-mtu packet: 1460 > 1450
May  6 17:24:13 compute4 kernel: [13526370.730681] tape901c8af-fb: dropped over-mtu packet: 1460 > 1450
"""  # noqa

DISK_FAILING_KERN_LOG = r"""
Jun 11 06:51:39 bronzor kernel: [  725.797102] sd 0:0:9:0: [sdk] tag#915 CDB: Write(16) 8a 00 00 00 00 00 07 c8 fa cb 00 00 00 65 00 00
Jun 11 06:51:39 bronzor kernel: [  725.995102] blk_update_request: critical medium error, dev sdk, sector 130611915 op 0x1:(WRITE) flags 0x0 phys_seg 13 prio class 0
"""  # noqa

# add one ovs-port line
EVENTS_KERN_LOG_W_OVS_PORTS = (EVENTS_KERN_LOG.splitlines(keepends=True)[-1].
                               replace('tape901c8af-fb', 'br-int'))
EVENTS_KERN_LOG_W_OVS_PORTS = EVENTS_KERN_LOG + EVENTS_KERN_LOG_W_OVS_PORTS


KERNLOG_NF_CONNTRACK_FULL = r"""
Jun  8 10:48:13 compute4 kernel: [1694413.621694] nf_conntrack: nf_conntrack: table full, dropping packet
"""  # noqa

KERNLOG_STACKTRACE = r"""
May  6 10:49:21 tututu kernel: [ 4965.415911] CPU: 1 PID: 4465 Comm: insmod Tainted: P           OE   4.13.0-rc5 #1
May  6 10:49:21 tututu kernel: [ 4965.415912] Hardware name: QEMU Standard PC (i440FX + PIIX, 1996), BIOS 1.10.2-1.fc26 04/01/2014
May  6 10:49:21 tututu kernel: [ 4965.415913] Call Trace:
May  6 10:49:21 tututu kernel: [ 4965.415920]  dump_stack+0x63/0x8b
May  6 10:49:21 tututu kernel: [ 4965.415923]  do_init_module+0x8d/0x1e9
May  6 10:49:21 tututu kernel: [ 4965.415926]  load_module+0x21bd/0x2b10
May  6 10:49:21 tututu kernel: [ 4965.415929]  SYSC_finit_module+0xfc/0x120
May  6 10:49:21 tututu kernel: [ 4965.415931]  ? SYSC_finit_module+0xfc/0x120
May  6 10:49:21 tututu kernel: [ 4965.415934]  SyS_finit_module+0xe/0x10
May  6 10:49:21 tututu kernel: [ 4965.415937]  entry_SYSCALL_64_fastpath+0x1a/0xa5
May  6 10:49:21 tututu kernel: [ 4965.415939] RIP: 0033:0x7fab36d717a9
"""  # noqa

KERNLOG_BCACHE_DEADLOCK = r"""
Jun 11 06:51:39 bronzor kernel: [  725.795102] INFO: task bcache-register:2330 blocked for more than 120 seconds.
Jun 11 06:51:39 bronzor kernel: [  726.146000]       Not tainted 4.15.0-176-generic #185
Jun 11 06:51:39 bronzor kernel: [  726.391338] "echo 0 > /proc/sys/kernel/hung_task_timeout_secs" disables this message.
Jun 11 06:51:39 bronzor kernel: [  726.771988] bcache-register D    0  2330   2328 0x00000320
Jun 11 06:51:39 bronzor kernel: [  726.771991] Call Trace:
Jun 11 06:51:39 bronzor kernel: [  726.771997]  __schedule+0x24e/0x890
Jun 11 06:51:39 bronzor kernel: [  726.771999]  schedule+0x2c/0x80
Jun 11 06:51:39 bronzor kernel: [  726.772024]  closure_sync+0x18/0x90 [bcache]
Jun 11 06:51:39 bronzor kernel: [  726.772031]  bch_journal+0x123/0x380 [bcache]
Jun 11 06:51:39 bronzor kernel: [  726.772036]  ? __switch_to_asm+0x35/0x70
Jun 11 06:51:39 bronzor kernel: [  726.772042]  bch_journal_meta+0x47/0x70 [bcache]
Jun 11 06:51:39 bronzor kernel: [  726.772045]  ? __switch_to+0x309/0x4e0
Jun 11 06:51:39 bronzor kernel: [  726.772046]  ? __switch_to_asm+0x35/0x70
Jun 11 06:51:39 bronzor kernel: [  726.772047]  ? __switch_to_asm+0x41/0x70
Jun 11 06:51:39 bronzor kernel: [  726.772048]  ? __switch_to_asm+0x35/0x70
Jun 11 06:51:39 bronzor kernel: [  726.772050]  ? __schedule+0x256/0x890
Jun 11 06:51:39 bronzor kernel: [  726.772051]  ? _cond_resched+0x19/0x40
Jun 11 06:51:39 bronzor kernel: [  726.772053]  ? mutex_lock+0x12/0x40
Jun 11 06:51:39 bronzor kernel: [  726.772057]  bch_btree_set_root+0x1c2/0x1f0 [bcache]
Jun 11 06:51:39 bronzor kernel: [  726.772074]  btree_split+0x69a/0x700 [bcache]
Jun 11 06:51:39 bronzor kernel: [  726.772077]  ? __switch_to_asm+0x35/0x70
Jun 11 06:51:39 bronzor kernel: [  726.772080]  ? __switch_to_asm+0x41/0x70
Jun 11 06:51:39 bronzor kernel: [  726.772082]  ? __switch_to_asm+0x35/0x70
Jun 11 06:51:39 bronzor kernel: [  726.772086]  ? __switch_to+0x309/0x4e0
Jun 11 06:51:39 bronzor kernel: [  726.772089]  ? __switch_to+0x309/0x4e0
Jun 11 06:51:39 bronzor kernel: [  726.772091]  ? __switch_to_asm+0x35/0x70
Jun 11 06:51:39 bronzor kernel: [  726.772092]  ? __switch_to_asm+0x41/0x70
Jun 11 06:51:39 bronzor kernel: [  726.772093]  ? __switch_to_asm+0x35/0x70
Jun 11 06:51:39 bronzor kernel: [  726.772096]  bch_btree_insert_node+0x340/0x410 [bcache]
Jun 11 06:51:39 bronzor kernel: [  726.772100]  btree_split+0x551/0x700 [bcache]
Jun 11 06:51:39 bronzor kernel: [  726.772103]  ? __switch_to_asm+0x35/0x70
Jun 11 06:51:39 bronzor kernel: [  726.772105]  ? __switch_to_asm+0x41/0x70
Jun 11 06:51:39 bronzor kernel: [  726.772107]  ? __switch_to_asm+0x35/0x70
Jun 11 06:51:39 bronzor kernel: [  726.772111]  ? __switch_to+0x309/0x4e0
Jun 11 06:51:39 bronzor kernel: [  726.772114]  ? __switch_to+0x309/0x4e0
Jun 11 06:51:39 bronzor kernel: [  726.772115]  ? __switch_to_asm+0x35/0x70
Jun 11 06:51:39 bronzor kernel: [  726.772129]  ? __switch_to_asm+0x41/0x70
Jun 11 06:51:39 bronzor kernel: [  726.772130]  ? __switch_to_asm+0x35/0x70
Jun 11 06:51:39 bronzor kernel: [  726.772137]  bch_btree_insert_node+0x340/0x410 [bcache]
Jun 11 06:51:39 bronzor kernel: [  726.772144]  btree_insert_fn+0x24/0x40 [bcache]
Jun 11 06:51:39 bronzor kernel: [  726.772151]  bch_btree_map_nodes_recurse+0x54/0x190 [bcache]
Jun 11 06:51:39 bronzor kernel: [  726.772159]  ? bch_btree_insert_check_key+0x1f0/0x1f0 [bcache]
Jun 11 06:51:39 bronzor kernel: [  726.772164]  ? _cond_resched+0x19/0x40
Jun 11 06:51:39 bronzor kernel: [  726.772167]  ? down_write+0x12/0x40
Jun 11 06:51:39 bronzor kernel: [  726.772175]  ? bch_btree_node_get+0x80/0x260 [bcache]
Jun 11 06:51:39 bronzor kernel: [  726.772179]  ? up_read+0x30/0x30
Jun 11 06:51:39 bronzor kernel: [  726.772185]  bch_btree_map_nodes_recurse+0x112/0x190 [bcache]
Jun 11 06:51:39 bronzor kernel: [  726.772190]  ? bch_btree_insert_check_key+0x1f0/0x1f0 [bcache]
Jun 11 06:51:39 bronzor kernel: [  726.772198]  __bch_btree_map_nodes+0xf0/0x150 [bcache]
Jun 11 06:51:39 bronzor kernel: [  726.772205]  ? bch_btree_insert_check_key+0x1f0/0x1f0 [bcache]
Jun 11 06:51:39 bronzor kernel: [  726.772212]  bch_btree_insert+0xf9/0x170 [bcache]
Jun 11 06:51:39 bronzor kernel: [  726.772215]  ? wait_woken+0x80/0x80
Jun 11 06:51:39 bronzor kernel: [  726.772222]  bch_journal_replay+0x220/0x2f0 [bcache]
Jun 11 06:51:39 bronzor kernel: [  726.772224]  ? try_to_wake_up+0x59/0x4b0
Jun 11 06:51:39 bronzor kernel: [  726.772229]  ? kthread_create_on_node+0x46/0x70
Jun 11 06:51:40 bronzor kernel: [  726.772238]  run_cache_set+0x5c6/0x970 [bcache]
Jun 11 06:51:40 bronzor kernel: [  726.772246]  register_bcache+0xd04/0x1110 [bcache]
Jun 11 06:51:40 bronzor kernel: [  726.772253]  ? register_bcache+0xd04/0x1110 [bcache]
Jun 11 06:51:40 bronzor kernel: [  726.772256]  kobj_attr_store+0x12/0x20
Jun 11 06:51:40 bronzor kernel: [  726.772257]  ? kobj_attr_store+0x12/0x20
Jun 11 06:51:40 bronzor kernel: [  726.772259]  sysfs_kf_write+0x3c/0x50
Jun 11 06:51:40 bronzor kernel: [  726.772261]  kernfs_fop_write+0x125/0x1a0
Jun 11 06:51:40 bronzor kernel: [  726.772263]  __vfs_write+0x1b/0x40
Jun 11 06:51:40 bronzor kernel: [  726.772265]  vfs_write+0xb1/0x1a0
Jun 11 06:51:40 bronzor kernel: [  726.772267]  SyS_write+0x5c/0xe0
Jun 11 06:51:40 bronzor kernel: [  726.772270]  do_syscall_64+0x73/0x130
Jun 11 06:51:40 bronzor kernel: [  726.772273]  entry_SYSCALL_64_after_hwframe+0x41/0xa6
Jun 11 06:51:40 bronzor kernel: [  726.772275] RIP: 0033:0x7efdb30af104
Jun 11 06:51:40 bronzor kernel: [  726.772276] RSP: 002b:00007fff9649a2b8 EFLAGS: 00000246 ORIG_RAX: 0000000000000001
Jun 11 06:51:40 bronzor kernel: [  726.772278] RAX: ffffffffffffffda RBX: 000000000000000b RCX: 00007efdb30af104
Jun 11 06:51:40 bronzor kernel: [  726.772279] RDX: 000000000000000b RSI: 00005625a6c2c260 RDI: 0000000000000003
Jun 11 06:51:40 bronzor kernel: [  726.772281] RBP: 00005625a6c2c260 R08: 0000000000000000 R09: 000000000000000a
Jun 11 06:51:40 bronzor kernel: [  726.772282] R10: 00000000fffffff6 R11: 0000000000000246 R12: 00007fff9649a350
Jun 11 06:51:40 bronzor kernel: [  726.772283] R13: 000000000000000b R14: 00007efdb33872a0 R15: 00007efdb3386760
"""  # noqa



FAKE_AMD_LSCPU = r"""
Vendor ID:                       AuthenticAMD
CPU family:                      23
Model:                           49
Model name:                      AMD EPYC 7502 32-Core Processor
"""  # noqa


class TestKernelBase(utils.BaseTestCase):
    def setUp(self):
        super().setUp()
        setup_config(PLUGIN_NAME='kernel')


class TestKernelCallTraceManager(TestKernelBase):

    def test_CallTraceManager_handler(self):
        for killer in CallTraceManager().oom_killer:
            self.assertEqual(killer.procname, 'kworker/0:0')
            self.assertEqual(killer.pid, '955')

        heuristics = CallTraceManager().oom_killer.heuristics
        # one per zone
        self.assertEqual(len(heuristics), 3)
        for h in heuristics:
            if h.zone == 'DMA':
                self.assertEqual(h(),
                                 ['Node 0 zone DMA free pages 15908 below min '
                                  '268'])
            elif h.zone == 'Normal':
                self.assertEqual(h(),
                                 ['Node 0 zone Normal free pages 20564 below '
                                  'low 20652'])
            else:
                self.assertEqual(h(), [])


class TestKernelInfo(TestKernelBase):

    @utils.create_test_files({'etc/systemd/system.conf':
                              ('[Manager]\n'
                               '#CPUAffinity=1 2\n'
                               'CPUAffinity=0-7,32-39\n')})
    def test_systemd_config_ranges(self):
        self.assertEqual(SystemdConfig().get('CPUAffinity'), '0-7,32-39')
        self.assertEqual(SystemdConfig().get('CPUAffinity',
                                             expand_to_list=True),
                         [0, 1, 2, 3, 4, 5, 6, 7, 32, 33, 34, 35, 36, 37,
                          38, 39])
        self.assertTrue(SystemdConfig().cpuaffinity_enabled)

    @utils.create_test_files({'etc/systemd/system.conf':
                              ('[Manager]\n'
                               '#CPUAffinity=1 2\n'
                               'CPUAffinity=0 1 2 3 8 9 10 11\n')})
    def test_systemd_config_expanded(self):
        self.assertEqual(SystemdConfig().get('CPUAffinity'),
                         '0 1 2 3 8 9 10 11')

    @mock.patch('hotsos.core.plugins.kernel.config.SystemdConfig.get',
                lambda *args, **kwargs: '0-7,32-39')
    def test_info(self):
        inst = summary.KernelSummary()
        expected = {'boot': 'ro',
                    'cpu': {'cpufreq-scaling-governor': 'unknown',
                            'smt': 'disabled', 'vendor': 'genuineintel'},
                    'systemd': {'CPUAffinity': '0-7,32-39'},
                    'version': '5.4.0-97-generic'}
        self.assertTrue(inst.plugin_runnable)
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual, expected)


class TestKernelMemoryInfo(TestKernelBase):

    def test_numa_nodes(self):
        ret = BuddyInfo().nodes
        expected = [0]
        self.assertEqual(ret, expected)

    def test_get_node_zones(self):
        ret = BuddyInfo().get_node_zones("DMA32", 0)
        expected = ("Node 0, zone DMA32 1127 453 112 65 27 7 13 6 5 30 48")
        self.assertEqual(ret, expected)

    def test_mallocinfo(self):
        m = MallocInfo(0, "Normal")
        self.assertEqual(m.empty_order_tally, 19)
        self.assertEqual(m.high_order_seq, 2)
        bsizes = {10: 0,
                  9: 0,
                  8: 2,
                  7: 4,
                  6: 14,
                  5: 35,
                  4: 222,
                  3: 1135,
                  2: 316,
                  1: 101,
                  0: 145}
        self.assertEqual(m.block_sizes_available, bsizes)

    def test_slab_major_consumers(self):
        top5 = SlabInfo(filter_names=[r"\S*kmalloc"]).major_consumers
        expected = ['buffer_head (87540.6796875k)',
                    'anon_vma_chain (9068.0k)',
                    'radix_tree_node (50253.65625k)',
                    'Acpi-State (5175.703125k)',
                    'vmap_area (2700.0k)']
        self.assertEqual(top5, expected)


class TestKernelScenarioChecks(TestKernelBase):

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('kernlog_calltrace.yaml'))
    @utils.create_test_files({'var/log/kern.log': KERNLOG_STACKTRACE})
    def test_stacktraces(self):
        YScenarioChecker()()
        msg = ('1 reports of stacktraces in kern.log - please check.')
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.plugins.kernel.KernelBase')
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('kernlog_calltrace.yaml'))
    @utils.create_test_files({'var/log/kern.log': KERNLOG_BCACHE_DEADLOCK})
    def test_bcache_deadlock(self, mock_kernelbase):
        mock_kernelbase.return_value = mock.MagicMock()
        mock_kernelbase.return_value.version = '5.3'
        YScenarioChecker()()
        msg = ("Bcache cache set registration deadlock has occurred. "
               "This is caused by a bug that has been fixed "
               "in kernel 5.15.11 (current is 5.3). "
               "See https://www.spinics.net/lists/stable/msg566639.html "
               "for full detail.")

        issues = list(IssuesStore().load().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('kernlog_calltrace.yaml'))
    def test_oom_killer_invoked(self):
        YScenarioChecker()()
        msg = ('1 reports of oom-killer invoked in kern.log - please check.')
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('network.yaml'))
    @utils.create_test_files({'var/log/kern.log': KERNLOG_NF_CONNTRACK_FULL})
    def test_nf_conntrack_full(self):
        YScenarioChecker()()
        msg = ("1 reports of 'nf_conntrack: table full' detected in "
               "kern.log - please check.")
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.plugins.kernel.KernelBase')
    @mock.patch('hotsos.core.host_helpers.CLIHelper')
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('amd_iommu_pt.yaml'))
    def test_amd_iommu_pt_fail(self, mock_cli, mock_kernel):
        mock_cli.return_value = mock.MagicMock()
        mock_cli.return_value.lscpu.return_value = \
            FAKE_AMD_LSCPU.splitlines(keepends=True)

        mock_kernel.return_value = mock.MagicMock()
        mock_kernel.return_value.boot_parameters = \
            ['intel_iommu=on']

        YScenarioChecker()()
        msg = ('This host is using an AMD AMD EPYC 7502 32-Core Processor cpu '
               'but is not using iommu passthrough mode (e.g. set iommu=pt in '
               'boot parameters) which is recommended in order to get the '
               'best performance e.g. for networking.')
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.plugins.kernel.KernelBase')
    @mock.patch('hotsos.core.host_helpers.CLIHelper')
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('amd_iommu_pt.yaml'))
    def test_amd_iommu_pt_pass(self, mock_cli, mock_kernel):
        mock_cli.return_value = mock.MagicMock()
        mock_cli.return_value.lscpu.return_value = \
            FAKE_AMD_LSCPU.splitlines(keepends=True)

        mock_kernel.return_value = mock.MagicMock()
        mock_kernel.return_value.boot_parameters = \
            ['intel_iommu=on', 'iommu=pt']

        YScenarioChecker()()
        issues = list(IssuesStore().load().values())
        self.assertEqual(issues, [])

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('network.yaml'))
    @utils.create_test_files({'var/log/kern.log': EVENTS_KERN_LOG})
    def test_over_mtu_dropped_packets(self):
        with mock.patch('hotsos.core.host_helpers.HostNetworkingHelper.'
                        'host_interfaces_all',
                        [NetworkPort('tap0e778df8-ca', None, None, None,
                                     None)]):
            YScenarioChecker()()
            msg = ('This host is reporting over-mtu dropped packets for (1) '
                   'interfaces. See kern.log for full details.')
            issues = list(IssuesStore().load().values())[0]
            self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.plugins.kernel.kernlog.events.log')
    @mock.patch('hotsos.core.plugins.kernel.kernlog.common.CLIHelper')
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('network.yaml'))
    @utils.create_test_files({'var/log/kern.log': EVENTS_KERN_LOG_W_OVS_PORTS})
    def test_over_mtu_dropped_packets_w_ovs_ports(self, mock_cli, mock_log):
        mock_cli.return_value = mock.MagicMock()
        # include trailing newline since cli would give that
        mock_cli.return_value.ovs_vsctl_list_br.return_value = ['br-int\n']

        with mock.patch('hotsos.core.plugins.kernel.kernlog.common.'
                        'HostNetworkingHelper.host_interfaces_all',
                        [NetworkPort('br-int', None, None, None, None),
                         NetworkPort('tap0e778df8-ca', None, None, None,
                                     None)]):
            YScenarioChecker()()
            mock_log.assert_has_calls([mock.call.debug(
                                        "excluding ovs bridge %s", 'br-int')])
            msg = ('This host is reporting over-mtu dropped packets for (1) '
                   'interfaces. See kern.log for full details.')
            issues = list(IssuesStore().load().values())[0]
            self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch.object(MemoryChecks, 'max_contiguous_unavailable_block_sizes',
                       1)
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('memory.yaml'))
    def test_memory(self):
        YScenarioChecker()()
        msg = ('The following numa nodes have limited high order memory '
               'available: node0-normal. At present the top 5 highest '
               'consumers of memory are: buffer_head (87540.6796875k), '
               'anon_vma_chain (9068.0k), radix_tree_node (50253.65625k), '
               'Acpi-State (5175.703125k), vmap_area (2700.0k). See '
               'summary or /proc/buddyinfo for more info.')
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.plugins.kernel.memory.VMStat')
    @mock.patch.object(MemoryChecks, 'max_contiguous_unavailable_block_sizes',
                       1)
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('memory.yaml'))
    def test_memory_w_compaction_failures(self, mock_vmstat):
        mock_vmstat.return_value = mock.MagicMock()
        mock_vmstat.return_value.compact_success = 10001
        mock_vmstat.return_value.compaction_failures_percent = 11
        YScenarioChecker()()
        msg1 = ('The following numa nodes have limited high order memory '
                'available: node0-normal. At present the top 5 highest '
                'consumers of memory are: buffer_head (87540.6796875k), '
                'anon_vma_chain (9068.0k), radix_tree_node (50253.65625k), '
                'Acpi-State (5175.703125k), vmap_area (2700.0k). See '
                'summary or /proc/buddyinfo for more info.')
        msg2 = ('Memory compaction failures are at 11% of successes. This can '
                'suggest that there are insufficient high-order memory blocks '
                'available and the kernel is unable form larger blocks on '
                'request which can slow things down. See vmstat output for '
                'more detail.')
        issues = list(IssuesStore().load().values())[0]
        actual = sorted([issue['desc'] for issue in issues])
        self.assertEqual(actual, sorted([msg1, msg2]))

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('disk_failure.yaml'))
    @utils.create_test_files({'var/log/kern.log': DISK_FAILING_KERN_LOG})
    def test_failing_disk(self):
        YScenarioChecker()()
        msg = ('critical medium error detected in '
               'kern.log for device sdk. This implies '
               'that this disk has a hardware issue!')
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])
