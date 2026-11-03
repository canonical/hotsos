from hotsos.core.plugins.kernel.netdata import (
    HostData,
    LinkData,
    TCPData,
    UDPData,
)
from hotsos.core.plugins.kernel.sockets import SocketTable

from . import utils

PROC_NET_TCP = """\
  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 0100007F:0035 00000000:0000 0A 00000000:00000000 00:00000000 00000000   101        0 17324 1 0000000000000000 100 0 0 10 0
   1: 0A00000A:1F90 1400000A:C350 01 00000010:00000020 00:00000000 00000000     0        0 33333 1 0000000000000000 100 0 0 10 0
   2: corrupt line
"""  # noqa, pylint: disable=C0301

PROC_NET_TCP6 = """\
  sl  local_address                         remote_address                        st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 00000000000000000000000001000000:0016 00000000000000000000000000000000:0000 0A 00000000:00000000 00:00000000 00000000     0        0 44444 1 0000000000000000 100 0 0 10 0
"""  # noqa, pylint: disable=C0301

# A LISTEN socket (state 0A) with three connections waiting to be accepted
# (rx_queue=3). /proc/net does not expose the accept-backlog limit so tx_queue
# is zero here.
PROC_NET_TCP_LISTEN_QUEUED = """\
  sl  local_address rem_address   st tx_queue rx_queue tr tm->when retrnsmt   uid  timeout inode
   0: 0100007F:1F90 00000000:0000 0A 00000000:00000003 00:00000000 00000000   101        0 11111 1 0000000000000000 100 0 0 10 0
"""  # noqa, pylint: disable=C0301

LSOF_LISTEN = """\
nginx      1234        0    6u     IPv4              11111          0t0        TCP 127.0.0.1:8080 (LISTEN)
"""  # noqa, pylint: disable=C0301

SS_PEAONMI = """\
Netid State  Recv-Q Send-Q Local Address:Port Peer Address:Port Process
tcp   LISTEN 3      128    0.0.0.0:80          0.0.0.0:*         users:(("nginx",pid=10,fd=6),("nginx",pid=11,fd=6)) ino:1 sk:1 <->
\t skmem:(r0,rb131072,t0,tb87040,f0,w0,o0,bl0,d0) cubic
tcp   ESTAB  0      0      [::1]:22            [::1]:50000       users:(("sshd",pid=20,fd=4)) ino:2 sk:2 <->
\t skmem:(r4096,rb131072,t0,tb87040,f2048,w1024,o0,bl0,d0) cubic retrans:1/5
udp   UNCONN 512    0      0.0.0.0:514         0.0.0.0:*         users:(("rsyslogd",pid=30,fd=5)) ino:3 sk:3 <->
\t skmem:(r512,rb212992,t0,tb212992,f0,w0,o0,bl0,d7)
"""  # noqa, pylint: disable=C0301

# A UDP sender whose only socket memory is a transmit allocation (wmem_alloc,
# 't'); 'r', 'w' and 'f' are all zero.
SS_UDP_TX_ALLOC = """\
Netid State  Recv-Q Send-Q Local Address:Port Peer Address:Port Process
udp   ESTAB  0      0      10.0.0.1:5000       10.0.0.2:6000     users:(("streamer",pid=40,fd=7)) ino:5 sk:5 <->
\t skmem:(r0,rb212992,t5000,tb212992,f0,w0,o0,bl0,d0)
"""  # noqa, pylint: disable=C0301

IP_LINK = """\
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN mode DEFAULT group default qlen 1000
    link/loopback 00:00:00:00:00:00 brd 00:00:00:00:00:00
    RX: bytes  packets  errors  dropped missed  mcast
    100        10       5       0       0       0
    TX: bytes  packets  errors  dropped carrier collsns
    100        10       0       0       0       0
2: eth0@if7: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc mq state UP mode DEFAULT group default qlen 1000
    link/ether 52:54:00:00:00:01 brd ff:ff:ff:ff:ff:ff
    RX: bytes  packets  errors  dropped missed  mcast
    5000       50       3       2       0       0
    RX errors:  length   crc   frame   fifo  missed
    0          3        0       0       0
    TX: bytes  packets  errors  dropped carrier collsns
    5000       50       0       0       0       0
"""  # noqa, pylint: disable=C0301


INTERRUPTS_BALANCED = """\
           CPU0       CPU1       CPU2       CPU3
  0:         10          0          0          0   IO-APIC   2-edge      timer
 25:       2500       2500       2500       2500   PCI-MSI 524288-edge      virtio0-input.0
"""  # noqa, pylint: disable=C0301

# eth0 only shows up in the description so is matched via the interface name
INTERRUPTS_IFACE_MATCH = """\
           CPU0       CPU1
 30:       5000          0   PCI-MSI 1048576-edge      eth0-TxRx-0
 31:          5          0   PCI-MSI 1048577-edge      eth10-TxRx-0
"""  # noqa, pylint: disable=C0301


class TestSocketTable(utils.BaseTestCase):
    """ Tests for the socket table. """

    @utils.create_data_root({'proc/net/tcp': PROC_NET_TCP,
                             'proc/net/tcp6': PROC_NET_TCP6})
    def test_proc_net_parse(self):
        """Test /proc/net/tcp{,6} parsing including address decoding."""
        socks = SocketTable().sockets
        self.assertEqual(
            [(s.state, s.local, s.remote, s.tx_queue, s.rx_queue)
             for s in socks],
            [('LISTEN', '127.0.0.1:53', '0.0.0.0:0', 0, 0),
             ('ESTABLISHED', '10.0.0.10:8080', '10.0.0.20:50000', 16, 32),
             ('LISTEN', '[::1]:22', '[::]:0', 0, 0)])

    @utils.create_data_root({'sos_commands/networking/ss_-peaonmi':
                             SS_PEAONMI})
    def test_ss_parse(self):
        """Test ss output parsing."""
        table = SocketTable()
        self.assertTrue(table.have_ss)
        listen, estab, udp = table.sockets
        self.assertEqual(listen.state, 'LISTEN')
        self.assertEqual((listen.rx_queue, listen.tx_queue), (3, 128))
        self.assertEqual(listen.owners, 'nginx/10, nginx/11')
        self.assertEqual(estab.state, 'ESTABLISHED')
        self.assertEqual(estab.local, '[::1]:22')
        self.assertEqual(estab.retrans_total, 5)
        self.assertEqual(estab.mem_bytes, 4096 + 1024 + 2048)
        self.assertEqual((udp.proto, udp.drops), ('udp', 7))
        self.assertEqual(table.owners_of_port('tcp', 80),
                         'nginx/10, nginx/11')
        self.assertEqual(table.state_counts(),
                         {'LISTEN': 1, 'ESTABLISHED': 1})

    @utils.create_data_root({})
    def test_no_data(self):
        """Test table is empty when no source of sockets exists."""
        table = SocketTable()
        self.assertEqual(table.sockets, [])
        self.assertFalse(table.have_ss)


class TestSocketDatapoints(utils.BaseTestCase):
    """ Tests for TCP and UDP datapoints. """

    @utils.create_data_root({})
    def test_no_data(self):
        """Test datapoints are empty when there is no socket info."""
        tcp = TCPData()
        self.assertEqual(tcp.queued_listeners, [])
        self.assertIsNone(tcp.half_open_connections)
        self.assertEqual(tcp.half_open_ports, [])
        self.assertEqual(tcp.unread_connections, [])
        self.assertEqual(tcp.socket_states, [])
        self.assertEqual(tcp.close_wait_sockets, 0)
        self.assertEqual(tcp.socket_memory_consumers, [])
        self.assertEqual(tcp.queued_data_consumers, [])
        self.assertEqual(tcp.socket_count_consumers, [])
        self.assertEqual(tcp.retransmitting_connections, [])

        udp = UDPData()
        self.assertEqual(udp.receive_queue_sockets, [])
        self.assertEqual(udp.send_queue_sockets, [])
        self.assertEqual(udp.socket_memory_consumers, [])
        self.assertEqual(udp.queued_data_consumers, [])
        self.assertEqual(udp.socket_count_consumers, [])

    @utils.create_data_root({'proc/net/tcp': PROC_NET_TCP})
    def test_sockets_without_known_owner_not_listed(self):
        """Test sockets with no owning process are not reported."""
        tcp = TCPData()
        self.assertEqual(tcp.unread_connections, [])
        self.assertEqual(tcp.queued_listeners, [])
        self.assertEqual(tcp.socket_count_consumers, [])
        self.assertEqual(tcp.queued_data_consumers, [])
        self.assertEqual(tcp.socket_states, ['LISTEN=1', 'ESTABLISHED=1'])
        self.assertEqual(tcp.half_open_connections, 0)

    @utils.create_data_root({'sos_commands/networking/ss_-peaonmi':
                             SS_PEAONMI})
    def test_ss_datapoints(self):
        """Test datapoints derived from ss."""
        tcp = TCPData()
        self.assertEqual(tcp.queued_listeners,
                         ['0.0.0.0:80 3/128 nginx/10, nginx/11'])
        self.assertEqual(tcp.retransmitting_connections,
                         ['[::1]:22 -> [::1]:50000 retransmits=5 sshd/20'])
        self.assertEqual(tcp.socket_memory_consumers,
                         ['sshd/20 sockets=1 bytes=7168'])
        self.assertEqual(tcp.queued_data_consumers, [])
        self.assertEqual(tcp.socket_count_consumers,
                         ['nginx/10, nginx/11 sockets=1', 'sshd/20 sockets=1'])

        udp = UDPData()
        self.assertEqual(
            udp.receive_queue_sockets,
            ['0.0.0.0:514 rx_queue=512 drops=7 rsyslogd/30'])
        self.assertEqual(udp.send_queue_sockets, [])

    @utils.create_data_root({
        'proc/net/tcp': PROC_NET_TCP_LISTEN_QUEUED,
        'sos_commands/process/lsof_M_-n_-l_-c': LSOF_LISTEN})
    def test_queued_listeners_proc_net_unknown_limit(self):
        """Test proc/net fallback shows '?' for the unknown accept limit."""
        self.assertFalse(SocketTable().have_ss)
        tcp = TCPData()
        self.assertEqual(tcp.queued_listeners,
                         ['127.0.0.1:8080 3/? nginx/1234'])
        # Pending connections are not bytes so must not be counted here.
        self.assertEqual(tcp.queued_data_consumers, [])

    @utils.create_data_root({'sos_commands/networking/ss_-peaonmi':
                             SS_UDP_TX_ALLOC})
    def test_udp_memory_consumers_wmem_alloc(self):
        """Test UDP transmit allocations (skmem 't') are not hidden."""
        udp = UDPData()
        self.assertEqual(udp.socket_memory_consumers,
                         ['streamer/40 sockets=1 bytes=5000'])


class TestLinkDatapoints(utils.BaseTestCase):
    """ Tests for interface datapoints. """

    @utils.create_data_root({'sos_commands/networking/ip_-s_-d_link':
                             IP_LINK})
    def test_link_errors(self):
        """Test interface counters, loopback ignored and names normalised."""
        link = LinkData()
        self.assertEqual(link.interfaces['eth0']['rx']['errors'], 3)
        self.assertEqual(link.rx_error_interfaces,
                         ['eth0: errors=3 dropped=2'])
        self.assertEqual(link.tx_error_interfaces, [])

    @utils.create_data_root({})
    def test_no_data(self):
        """Test no interface datapoints without ip link output."""
        link = LinkData()
        self.assertEqual(link.rx_error_interfaces, [])
        self.assertEqual(link.tx_error_interfaces, [])


class TestHostDatapoints(utils.BaseTestCase):
    """ Tests for host datapoints. """

    @utils.create_data_root({})
    def test_no_data(self):
        """Test datapoints are empty when data is missing."""
        host = HostData()
        self.assertEqual(host.strict_rp_filter_interfaces, [])
        self.assertEqual(host.routing_daemons, [])
        self.assertIsNone(host.conntrack_usage_pcent)
        self.assertEqual(host.conntrack_entries_by_protocol, [])
        self.assertEqual(host.conntrack_tcp_states, [])
        self.assertEqual(host.softnet_drops, [])
        self.assertEqual(host.online_cpus, 0)
        self.assertEqual(host.nic_interrupt_total, 0)
        self.assertIsNone(host.nic_interrupt_busiest_cpu)
        self.assertEqual(host.nic_interrupt_busiest_pcent, 0)
        self.assertEqual(host.nic_irqs, [])

    @utils.create_data_root({'proc/net/softnet_stat':
                             '0000a000 00000000 00000000\n'
                             '00009000 0000000a 00000003\n'
                             'garbage\n'})
    def test_softnet(self):
        """Test softnet drops and that corrupt lines are ignored."""
        self.assertEqual(HostData().softnet_drops,
                         ['cpu1: dropped=10 time_squeeze=3'])

    # CPUs 1 and 2 offline so rows are for CPUs 0 and 3 (ID in column 13).
    @utils.create_data_root({'proc/net/softnet_stat':
                             '0000a000 00000000 00000000 00000000 00000000 '
                             '00000000 00000000 00000000 00000000 00000000 '
                             '00000000 00000000 00000000\n'
                             '00009000 0000000a 00000003 00000000 00000000 '
                             '00000000 00000000 00000000 00000000 00000000 '
                             '00000000 00000000 00000003\n'})
    def test_softnet_cpu_id_column(self):
        """Test softnet uses the explicit CPU ID column when present."""
        self.assertEqual(HostData().softnet_drops,
                         ['cpu3: dropped=10 time_squeeze=3'])

    @utils.create_data_root({'sos_commands/kernel/sysctl_-a':
                             'net.ipv4.conf.all.rp_filter = 1\n'
                             'net.ipv4.conf.default.rp_filter = 0\n'
                             'net.ipv4.conf.eth0.rp_filter = 0\n'
                             'net.ipv4.conf.eth1.rp_filter = 2\n'})
    def test_rp_filter_all_strict(self):
        """Test the 'all' value overrides a less strict interface value."""
        self.assertEqual(HostData().strict_rp_filter_interfaces, ['eth0'])

    @utils.create_data_root({'sos_commands/kernel/sysctl_-a':
                             'net.ipv4.conf.all.rp_filter = 0\n'
                             'net.ipv4.conf.eth0.rp_filter = 0\n'})
    def test_rp_filter_none_strict(self):
        """Test no strict interfaces."""
        self.assertEqual(HostData().strict_rp_filter_interfaces, [])

    @utils.create_data_root({'ps': 'root 1 0.0 0.0 1 1 ? Ss Jan01 0:00 '
                                   '/sbin/init\n'
                                   'root 2 0.0 0.0 1 1 ? Ss Jan01 0:00 '
                                   '/usr/lib/frr/bgpd -d\n'})
    def test_routing_daemons(self):
        """Test routing daemon detection."""
        self.assertEqual(HostData().routing_daemons, ['bgpd'])

    @utils.create_data_root({'sos_commands/kernel/sysctl_-a':
                             'net.netfilter.nf_conntrack_count = 65000\n'
                             'net.netfilter.nf_conntrack_max = 65536\n',
                             'proc/net/nf_conntrack':
                             'ipv4 2 tcp 6 10 ESTABLISHED src=1\n'
                             'ipv4 2 tcp 6 10 TIME_WAIT src=1\n'
                             'ipv4 2 tcp 6 10 ESTABLISHED src=1\n'
                             'ipv4 2 udp 17 20 src=1 dst=2\n'})
    def test_conntrack(self):
        """Test conntrack datapoints."""
        host = HostData()
        self.assertEqual(host.conntrack_usage_pcent, 99.2)
        self.assertEqual(host.conntrack_entries_by_protocol,
                         ['tcp=3', 'udp=1'])
        self.assertEqual(host.conntrack_tcp_states,
                         ['ESTABLISHED=2', 'TIME_WAIT=1'])

    @utils.create_data_root({'proc/interrupts': INTERRUPTS_BALANCED})
    def test_interrupts_balanced(self):
        """Test interrupt datapoints when balanced."""
        host = HostData()
        self.assertEqual(host.online_cpus, 4)
        self.assertEqual(host.nic_interrupt_total, 10000)
        self.assertEqual(host.nic_interrupt_busiest_cpu, 'cpu0')
        self.assertEqual(host.nic_interrupt_busiest_pcent, 25)
        self.assertEqual(host.nic_irqs,
                         ['IRQ 25 virtio0-input.0: 10000 (cpu0 25%)'])

    @utils.create_data_root({'proc/interrupts':
                             'CPU0\n 25: 95000 PCI-MSI virtio0-input.0\n'})
    def test_interrupts_single_cpu(self):
        """Test a single-CPU host reports one online CPU."""
        host = HostData()
        self.assertEqual(host.online_cpus, 1)
        self.assertEqual(host.nic_interrupt_total, 95000)
        self.assertEqual(host.nic_interrupt_busiest_pcent, 100)

    @utils.create_data_root({'proc/interrupts': INTERRUPTS_IFACE_MATCH,
                             'sos_commands/networking/ip_-s_-d_link':
                             IP_LINK})
    def test_interrupts_iface_name_match(self):
        """Test IRQs are matched by interface name without matching eth10."""
        host = HostData()
        self.assertEqual(host.nic_irqs,
                         ['IRQ 30 eth0-TxRx-0: 5000 (cpu0 100%)'])
        self.assertEqual(host.nic_interrupt_total, 5000)
        self.assertEqual(host.nic_interrupt_busiest_pcent, 100)

    @utils.create_data_root({'proc/interrupts':
                             '           CPU0\n  0:  5000   IO-APIC timer\n'})
    def test_interrupts_no_nic_irqs(self):
        """Test no datapoints when no IRQ belongs to a network device."""
        host = HostData()
        self.assertEqual(host.nic_interrupt_total, 0)
        self.assertEqual(host.nic_irqs, [])
