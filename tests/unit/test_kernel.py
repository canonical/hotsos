import os
import tempfile

import mock

from . import utils

from hotsos.plugin_extensions.kernel import (
    summary,
    memory,
    log_event_checks,
)
from hotsos.core.config import setup_config
from hotsos.core.plugins.kernel import SystemdConfig
from hotsos.core.ycheck.events import EventCheckResult
from hotsos.core.ycheck.scenarios import YScenarioChecker

from hotsos.core.host_helpers import NetworkPort


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

KERNLOG_OOM = r"""
Aug  3 10:31:24 compute4 kernel: [5490487.294657] Memory cgroup out of memory: Kill process 55438 (ruby) score 1116 or sacrifice child
Aug  3 10:31:24 compute4 kernel: [5490487.297212] Killed process 55438 (ruby) total-vm:1771344kB, anon-rss:1469448kB, file-rss:4992kB
Aug  3 08:32:23 compute4 kernel: [5489652.470650] nice invoked oom-killer: gfp_mask=0x24000c0, order=0, oom_score_adj=876
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


class TestKernelBase(utils.BaseTestCase):
    def setUp(self):
        super().setUp()
        setup_config(PLUGIN_NAME='kernel')


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

    @mock.patch('hotsos.core.plugins.kernel.SystemdConfig.get',
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
        ret = memory.KernelMemoryChecks().numa_nodes
        expected = [0]
        self.assertEqual(ret, expected)

    def test_get_node_zones(self):
        inst = memory.KernelMemoryChecks()
        ret = inst.get_node_zones("DMA32", 0)
        expected = ("Node 0, zone DMA32 1127 453 112 65 27 7 13 6 5 30 48")
        self.assertTrue(inst.plugin_runnable)
        self.assertEqual(ret, expected)

    def test_check_mallocinfo(self):
        inst = memory.KernelMemoryChecks()
        ret = inst.check_mallocinfo(0, "Normal")
        self.assertIsNone(ret)

    def test_check_nodes_memory(self):
        inst = memory.KernelMemoryChecks()
        inst.check_nodes_memory("Normal")
        expected = {'memory-checks': "no issues found"}
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual, expected)

    def test_get_slab_major_consumers(self):
        inst = memory.KernelMemoryChecks()
        top5 = inst.get_slab_major_consumers()
        expected = ['buffer_head (87540.6796875k)',
                    'anon_vma_chain (9068.0k)',
                    'radix_tree_node (50253.65625k)',
                    'Acpi-State (5175.703125k)',
                    'vmap_area (2700.0k)']
        self.assertEqual(top5, expected)


class TestKernelLogEventChecks(TestKernelBase):

    @mock.patch('hotsos.core.host_helpers.HostNetworkingHelper.'
                'host_interfaces_all',
                [NetworkPort('tap0e778df8-ca', None, None, None, None)])
    @mock.patch('hotsos.core.issues.IssuesManager.add')
    def test_run_log_event_checks(self, mock_add_issue):
        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(DATA_ROOT=dtmp)
            logfile = os.path.join(dtmp, ('var/log/kern.log'))
            os.makedirs(os.path.dirname(logfile))
            with open(logfile, 'w') as fd:
                fd.write(EVENTS_KERN_LOG)

            raised_issues = []

            def fake_add_issue(issue, **_kwargs):
                raised_issues.append(issue)

            mock_add_issue.side_effect = fake_add_issue
            expected = {'over-mtu-dropped-packets':
                        {'tap0e778df8-ca': 5}}
            inst = log_event_checks.KernelLogEventChecks()
            # checks get run when we fetch the output so do that now
            actual = self.part_output_to_actual(inst.output)
            self.assertTrue(mock_add_issue.called)
            self.assertEqual(len(raised_issues), 1)
            self.assertTrue(inst.plugin_runnable)
            self.assertEqual(actual, expected)

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

        event = EventCheckResult(defs_section='section8',
                                 defs_event='over_mtu_dropped_packets',
                                 search_results=[mock_result1, mock_result2])
        ret = inst.over_mtu_dropped_packets(event)
        self.assertTrue(inst.plugin_runnable)
        self.assertEqual(ret, expected)


class TestKernelScenarioChecks(TestKernelBase):

    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('kernlog.yaml'))
    @mock.patch('hotsos.core.issues.IssuesManager.add')
    def test_stacktraces(self, mock_add_issue):
        raised_issues = []

        def fake_add_issue(issue, **_kwargs):
            raised_issues.append(issue)

        mock_add_issue.side_effect = fake_add_issue

        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(DATA_ROOT=dtmp)
            os.makedirs(os.path.join(dtmp, 'var/log'))
            klog = os.path.join(dtmp, 'var/log/kern.log')
            with open(klog, 'w') as fd:
                fd.write(KERNLOG_STACKTRACE)

            YScenarioChecker()()

        self.assertTrue(mock_add_issue.called)
        msg = ('1 reports of stacktraces in kern.log - please check.')
        msgs = [issue.msg for issue in raised_issues]
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs, [msg])

    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('kernlog.yaml'))
    @mock.patch('hotsos.core.issues.IssuesManager.add')
    def test_oom_killer_invoked(self, mock_add_issue):
        raised_issues = []

        def fake_add_issue(issue, **_kwargs):
            raised_issues.append(issue)

        mock_add_issue.side_effect = fake_add_issue

        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(DATA_ROOT=dtmp)
            os.makedirs(os.path.join(dtmp, 'var/log'))
            klog = os.path.join(dtmp, 'var/log/kern.log')
            with open(klog, 'w') as fd:
                fd.write(KERNLOG_OOM)

            YScenarioChecker()()

        self.assertTrue(mock_add_issue.called)
        msg = ('1 reports of oom-killer invoked in kern.log - please check.')
        msgs = [issue.msg for issue in raised_issues]
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs, [msg])

    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('kernlog.yaml'))
    @mock.patch('hotsos.core.issues.IssuesManager.add')
    def test_nf_conntrack_full(self, mock_add_issue):
        raised_issues = []

        def fake_add_issue(issue, **_kwargs):
            raised_issues.append(issue)

        mock_add_issue.side_effect = fake_add_issue

        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(DATA_ROOT=dtmp)
            os.makedirs(os.path.join(dtmp, 'var/log'))
            klog = os.path.join(dtmp, 'var/log/kern.log')
            with open(klog, 'w') as fd:
                fd.write(KERNLOG_NF_CONNTRACK_FULL)

            YScenarioChecker()()

        self.assertTrue(mock_add_issue.called)
        msg = ("1 reports of 'nf_conntrack: table full' detected in "
               "kern.log - please check.")
        msgs = [issue.msg for issue in raised_issues]
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs, [msg])
