"""
Network datapoints for kernel network scenarios.

Each property provides a piece of information about the host that is relevant
when diagnosing network problems e.g. the processes that own sockets with
queued data, interfaces reporting errors or how interrupts are distributed
across CPUs. They are consumed by scenarios which decide whether and how to
present them so properties only return plain values:

* lists of short entries (empty if there is nothing to report),
* numbers, or
* None if the information is not available.
"""
import os
import re
from functools import cached_property

from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import CLIHelper, SYSCtlFactory
from hotsos.core.log import log
from hotsos.core.plugins.kernel.sockets import SocketTable

TOP_N = 5


class NetDataBase:  # pylint: disable=too-few-public-methods
    """ Common helpers for network datapoint providers. """

    @cached_property
    def _table(self):
        return SocketTable()

    @cached_property
    def _sysctl_all(self):
        return SYSCtlFactory().sysctl_all

    @staticmethod
    def _by_process(socks, value=lambda s: 1):
        """
        Aggregate sockets with a known owner by owning process. Returns list
        of (owners, num_sockets, total) sorted by total descending.
        """
        agg = {}
        for sock in socks:
            if not sock.owners:
                continue

            num, total = agg.get(sock.owners, (0, 0))
            agg[sock.owners] = (num + 1, total + value(sock))

        return sorted(((k, v[0], v[1]) for k, v in agg.items()),
                      key=lambda x: x[2], reverse=True)

    def _memory_consumers(self, socks):
        """ Entries of processes with the most memory held by sockets. """
        if not self._table.have_ss:
            return []

        return [f'{owners} sockets={num} bytes={total}'
                for owners, num, total in
                self._by_process([s for s in socks if s.mem_bytes],
                                 lambda s: s.mem_bytes)[:TOP_N]]

    def _sockets_w_non_empty_recv_buffer(self, socks):
        """
        Entries of processes with the most queued socket data. This is a
        proxy for socket memory used when per-socket memory is not available.
        """
        if self._table.have_ss:
            return []

        # Filter/aggregate on rx_queue only; mem_bytes also includes tx_queue
        # in this fallback, which would count send-only sockets as receivers.
        return [f'{owners} sockets={num} bytes={total}'
                for owners, num, total in
                self._by_process([s for s in socks if s.rx_queue],
                                 lambda s: s.rx_queue)[:TOP_N]]

    def _socket_count_consumers(self, socks):
        """ Entries of processes with the most sockets. """
        return [f'{owners} sockets={num}'
                for owners, num, _ in self._by_process(socks)[:TOP_N]]


class TCPData(NetDataBase):
    """ Datapoints based on the TCP sockets on this host. """

    @property
    def queued_listeners(self):
        """
        Listening sockets with connections waiting to be accepted as
        '<address> <queued>/<limit> <owners>'. The accept-backlog limit is
        only available from ss; the /proc/net fallback does not expose it so
        the limit is shown as '?' rather than a misleading zero.
        """
        have_ss = self._table.have_ss
        queued = sorted((s for s in self._table.tcp_in_state('LISTEN')
                         if s.rx_queue > 0 and s.owners),
                        key=lambda s: s.rx_queue / max(s.tx_queue, 1),
                        reverse=True)
        return [f'{s.local} {s.rx_queue}/{s.tx_queue if have_ss else "?"} '
                f'{s.owners}' for s in queued[:TOP_N]]

    @property
    def half_open_connections(self):
        """ Number of connections in SYN_RECV or None if no socket info. """
        if not self._table.sockets:
            return None

        return len(self._table.tcp_in_state('SYN_RECV'))

    @property
    def half_open_ports(self):
        """ Ports with half-open connections as 'port <port>: <num> <owners>'.
        """
        ports = {}
        for sock in self._table.tcp_in_state('SYN_RECV'):
            ports[sock.local_port] = ports.get(sock.local_port, 0) + 1

        entries = []
        for port, num in sorted(ports.items(), key=lambda x: x[1],
                                reverse=True)[:TOP_N]:
            owners = self._table.owners_of_port('tcp', port)
            entries.append(f'port {port}: {num} {owners}'.rstrip())

        return entries

    @property
    def unaccepted_connections(self):
        """
        Connections with unread data as
        '<local> <- <remote> <bytes> <owners>'.
        """
        conns = sorted((s for s in self._table.tcp
                        if s.state != 'LISTEN' and s.rx_queue > 0 and
                        s.owners),
                       key=lambda s: s.rx_queue, reverse=True)
        return [f'{s.local} <- {s.remote} {s.rx_queue} {s.owners}'
                for s in conns[:TOP_N]]

    @property
    def socket_states(self):
        """ Number of sockets in each state as '<state>=<num>'. """
        counts = self._table.state_counts('tcp')
        return [f'{state}={num}' for state, num in
                sorted(counts.items(), key=lambda x: x[1], reverse=True)]

    @property
    def socket_memory_consumers(self):
        """ Processes holding the most socket memory (requires ss). """
        return self._memory_consumers(self._table.tcp)

    @property
    def sockets_w_non_empty_recv_buffer(self):
        """ Processes with the most queued socket data (when no ss). """
        # LISTEN rx_queue is pending connections, not bytes.
        return self._sockets_w_non_empty_recv_buffer(
            [s for s in self._table.tcp if s.state != 'LISTEN'])

    @property
    def socket_count_consumers(self):
        """ Processes with the most sockets. """
        return self._socket_count_consumers(self._table.tcp)

    @property
    def retransmitting_connections(self):
        """
        Connections with the most retransmissions (requires ss) as
        '<local> -> <remote> retransmits=<num> <owners>'.
        """
        if not self._table.have_ss:
            return []

        socks = sorted((s for s in self._table.tcp
                        if s.retrans_total > 0 and s.owners),
                       key=lambda s: s.retrans_total, reverse=True)
        return [f'{s.local} -> {s.remote} retransmits={s.retrans_total} '
                f'{s.owners}' for s in socks[:TOP_N]]


class UDPData(NetDataBase):
    """ Datapoints based on the UDP sockets on this host. """

    @property
    def receive_queue_sockets(self):
        """
        Sockets with unread data or drops as
        '<local> rx_queue=<bytes> drops=<num> <owners>'.
        """
        socks = sorted((s for s in self._table.udp
                        if (s.rx_queue or s.drops) and s.owners),
                       key=lambda s: (s.drops, s.rx_queue), reverse=True)
        return [f'{s.local} rx_queue={s.rx_queue} drops={s.drops} {s.owners}'
                for s in socks[:TOP_N]]

    @property
    def send_queue_sockets(self):
        """
        Sockets with data waiting to be sent as
        '<local> tx_queue=<bytes> drops=<num> <owners>'.
        """
        socks = sorted((s for s in self._table.udp
                        if s.tx_queue and s.owners),
                       key=lambda s: s.tx_queue, reverse=True)
        return [f'{s.local} tx_queue={s.tx_queue} drops={s.drops} {s.owners}'
                for s in socks[:TOP_N]]

    @property
    def socket_memory_consumers(self):
        """ Processes holding the most socket memory (requires ss). """
        return self._memory_consumers(self._table.udp)

    @property
    def sockets_w_non_empty_recv_buffer(self):
        """ Processes with the most queued socket data (when no ss). """
        return self._sockets_w_non_empty_recv_buffer(self._table.udp)

    @property
    def socket_count_consumers(self):
        """ Processes with the most sockets. """
        return self._socket_count_consumers(self._table.udp)


class LinkData(NetDataBase):
    """ Datapoints from interface counters i.e. 'ip -s link'. """
    IFACE_EXPR = re.compile(r'^\d+:\s+([^:@\s]+)(?:@\S+)?:\s')
    COUNTERS = {'rx': ['errors', 'dropped', 'missed', 'overrun'],
                'tx': ['errors', 'dropped', 'carrier', 'collsns']}

    @cached_property
    def interfaces(self):
        """ Dict of interface name to rx/tx counters. """
        ifaces = {}
        name = None
        pending = None
        for line in CLIHelper().ip_link():
            line = line.rstrip('\n')
            ret = self.IFACE_EXPR.match(line)
            if ret:
                name = ret.group(1)
                ifaces[name] = {'rx': {}, 'tx': {}}
                pending = None
                continue

            if name is None:
                continue

            if pending:
                direction, headers = pending
                pending = None
                values = line.split()
                if (len(values) == len(headers) and
                        all(v.isdigit() for v in values)):
                    ifaces[name][direction] = dict(
                        zip(headers, (int(v) for v in values)))

                continue

            ret = re.match(r'\s+(RX|TX):\s+(.+)$', line)
            if ret:
                pending = (ret.group(1).lower(), ret.group(2).split())

        return ifaces

    def _error_interfaces(self, direction):
        bad = []
        for name, counters in self.interfaces.items():
            if name == 'lo':
                continue

            shown = {k: counters[direction].get(k, 0)
                     for k in self.COUNTERS[direction]}
            shown = {k: v for k, v in shown.items() if v}
            if shown:
                bad.append((sum(shown.values()), name, shown))

        return [f'{name}: ' + ' '.join(f'{k}={v}' for k, v in shown.items())
                for _, name, shown in sorted(bad, reverse=True)[:TOP_N]]

    @property
    def rx_error_interfaces(self):
        """ Interfaces with receive errors/drops as '<name>: <counters>'. """
        return self._error_interfaces('rx')

    @property
    def tx_error_interfaces(self):
        """ Interfaces with transmit errors/drops as '<name>: <counters>'. """
        return self._error_interfaces('tx')


class HostData(NetDataBase):
    """ Datapoints from host configuration and per-host statistics. """
    ROUTING_DAEMONS = ['bird', 'bird6', 'bgpd', 'bfdd', 'zebra', 'frr',
                       'gobgpd', 'exabgp', 'neutron-bgp-dragent']
    # Names of IRQ lines that belong to network devices but do not contain
    # the interface name.
    NIC_IRQ_EXPR = re.compile(
        r'virtio\d+-(input|output)|mlx[45]_(comp|async)|mlx4-\d|ixgbe|i40e|'
        r'iavf|ice-|igb|bnxt|bnx2x|ena-|vmxnet3|e1000|tg3|be2net|qede|enic|'
        r'hinic')

    @property
    def strict_rp_filter_interfaces(self):
        """ Interfaces where strict reverse path filtering is in effect. """
        conf = {}
        for key, value in self._sysctl_all.items():
            ret = re.match(r'^net\.ipv4\.conf\.(.+)\.rp_filter$', key)
            if ret and value.isdigit():
                conf[ret.group(1).replace('/', '.')] = int(value)

        if 'all' not in conf:
            return []

        # The kernel uses the highest of the 'all' and per-interface values.
        return sorted(name for name, value in conf.items()
                      if name not in ('all', 'default') and
                      max(value, conf['all']) == 1)[:10]

    @property
    def routing_daemons(self):
        """
        Routing daemons running on this host. These commonly use a minimum
        TTL for BGP/BFD sessions.
        """
        found = set()
        for line in CLIHelper().ps():
            cols = line.split(None, 10)
            if len(cols) < 11:
                continue

            exe = os.path.basename(cols[10].split()[0])
            if exe in self.ROUTING_DAEMONS:
                found.add(exe)

        return sorted(found)

    @property
    def conntrack_usage_pcent(self):
        """ Percentage of the conntrack table in use or None. """
        count = self._sysctl_all.get('net.netfilter.nf_conntrack_count')
        limit = self._sysctl_all.get('net.netfilter.nf_conntrack_max')
        if not (count and limit and count.isdigit() and limit.isdigit()):
            return None

        return round(int(count) * 100.0 / max(int(limit), 1), 1)

    @cached_property
    def _conntrack_entries(self):
        path = os.path.join(HotSOSConfig.data_root, 'proc/net/nf_conntrack')
        protos = {}
        tcp_states = {}
        if not os.path.exists(path):
            return protos, tcp_states

        with open(path, encoding='utf-8') as fd:
            for line in fd:
                cols = line.split()
                if len(cols) < 6:
                    continue

                protos[cols[2]] = protos.get(cols[2], 0) + 1
                if cols[2] == 'tcp':
                    tcp_states[cols[5]] = tcp_states.get(cols[5], 0) + 1

        return protos, tcp_states

    @staticmethod
    def _counts_entries(counts):
        return [f'{k}={v}' for k, v in
                sorted(counts.items(), key=lambda x: x[1], reverse=True)]

    @property
    def conntrack_entries_by_protocol(self):
        """ Conntrack entries per protocol as '<proto>=<num>'. """
        return self._counts_entries(self._conntrack_entries[0])

    @property
    def conntrack_tcp_states(self):
        """ Conntrack tcp entries per state as '<state>=<num>'. """
        return self._counts_entries(self._conntrack_entries[1])

    @cached_property
    def _softnet(self):
        path = os.path.join(HotSOSConfig.data_root, 'proc/net/softnet_stat')
        if not os.path.exists(path):
            return {}

        cpus = {}
        with open(path, encoding='utf-8') as fd:
            for row, line in enumerate(fd):
                cols = line.split()
                try:
                    # Kernel >= 5.10 has the CPU ID in column 13; older
                    # layouts only allow inferring it from row position.
                    cpu = int(cols[12], 16) if len(cols) > 12 else row
                    cpus[cpu] = {'processed': int(cols[0], 16),
                                 'dropped': int(cols[1], 16),
                                 'time_squeeze': int(cols[2], 16)}
                except (IndexError, ValueError):
                    log.debug("failed to parse softnet_stat line '%s'", line)

        return cpus

    def _softnet_top(self, counter):
        bad = [(v[counter], cpu) for cpu, v in self._softnet.items()
               if v[counter]]
        return [f"cpu{cpu}: {num}"
                for num, cpu in sorted(bad, reverse=True)[:TOP_N]]

    def _softnet_total(self, counter):
        return sum(v[counter] for v in self._softnet.values())

    @property
    def softnet_drops(self):
        """
        CPUs that dropped packets because their network backlog
        (net.core.netdev_max_backlog) was full as 'cpu<id>: <num>'.
        """
        return self._softnet_top('dropped')

    @property
    def softnet_time_squeeze(self):
        """
        CPUs that deferred receive processing because the softirq budget
        (net.core.netdev_budget/netdev_budget_usecs) ran out as
        'cpu<id>: <num>'.
        """
        return self._softnet_top('time_squeeze')

    @property
    def softnet_processed_total(self):
        """ Packets processed by the network backlog across all CPUs. """
        return self._softnet_total('processed')

    @property
    def softnet_dropped_total(self):
        """ Packets dropped from the network backlog across all CPUs. """
        return self._softnet_total('dropped')

    @property
    def softnet_time_squeeze_total(self):
        """ Times the softirq budget ran out across all CPUs. """
        return self._softnet_total('time_squeeze')

    @property
    def softnet_time_squeeze_pcent(self):
        """ time_squeeze as a percentage of packets processed. """
        processed = self.softnet_processed_total
        if not processed:
            return 0

        return round(self.softnet_time_squeeze_total * 100.0 / processed, 2)

    @cached_property
    def online_cpus(self):
        """
        Number of online CPUs as reported by the per-CPU columns of
        /proc/interrupts (offline CPUs have no column). 0 if unavailable.
        """
        path = os.path.join(HotSOSConfig.data_root, 'proc/interrupts')
        if not os.path.exists(path):
            return 0

        with open(path, encoding='utf-8') as fd:
            for line in fd:
                cols = line.split()
                if cols and all(c.startswith('CPU') for c in cols):
                    return len(cols)

        return 0

    @cached_property
    def _nic_irqs(self):
        """
        Parse /proc/interrupts and return a list of (irq, name, counts)
        for IRQs that belong to network devices, where counts is a dict of
        cpu name to interrupt count.
        """
        path = os.path.join(HotSOSConfig.data_root, 'proc/interrupts')
        if not os.path.exists(path):
            return []

        ifaces = [name for name in LinkData().interfaces if name != 'lo']
        iface_expr = None
        if ifaces:
            iface_expr = re.compile(
                '(?<![A-Za-z0-9])(' + '|'.join(re.escape(n) for n in ifaces) +
                ')(?![0-9])')

        cpus = None
        irqs = []
        with open(path, encoding='utf-8') as fd:
            for line in fd:
                cols = line.split()
                if cpus is None:
                    if cols and all(c.startswith('CPU') for c in cols):
                        cpus = cols

                    continue

                if len(cols) <= len(cpus) + 1 or not cols[0].endswith(':'):
                    continue

                counts = cols[1:len(cpus) + 1]
                if not all(c.isdigit() for c in counts):
                    continue

                desc = ' '.join(cols[len(cpus) + 1:])
                if (self.NIC_IRQ_EXPR.search(desc) or
                        (iface_expr and iface_expr.search(desc))):
                    irqs.append((cols[0].rstrip(':'), cols[-1],
                                 dict(zip(cpus, (int(c) for c in counts)))))

        return irqs

    @cached_property
    def _nic_interrupts_per_cpu(self):
        per_cpu = {}
        for _, _, counts in self._nic_irqs:
            for cpu, count in counts.items():
                per_cpu[cpu] = per_cpu.get(cpu, 0) + count

        return per_cpu

    @property
    def nic_interrupt_total(self):
        """ Total interrupts handled for network devices. """
        return sum(self._nic_interrupts_per_cpu.values())

    @property
    def nic_interrupt_busiest_cpu(self):
        """ CPU handling the most network device interrupts or None. """
        if not self.nic_interrupt_total:
            return None

        cpu = max(self._nic_interrupts_per_cpu.items(), key=lambda x: x[1])[0]
        return cpu.lower()

    @property
    def nic_interrupt_busiest_pcent(self):
        """ Percentage of network device interrupts on the busiest CPU. """
        total = self.nic_interrupt_total
        if not total:
            return 0

        return round(max(self._nic_interrupts_per_cpu.values()) * 100.0 /
                     total)

    @property
    def nic_irqs(self):
        """
        Network device IRQs with the most interrupts as
        'IRQ <num> <name>: <total> (<busiest cpu> <pcent>%)'.
        """
        entries = []
        for irq, name, counts in sorted(
                self._nic_irqs, key=lambda x: sum(x[2].values()),
                reverse=True)[:TOP_N]:
            irq_total = sum(counts.values())
            if not irq_total:
                continue

            cpu, count = max(counts.items(), key=lambda x: x[1])
            share = round(count * 100.0 / irq_total)
            entries.append(f'IRQ {irq} {name}: {irq_total} '
                           f'({cpu.lower()} {share}%)')

        return entries
