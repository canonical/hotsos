from unittest import mock

from . import utils

from hotsos.plugin_extensions.kernel import summary
from hotsos.core.config import HotSOSConfig
from hotsos.core.plugins.kernel.config import SystemdConfig
from hotsos.core.plugins.kernel import CallTraceManager
from hotsos.core.plugins.kernel.net import SockStat

from hotsos.core.plugins.kernel.memory import (
    BuddyInfo,
    SlabInfo,
    MallocInfo,
)

PROC_SOCKSTAT = r"""sockets: used 908
TCP: inuse 22 orphan 0 tw 2 alloc 58 mem 150987
UDP: inuse 18 mem 350876
UDPLITE: inuse 44
RAW: inuse 55
FRAG: inuse 66 memory 77
"""  # noqa, pylint: disable=C0301

PROC_SOCKSTAT_BAD = r"""sockets: used 908
TCP: inuse 22 orphan 0 tw 2 alloc 58 mem 15
UDP: inuse 18 mem 350876
UDPLITE: inuse 44
UNKNOWN: inuse 22 orphan 15
CORRUPT: inuse orphan 15
RAW: inuse 55
FRAG: inuse 66 memory 77
"""  # noqa, pylint: disable=C0301

PROC_SOCKSTAT_SYSCTL_A = r"""
net.ipv4.udp_mem = 379728	506307	762456
net.ipv4.tcp_mem = 189864	253153	379728
"""


class TestKernelBase(utils.BaseTestCase):
    def setUp(self):
        super().setUp()
        HotSOSConfig.plugin_name = 'kernel'


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

    @utils.create_data_root({'etc/systemd/system.conf':
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

    @utils.create_data_root({'etc/systemd/system.conf':
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
                            'model': 'intel core processor (skylake, ibrs)',
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


class TestKernelNetworkInfo(TestKernelBase):
    @utils.create_data_root(
        {'proc/net/sockstat': PROC_SOCKSTAT,
         'sos_commands/kernel/sysctl_-a': PROC_SOCKSTAT_SYSCTL_A}
    )
    def test_sockstat_parse(self):
        uut = SockStat()
        self.assertEqual(uut.NsTotalSocksInUse, 908)
        self.assertEqual(uut.NsTcpSocksInUse, 22)
        self.assertEqual(uut.GlobTcpSocksOrphaned, 0)
        self.assertEqual(uut.NsTcpSocksInTimeWait, 2)
        self.assertEqual(uut.GlobTcpSocksAllocated, 58)
        self.assertEqual(uut.GlobTcpSocksTotalMemPages, 150987)
        self.assertEqual(uut.NsUdpSocksInUse, 18)
        self.assertEqual(uut.GlobUdpSocksTotalMemPages, 350876)
        self.assertEqual(uut.NsUdpliteSocksInUse, 44)
        self.assertEqual(uut.NsRawSocksInUse, 55)
        self.assertEqual(uut.NsFragSocksInUse, 66)
        self.assertEqual(uut.NsFragSocksTotalMemPages, 77)
        self.assertEqual(uut.SysctlTcpMemMin, 189864)
        self.assertEqual(uut.SysctlTcpMemPressure, 253153)
        self.assertEqual(uut.SysctlTcpMemMax, 379728)
        self.assertEqual(uut.SysctlUdpMemMin, 379728)
        self.assertEqual(uut.SysctlUdpMemPressure, 506307)
        self.assertEqual(uut.SysctlUdpMemMax, 762456)
        self.assertEqual(int(uut.UDPMemUsagePct), 46)
        self.assertEqual(int(uut.TCPMemUsagePct), 39)

    @utils.create_data_root(
        {'proc/net/sockstat': PROC_SOCKSTAT_BAD,
         'sos_commands/kernel/sysctl_-a': PROC_SOCKSTAT_SYSCTL_A}
    )
    def test_sockstat_parse_bad(self):
        uut = SockStat()
        self.assertEqual(uut.NsTotalSocksInUse, 908)
        self.assertEqual(uut.NsTcpSocksInUse, 22)
        self.assertEqual(uut.GlobTcpSocksOrphaned, 0)
        self.assertEqual(uut.NsTcpSocksInTimeWait, 2)
        self.assertEqual(uut.GlobTcpSocksAllocated, 58)
        self.assertEqual(uut.GlobTcpSocksTotalMemPages, 15)
        self.assertEqual(uut.NsUdpSocksInUse, 18)
        self.assertEqual(uut.GlobUdpSocksTotalMemPages, 350876)
        self.assertEqual(uut.NsUdpliteSocksInUse, 44)
        self.assertEqual(uut.NsRawSocksInUse, 55)
        self.assertEqual(uut.NsFragSocksInUse, 66)
        self.assertEqual(uut.NsFragSocksTotalMemPages, 77)
        self.assertEqual(uut.SysctlTcpMemMin, 189864)
        self.assertEqual(uut.SysctlTcpMemPressure, 253153)
        self.assertEqual(uut.SysctlTcpMemMax, 379728)
        self.assertEqual(uut.SysctlUdpMemMin, 379728)
        self.assertEqual(uut.SysctlUdpMemPressure, 506307)
        self.assertEqual(int(uut.UDPMemUsagePct), 46)
        self.assertEqual(int(uut.TCPMemUsagePct), 0)

    @utils.create_data_root(
        {'proc/net/sockstat': "",
         'sos_commands/kernel/sysctl_-a': ""}
    )
    def test_sockstat_parse_sockstat_sysctl_absent(self):
        uut = SockStat()
        self.assertEqual(uut.NsTotalSocksInUse, 0)
        self.assertEqual(uut.NsTcpSocksInUse, 0)
        self.assertEqual(uut.GlobTcpSocksOrphaned, 0)
        self.assertEqual(uut.NsTcpSocksInTimeWait, 0)
        self.assertEqual(uut.GlobTcpSocksAllocated, 0)
        self.assertEqual(uut.GlobTcpSocksTotalMemPages, 0)
        self.assertEqual(uut.NsUdpSocksInUse, 0)
        self.assertEqual(uut.GlobUdpSocksTotalMemPages, 0)
        self.assertEqual(uut.NsUdpliteSocksInUse, 0)
        self.assertEqual(uut.NsRawSocksInUse, 0)
        self.assertEqual(uut.NsFragSocksInUse, 0)
        self.assertEqual(uut.NsFragSocksTotalMemPages, 0)
        self.assertEqual(uut.SysctlTcpMemMin, 0)
        self.assertEqual(uut.SysctlTcpMemPressure, 0)
        self.assertEqual(uut.SysctlTcpMemMax, 0)
        self.assertEqual(uut.SysctlUdpMemMin, 0)
        self.assertEqual(uut.SysctlUdpMemPressure, 0)
        self.assertEqual(uut.UDPMemUsagePct, 0)
        self.assertEqual(uut.TCPMemUsagePct, 0)


@utils.load_templated_tests('scenarios/kernel')
class TestKernelScenarios(TestKernelBase):
    """
    Scenario tests can be written using YAML templates that are auto-loaded
    into this test runner. This is the recommended way to write tests for
    scenarios. It is however still possible to write the tests in Python if
    required. See defs/tests/README.md for more info.
    """
