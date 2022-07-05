import os
import tempfile

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

    def test_systemd_config(self):
        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(DATA_ROOT=dtmp)
            path = os.path.join(dtmp, 'etc/systemd/system.conf')
            os.makedirs(os.path.dirname(path))
            with open(path, 'w') as fd:
                fd.write("[Manager]\n")
                fd.write("#CPUAffinity=1 2\n")
                fd.write("CPUAffinity=0-7,32-39\n")

            self.assertEqual(SystemdConfig().get('CPUAffinity'), '0-7,32-39')
            self.assertEqual(SystemdConfig().get('CPUAffinity',
                                                 expand_to_list=True),
                             [0, 1, 2, 3, 4, 5, 6, 7, 32, 33, 34, 35, 36, 37,
                              38, 39])
            self.assertTrue(SystemdConfig().cpuaffinity_enabled)

            with open(path, 'w') as fd:
                fd.write("[Manager]\n")
                fd.write("#CPUAffinity=1 2\n")
                fd.write("CPUAffinity=0 1 2 3 8 9 10 11\n")

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
                new=utils.is_def_filter('kernlog_checks.yaml'))
    def test_stacktraces(self):
        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(DATA_ROOT=dtmp)
            os.makedirs(os.path.join(dtmp, 'var/log'))
            klog = os.path.join(dtmp, 'var/log/kern.log')
            with open(klog, 'w') as fd:
                fd.write(KERNLOG_STACKTRACE)

            YScenarioChecker()()

        msg = ('1 reports of stacktraces in kern.log - please check.')
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('kernlog_checks.yaml'))
    def test_oom_killer_invoked(self):
        YScenarioChecker()()
        msg = ('1 reports of oom-killer invoked in kern.log - please check.')
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('kernlog_checks.yaml'))
    def test_nf_conntrack_full(self):
        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(DATA_ROOT=dtmp)
            os.makedirs(os.path.join(dtmp, 'var/log'))
            klog = os.path.join(dtmp, 'var/log/kern.log')
            with open(klog, 'w') as fd:
                fd.write(KERNLOG_NF_CONNTRACK_FULL)

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

    @mock.patch('hotsos.core.host_helpers.HostNetworkingHelper.'
                'host_interfaces_all',
                [NetworkPort('tap0e778df8-ca', None, None, None, None)])
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('kernlog_checks.yaml'))
    def test_over_mtu_dropped_packets(self):
        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(DATA_ROOT=dtmp)
            logfile = os.path.join(dtmp, ('var/log/kern.log'))
            os.makedirs(os.path.dirname(logfile))
            with open(logfile, 'w') as fd:
                fd.write(EVENTS_KERN_LOG)

            YScenarioChecker()()
            msg = ('This host is reporting over-mtu dropped packets for (1) '
                   'interfaces. See kern.log for full details.')
            issues = list(IssuesStore().load().values())[0]
            self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.plugins.kernel.kernlog.events.log')
    @mock.patch('hotsos.core.plugins.kernel.kernlog.common.CLIHelper')
    @mock.patch('hotsos.core.plugins.kernel.kernlog.common.'
                'HostNetworkingHelper.host_interfaces_all',
                [NetworkPort('br-int', None, None, None, None),
                 NetworkPort('tap0e778df8-ca', None, None, None, None)])
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('kernlog_checks.yaml'))
    def test_over_mtu_dropped_packets_w_ovs_ports(self, mock_cli, mock_log):
        mock_cli.return_value = mock.MagicMock()
        # include trailing newline since cli would give that
        mock_cli.return_value.ovs_vsctl_list_br.return_value = ['br-int\n']
        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(DATA_ROOT=dtmp)
            logfile = os.path.join(dtmp, ('var/log/kern.log'))
            os.makedirs(os.path.dirname(logfile))
            with open(logfile, 'w') as fd:
                fd.write(EVENTS_KERN_LOG)
                ovs_port = EVENTS_KERN_LOG.splitlines(keepends=True)[-1]
                # add one ovs-port line
                fd.write(ovs_port.replace('tape901c8af-fb', 'br-int'))

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
