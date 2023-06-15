from unittest import mock

from hotsos.plugin_extensions.kernel import summary
from hotsos.core.config import HotSOSConfig
from hotsos.core.plugins.kernel.config import SystemdConfig
from hotsos.core.plugins.kernel import CallTraceManager
from hotsos.core.plugins.kernel.net import SockStat, NetLink, Lsof
from hotsos.core.plugins.kernel.memory import (
    BuddyInfo,
    SlabInfo,
    MallocInfo,
)

from . import utils

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

# pylint: disable=C0301
PROC_NETLINK = r"""sk               Eth Pid        Groups   Rmem     Wmem     Dump  Locks    Drops    Inode
0000000000000000 0   23984      00000113 0        0        0     2        0        129906  
0000000000000000 0   142171     00000113 0        0        0     2        0        411370  
0000000000000000 0   12686      00000440 0        0        0     2        0        112920  
0000000000000000 0   186014     00000113 0        0        0     2        0        636924  
0000000000000000 0   186159     00000113 0        0        0     2        0        610163  
0000000000000000 0   10132      00000440 0        0        0     2        0        108883  
0000000000000000 0   2719       00000550 0        0        0     2        0        90600   
0000000000000000 0   10542      00000113 0        0        0     2        0        114127  
0000000000000000 0   2199       000405d1 0        0        0     2        1        34703   
0000000000000000 0   3426       00000440 0        0        0     2        0        89397 
"""  # noqa

# pylint: disable=C0301
LSOF_MNLC = r"""                                                                                                                                                                                                                                    COMMAND     PID   USER   FD      TYPE             DEVICE     SIZE/OFF       NODE NAME
systemd       1        0  cwd       DIR                9,1         4096          2 /
systemd       1        0  rtd       DIR                9,1         4096          2 /
systemd       1        0  txt       REG                9,1      1589552      54275 /lib/systemd/systemd
ksoftirqd   180        0  rtd       DIR                9,1         4096          2 /
watchdog/   382        0  rtd       DIR                9,1         4096          2 /
kswapd0     590        0  rtd       DIR                9,1         4096          2 /
rsyslogd   4084        0  mem       REG                9,1        18976      51133 /lib/x86_64-linux-gnu/libuuid.so.1.3.0
ceilomete  4129      116  mem       REG                9,1        43200      48271 /usr/lib/x86_64-linux-gnu/libyajl.so.2.1.0
kworker/1 10645        0  rtd       DIR                9,1         4096          2 /
ovs-vswit 13936        0  mem-R     REG               0,43      2097152     129906 /mnt/huge_ovs_2M/rtemap_286
ovs-vswit 13936        0  mem-R     REG               0,43      2097152      44403 /mnt/huge_ovs_2M/rtemap_33226
ovs-vswit 13936        0   16u  a_inode               0,13            0      11305 [timerfd]
ovs-vswit 13936        0  616uR     REG               0,43      2097152      34703 /mnt/huge_ovs_2M/rtemap_586
eal-intr- 13936        0  mem-R     REG               0,43      2097152      43181 /mnt/huge_ovs_2M/rtemap_260
eal-intr- 13936        0  mem       REG                9,1      1088952      31573 /lib/x86_64-linux-gnu/libm-2.23.so
eal-intr- 13936        0 1790uR     REG               0,43      2097152      44681 /mnt/huge_ovs_2M/rtemap_33504
rte_mp_ha 13936        0  mem-R     REG               0,43      2097152      43155 /mnt/huge_ovs_2M/rtemap_234
dpdk_watc 13936        0  mem-R     REG               0,43      2097152      43129 /mnt/huge_ovs_2M/rtemap_208
ct_clean4 13936        0  mem-R     REG               0,43      2097152      43103 /mnt/huge_ovs_2M/rtemap_182
ipf_clean 13936        0  mem-R     REG               0,43      2097152      43077 /mnt/huge_ovs_2M/rtemap_156
urcu3     13936        0  mem-R     REG               0,43      2097152      43051 /mnt/huge_ovs_2M/rtemap_130
urcu3     13936        0 1660uR     REG               0,43      2097152      44551 /mnt/huge_ovs_2M/rtemap_33374
pmd7      13936        0  mem-R     REG               0,43      2097152      43025 /mnt/huge_ovs_2M/rtemap_104
pmd8      13936        0  mem-R     REG               0,43      2097152      39927 /mnt/huge_ovs_2M/rtemap_78
pmd8      13936        0 1608uR     REG               0,43      2097152      44499 /mnt/huge_ovs_2M/rtemap_33322
pmd9      13936        0  mem-R     REG               0,43      2097152      39901 /mnt/huge_ovs_2M/rtemap_52
pmd9      13936        0 1582uR     REG               0,43      2097152      44473 /mnt/huge_ovs_2M/rtemap_33296
pmd10     13936        0  mem-R     REG               0,43      2097152      39875 /mnt/huge_ovs_2M/rtemap_26
vhost_rec 13936        0  mem-R     REG               0,43      2097152      39849 /mnt/huge_ovs_2M/rtemap_0
vhost_rec 13936        0 1530uR     REG               0,43      2097152      44421 /mnt/huge_ovs_2M/rtemap_33244
vhost_rec 13936        0 2130r     FIFO               0,12          0t0      41344 pipe
vhost-eve 13936        0  mem-R     REG               0,43      2097152      43495 /mnt/huge_ovs_2M/rtemap_574
vhost-eve 13936        0 2104u      CHR             10,200          0t0        136 /dev/net/tun
monitor13 13936        0  mem-R     REG               0,43      2097152     411370 /mnt/huge_ovs_2M/rtemap_548
monitor13 13936        0 2078u  a_inode               0,13            0      11305 [vfio-device]
revalidat 13936        0  mem-R     REG               0,43      2097152      43417 /mnt/huge_ovs_2M/rtemap_496
zabbix_ag 17684      111  cwd       DIR                9,1         4096          2 /
zabbix_ag 17712      111  mem       REG                9,1       219240      33580 /usr/lib/x86_64-linux-gnu/libnettle.so.6.3
ceilomete 18072      116   48w     FIFO               0,12          0t0      81191 pipe
ceilomete 18072      116  114w     FIFO               0,12          0t0      81243 pipe
qemu-syst 20986        0   44u  a_inode               0,13            0      34703 [eventfd]
CPU\x201/ 20986        0  mem       REG                9,1        43648      49833 /usr/lib/x86_64-linux-gnu/libcacard.so.0.0.0
CPU\x2028 20986        0   74u  a_inode               0,13            0      11305 kvm-vcpu
CPU\x2031 20986        0   17u  a_inode               0,13            0      11305 kvm-vm
agetty    23623        0  rtd       DIR                9,1         4096          2 /
libvirtd  44443        0   25u     unix 0xffffa01631378000          0t0    2022202 /var/run/libvirt/libvirt-sock-ro type=STREAM
libvirtd  44443        0  mem       REG                9,1       408472      33585 /usr/lib/x86_64-linux-gnu/libp11-kit.so.0.1.0
nova-comp 49287      114  mem       REG                9,1        68512      33561 /usr/lib/x86_64-linux-gnu/libavahi-client.so.3.2.9
nova-comp 49287      114   21u     IPv4            2914832          0t0        TCP 192.168.2.24:46064->192.168.2.45:5673 (ESTABLISHED)
sosreport 67605        0    5r     FIFO               0,12          0t0  289262208 pipe
"""  # noqa


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

    @utils.create_data_root(
        {'sos_commands/process/lsof_M_-n_-l_-c': LSOF_MNLC}
    )
    def test_lsof_parse(self):
        uut = Lsof()

        expected_output = [
            ("systemd", 1, 0, "cwd", "DIR", "9,1", "4096", 2, "/"),
            ("systemd", 1, 0, "rtd", "DIR", "9,1", "4096", 2, "/"),
            ("systemd", 1, 0, "txt", "REG", "9,1", "1589552", 54275,
             "/lib/systemd/systemd"),
            ("ksoftirqd", 180, 0, "rtd", "DIR", "9,1", "4096", 2, "/"),
            ("watchdog/", 382, 0, "rtd", "DIR", "9,1", "4096", 2, "/"),
            ("kswapd0", 590, 0, "rtd", "DIR", "9,1", "4096", 2, "/"),
            ("rsyslogd", 4084, 0, "mem", "REG", "9,1", "18976", 51133,
             "/lib/x86_64-linux-gnu/libuuid.so.1.3.0"),
            ("ceilomete", 4129, 116, "mem", "REG", "9,1", "43200", 48271,
             "/usr/lib/x86_64-linux-gnu/libyajl.so.2.1.0"),
            ("kworker/1", 10645, 0, "rtd", "DIR", "9,1", "4096", 2, "/"),
            ("ovs-vswit", 13936,  0, "mem-R", "REG", "0,43", "2097152",
             129906, "/mnt/huge_ovs_2M/rtemap_286"),
            ("ovs-vswit", 13936, 0, "mem-R", "REG", "0,43", "2097152", 44403,
             "/mnt/huge_ovs_2M/rtemap_33226"),
            ("ovs-vswit", 13936, 0, "16u", "a_inode", "0,13", "0", 11305,
             "[timerfd]"),
            ("ovs-vswit", 13936, 0, "616uR", "REG", "0,43", "2097152", 34703,
             "/mnt/huge_ovs_2M/rtemap_586"),
            ("eal-intr-", 13936, 0, "mem-R", "REG", "0,43", "2097152", 43181,
             "/mnt/huge_ovs_2M/rtemap_260"),
            ("eal-intr-", 13936, 0, "mem", "REG", "9,1", "1088952", 31573,
             "/lib/x86_64-linux-gnu/libm-2.23.so"),
            ("eal-intr-", 13936, 0, "1790uR", "REG", "0,43", "2097152", 44681,
             "/mnt/huge_ovs_2M/rtemap_33504"),
            ("rte_mp_ha", 13936, 0, "mem-R", "REG", "0,43", "2097152", 43155,
             "/mnt/huge_ovs_2M/rtemap_234"),
            ("dpdk_watc", 13936, 0, "mem-R", "REG", "0,43", "2097152", 43129,
             "/mnt/huge_ovs_2M/rtemap_208"),
            ("ct_clean4", 13936, 0, "mem-R", "REG", "0,43", "2097152", 43103,
             "/mnt/huge_ovs_2M/rtemap_182"),
            ("ipf_clean", 13936, 0, "mem-R", "REG", "0,43", "2097152", 43077,
             "/mnt/huge_ovs_2M/rtemap_156"),
            ("urcu3", 13936, 0, "mem-R", "REG", "0,43", "2097152", 43051,
             "/mnt/huge_ovs_2M/rtemap_130"),
            ("urcu3", 13936, 0, "1660uR", "REG", "0,43", "2097152", 44551,
             "/mnt/huge_ovs_2M/rtemap_33374"),
            ("pmd7", 13936, 0, "mem-R", "REG", "0,43", "2097152", 43025,
             "/mnt/huge_ovs_2M/rtemap_104"),
            ("pmd8", 13936, 0, "mem-R", "REG", "0,43", "2097152", 39927,
             "/mnt/huge_ovs_2M/rtemap_78"),
            ("pmd8", 13936, 0, "1608uR", "REG", "0,43", "2097152", 44499,
             "/mnt/huge_ovs_2M/rtemap_33322"),
            ("pmd9", 13936, 0, "mem-R", "REG", "0,43", "2097152", 39901,
             "/mnt/huge_ovs_2M/rtemap_52"),
            ("pmd9", 13936, 0, "1582uR", "REG", "0,43", "2097152", 44473,
             "/mnt/huge_ovs_2M/rtemap_33296"),
            ("pmd10", 13936, 0, "mem-R", "REG", "0,43", "2097152", 39875,
             "/mnt/huge_ovs_2M/rtemap_26"),
            ("vhost_rec", 13936, 0, "mem-R", "REG", "0,43", "2097152", 39849,
             "/mnt/huge_ovs_2M/rtemap_0"),
            ("vhost_rec", 13936, 0, "1530uR", "REG", "0,43", "2097152", 44421,
             "/mnt/huge_ovs_2M/rtemap_33244"),
            ("vhost_rec", 13936, 0, "2130r", "FIFO", "0,12", "0t0", 41344,
             "pipe"),
            ("vhost-eve", 13936, 0, "mem-R", "REG", "0,43", "2097152", 43495,
             "/mnt/huge_ovs_2M/rtemap_574"),
            ("vhost-eve", 13936, 0, "2104u", "CHR", "10,200", "0t0", 136,
             "/dev/net/tun"),
            ("monitor13", 13936, 0, "mem-R", "REG", "0,43", "2097152", 411370,
             "/mnt/huge_ovs_2M/rtemap_548"),
            ("monitor13", 13936, 0, "2078u", "a_inode", "0,13", "0", 11305,
             "[vfio-device]"),
            ("revalidat", 13936, 0, "mem-R", "REG", "0,43", "2097152", 43417,
             "/mnt/huge_ovs_2M/rtemap_496"),
            ("zabbix_ag", 17684, 111, "cwd", "DIR", "9,1", "4096", 2, "/"),
            ("zabbix_ag", 17712, 111, "mem", "REG", "9,1", "219240", 33580,
             "/usr/lib/x86_64-linux-gnu/libnettle.so.6.3"),
            ("ceilomete", 18072, 116, "48w", "FIFO", "0,12", "0t0", 81191,
             "pipe"),
            ("ceilomete", 18072, 116, "114w", "FIFO", "0,12", "0t0", 81243,
             "pipe"),
            ("qemu-syst", 20986, 0, "44u", "a_inode", "0,13", "0", 34703,
             "[eventfd]"),
            (r"CPU\x201/", 20986, 0, "mem", "REG", "9,1", "43648", 49833,
             "/usr/lib/x86_64-linux-gnu/libcacard.so.0.0.0"),
            (r"CPU\x2028", 20986, 0, "74u", "a_inode", "0,13", "0", 11305,
             "kvm-vcpu"),
            (r"CPU\x2031", 20986, 0, "17u", "a_inode", "0,13", "0", 11305,
             "kvm-vm"),
            ("agetty", 23623, 0, "rtd", "DIR", "9,1", "4096", 2, "/"),
            ("libvirtd", 44443, 0, "25u", "unix", "0xffffa01631378000", "0t0",
             2022202, "/var/run/libvirt/libvirt-sock-ro type=STREAM"),
            ("libvirtd", 44443, 0, "mem", "REG", "9,1", "408472", 33585,
             "/usr/lib/x86_64-linux-gnu/libp11-kit.so.0.1.0"),
            ("nova-comp", 49287, 114, "mem", "REG", "9,1", "68512", 33561,
             "/usr/lib/x86_64-linux-gnu/libavahi-client.so.3.2.9"),
            ("nova-comp", 49287, 114, "21u", "IPv4", "2914832", "0t0",
             "TCP", "192.168.2.24:46064->192.168.2.45:5673 (ESTABLISHED)"),
            ("sosreport", 67605, 0, "5r", "FIFO", "0,12", "0t0", 289262208,
             "pipe"),
        ]

        self.assertEqual(len(uut.data), 50)

        for ridx, row in enumerate(uut.data):
            for fidx, fname in enumerate(uut.fields):
                self.assertEqual(getattr(row, fname),
                                 expected_output[ridx][fidx])

    @utils.create_data_root(
        {'proc/net/netlink': PROC_NETLINK}
    )
    def test_netlink_parse(self):
        uut = NetLink()

        expected_output = [
            (0, 0, 23984, 275, 0, 0, 0, 2, 0, 129906),
            (0, 0, 142171, 275, 0, 0, 0, 2, 0, 411370),
            (0, 0, 12686, 1088, 0, 0, 0, 2, 0, 112920),
            (0, 0, 186014, 275, 0, 0, 0, 2, 0, 636924),
            (0, 0, 186159, 275, 0, 0, 0, 2, 0, 610163),
            (0, 0, 10132, 1088, 0, 0, 0, 2, 0, 108883),
            (0, 0, 2719, 1360, 0, 0, 0, 2, 0, 90600),
            (0, 0, 10542, 275, 0, 0, 0, 2, 0, 114127),
            (0, 0, 2199, 263633, 0, 0, 0, 2, 1, 34703),
            (0, 0, 3426, 1088, 0, 0, 0, 2, 0, 89397),
        ]

        self.assertEqual(len(uut), 10)

        for ridx, row in enumerate(uut):
            for fidx, fname in enumerate(uut.fields):
                self.assertEqual(getattr(row, fname),
                                 expected_output[ridx][fidx])

    @utils.create_data_root(
        {'proc/net/netlink': PROC_NETLINK,
         'sos_commands/process/lsof_M_-n_-l_-c': LSOF_MNLC}
    )
    def test_netlink_parse_with_drops(self):
        uut = NetLink()
        awd = uut.all_with_drops()
        self.assertEqual(len(awd), 1)
        self.assertEqual(awd[0].sk_addr, 0)
        self.assertEqual(awd[0].sk_protocol, 0)
        self.assertEqual(awd[0].netlink_port_id, 2199)
        self.assertEqual(awd[0].netlink_groups, 263633)
        self.assertEqual(awd[0].sk_rmem, 0)
        self.assertEqual(awd[0].sk_wmem, 0)
        self.assertEqual(awd[0].netlink_dump, 0)
        self.assertEqual(awd[0].sk_references, 2)
        self.assertEqual(awd[0].sk_drops, 1)
        self.assertEqual(awd[0].sk_inode_num, 34703)
        self.assertEqual(awd[0].procs, {'ovs-vswit/13936', 'qemu-syst/20986'})


@utils.load_templated_tests('scenarios/kernel')
class TestKernelScenarios(TestKernelBase):
    """
    Scenario tests can be written using YAML templates that are auto-loaded
    into this test runner. This is the recommended way to write tests for
    scenarios. It is however still possible to write the tests in Python if
    required. See defs/tests/README.md for more info.
    """
