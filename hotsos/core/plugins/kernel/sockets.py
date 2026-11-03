"""
Socket table helpers.

These provide a view of the sockets on the host (state, queue sizes, owning
processes) so that kernel network warnings can point at the sockets and
processes that are contributing to a problem.

The preferred source is the output of 'ss -peaonmi' since it includes owning
processes and per-socket memory/retransmit info. If that is not available we
fall back to /proc/net/{tcp,tcp6,udp,udp6} with process ownership resolved by
correlating socket inodes with lsof output.
"""
import os
import re
import socket
import struct
from dataclasses import dataclass, field
from functools import cached_property

from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import CLIHelper
from hotsos.core.log import log
from hotsos.core.plugins.kernel.net import Lsof

TCP_STATES = {'01': 'ESTABLISHED', '02': 'SYN_SENT', '03': 'SYN_RECV',
              '04': 'FIN_WAIT1', '05': 'FIN_WAIT2', '06': 'TIME_WAIT',
              '07': 'CLOSE', '08': 'CLOSE_WAIT', '09': 'LAST_ACK',
              '0A': 'LISTEN', '0B': 'CLOSING'}
# UDP sockets only ever report these two.
UDP_STATES = {'01': 'ESTABLISHED', '07': 'UNCONN'}
SS_STATE_ALIASES = {'ESTAB': 'ESTABLISHED'}


@dataclass
class Socket:  # pylint: disable=too-many-instance-attributes
    """ A single socket entry. """
    proto: str
    state: str
    local: str
    remote: str
    rx_queue: int = 0
    tx_queue: int = 0
    inode: int = 0
    drops: int = 0
    procs: set = field(default_factory=set)
    # Only available from ss.
    skmem: dict = field(default_factory=dict)
    retrans_total: int = 0

    @property
    def local_port(self):
        """ Port part of the local address. """
        return self.local.rpartition(':')[2]

    @property
    def owners(self):
        """ Comma separated list of owning processes. """
        return ', '.join(sorted(self.procs))

    @property
    def mem_bytes(self):
        """ Memory held by the socket. Falls back to queue sizes.

        Transmit memory is reported differently per protocol: TCP exposes the
        bytes queued but not yet sent (wmem_queued, 'w') while UDP only
        accounts transmit allocations under wmem_alloc ('t'). Using the
        protocol-appropriate field avoids hiding UDP senders (nonzero 't' but
        zero 'w') and double-counting TCP send buffers.
        """
        if self.skmem:
            tx = self.skmem.get('t' if self.proto == 'udp' else 'w', 0)
            return self.skmem.get('r', 0) + tx + self.skmem.get('f', 0)

        return self.rx_queue + self.tx_queue


def _decode_addr(hexaddr):
    """ Decode a /proc/net/{tcp,udp}{,6} 'address:port' field. """
    addr, _, port = hexaddr.partition(':')
    try:
        if len(addr) == 8:
            ip = socket.inet_ntoa(struct.pack('<I', int(addr, 16)))
        else:
            words = [addr[i:i + 8] for i in range(0, 32, 8)]
            packed = b''.join(struct.pack('<I', int(w, 16)) for w in words)
            ip = socket.inet_ntop(socket.AF_INET6, packed)
            ip = f'[{ip}]'

        return f'{ip}:{int(port, 16)}'
    except (ValueError, struct.error, OSError):
        return hexaddr


def _hex_queue_pair(value):
    """ Decode 'tx_queue:rx_queue' (hex) into (tx, rx). """
    tx, _, rx = value.partition(':')
    return int(tx, 16), int(rx, 16)


class SocketTable:
    """ All TCP and UDP sockets on the host. """

    PROC_NET = {'tcp': ['proc/net/tcp', 'proc/net/tcp6'],
                'udp': ['proc/net/udp', 'proc/net/udp6']}

    @cached_property
    def sockets(self):
        """ List of Socket objects. Empty if no source is available. """
        socks = self._load_ss()
        if socks:
            return socks

        return self._load_proc_net()

    @cached_property
    def have_ss(self):
        """ True if sockets were loaded from ss. """
        return any(s.skmem for s in self.sockets)

    @property
    def tcp(self):
        """ All TCP sockets. """
        return [s for s in self.sockets if s.proto == 'tcp']

    @property
    def udp(self):
        """ All UDP sockets. """
        return [s for s in self.sockets if s.proto == 'udp']

    def tcp_in_state(self, state):
        """ TCP sockets in the given state. """
        return [s for s in self.tcp if s.state == state]

    def owners_of_port(self, proto, port):
        """ Processes owning sockets with the given local port. """
        procs = set()
        for sock in self.sockets:
            if sock.proto == proto and sock.local_port == str(port):
                procs.update(sock.procs)

        return ', '.join(sorted(procs))

    def state_counts(self, proto='tcp'):
        """ Dict of socket counts by state for given protocol. """
        counts = {}
        for sock in self.sockets:
            if sock.proto == proto:
                counts[sock.state] = counts.get(sock.state, 0) + 1

        return counts

    # ss -peaonmi
    @staticmethod
    def _parse_ss_head(line):
        """
        Parse the first line of an ss entry:

        Netid State Recv-Q Send-Q Local:Port Peer:Port [Process] [ino:..]
        """
        cols = line.split(None, 6)
        if len(cols) < 6 or cols[0] not in ('tcp', 'udp'):
            return None

        netid, state, recvq, sendq, local, remote = cols[:6]
        if not (recvq.isdigit() and sendq.isdigit()):
            return None

        state = state.upper().replace('-', '_')
        state = SS_STATE_ALIASES.get(state, state)
        sock = Socket(netid, state, local, remote, rx_queue=int(recvq),
                      tx_queue=int(sendq))
        rest = cols[6] if len(cols) > 6 else ''
        for name, pid in re.findall(r'\("([^"]*)",pid=(\d+)', rest):
            sock.procs.add(f'{name}/{pid}')

        ret = re.search(r'\bino:(\d+)', rest)
        if ret:
            sock.inode = int(ret.group(1))

        return sock

    @staticmethod
    def _parse_ss_detail(sock, line):
        """ Parse an indented continuation line of an ss entry. """
        ret = re.search(r'skmem:\(([^)]*)\)', line)
        if ret:
            sock.skmem = {k: int(v) for k, v in
                          re.findall(r'([a-z]+)(\d+)', ret.group(1))}
            sock.drops = sock.skmem.get('d', 0)

        ret = re.search(r'\bretrans:\d+/(\d+)', line)
        if ret:
            sock.retrans_total = int(ret.group(1))

    def _load_ss(self):
        socks = []
        current = None
        for line in CLIHelper().ss_peaonmi():
            line = line.rstrip('\n')
            if not line.strip():
                continue

            if line[0].isspace():
                if current:
                    self._parse_ss_detail(current, line)

                continue

            current = self._parse_ss_head(line)
            if current:
                socks.append(current)

        log.debug("loaded %d sockets from ss", len(socks))
        return socks

    # /proc/net
    @cached_property
    def _inode_owners(self):
        """ Map of socket inode to set of 'command/pid'. """
        owners = {}
        for entry in Lsof():
            # For IP sockets lsof puts the socket inode in the DEVICE column.
            if entry.TYPE not in ('IPv4', 'IPv6'):
                continue

            value = entry.DEVICE
            if isinstance(value, str) and value.isdigit():
                owners.setdefault(int(value), set()).add(
                    f'{entry.COMMAND}/{entry.PID}')

        return owners

    @staticmethod
    def _parse_proc_net_line(proto, line):
        cols = line.split()
        # header or short/corrupt line
        if len(cols) < 10 or not cols[0].endswith(':'):
            return None

        try:
            states = TCP_STATES if proto == 'tcp' else UDP_STATES
            tx_queue, rx_queue = _hex_queue_pair(cols[4])
            sock = Socket(proto, states.get(cols[3], cols[3]),
                          _decode_addr(cols[1]), _decode_addr(cols[2]),
                          rx_queue=rx_queue, tx_queue=tx_queue,
                          inode=int(cols[9]))
            if proto == 'udp' and len(cols) >= 13:
                sock.drops = int(cols[12])
        except ValueError:
            log.debug("failed to parse socket line '%s'", line)
            return None

        return sock

    def _load_proc_net(self):
        socks = []
        for proto, paths in self.PROC_NET.items():
            for path in paths:
                path = os.path.join(HotSOSConfig.data_root, path)
                if not os.path.exists(path):
                    continue

                with open(path, encoding='utf-8') as fd:
                    for line in fd:
                        sock = self._parse_proc_net_line(proto, line)
                        if sock:
                            socks.append(sock)

        if socks:
            owners = self._inode_owners
            for sock in socks:
                sock.procs = set(owners.get(sock.inode, ()))

        log.debug("loaded %d sockets from proc/net", len(socks))
        return socks
