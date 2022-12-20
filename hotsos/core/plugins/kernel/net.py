import abc
import os

from hotsos.core.log import log
from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import SYSCtlFactory


class ProcNetBase(abc.ABC):
    """
    Provides a common way to extract fields from /proc/net/snmp and netstat.

    Expected file format is:

    hdr1: label1 label2 ...
    hdr1: value1 value2 ...
    hdr2: label3 label4 ...
    hdr2: value3 value4 ...
    """
    def __init__(self):
        self._data = {}

    def _pcent_of(self, field_count, total):
        """
        @param field_count: field we want to determine as percentage if total
        @param total: total value
        """
        count = getattr(self, field_count)
        if not count:
            return 0

        if not total:
            return 0

        return round((count * 100.0) / total, 2)

    def _process_file(self, fname):
        if not os.path.exists(fname):
            log.debug("file not found '%s' - skipping load", fname)
            return

        log.debug("start processing %s", fname)
        with open(fname) as fd:
            labels = None
            values = None
            for line in fd:
                if labels is None:
                    labels = line
                    continue

                values = line
                if not all([labels, values]):
                    break

                labels = labels.split()
                values = values.split()
                if labels[0] != values[0]:
                    log.warning('badness: header mismatch in file %s', fname)
                    break

                hdr = labels[0].rstrip(':')
                if hdr in self._data:
                    log.warning('badness: duplicate header in file %s', fname)
                    break

                self._data[hdr] = {}
                for i in list(range(1, len(labels))):
                    self._data[hdr][labels[i]] = int(values[i])

                labels = None
                values = None

        log.debug("finished processing %s", fname)

    def _get_field(self, header, field):
        """Return counter value for field in section header, or
        zero if field does not exist (because older kernel versions
        do not have some fields).
        """
        return self._data.get(header, {}).get(field, 0)

    @abc.abstractproperty
    def _header(self):
        """
        """

    @abc.abstractproperty
    def _fields(self):
        """
        """

    def __getattr__(self, fld):
        if fld in self._fields:
            return self._get_field(self._header, fld)

        raise AttributeError("{} not found in {}".
                             format(fld, self.__class__.__name__))


class SNMPBase(ProcNetBase):

    def __init__(self):
        super().__init__()
        self._process_file(os.path.join(HotSOSConfig.data_root,
                                        'proc/net/snmp'))


class SNMPTcp(SNMPBase):

    def PcentInSegs(self, field):
        """
        The value of a field can be provided as a percentage of the total rx
        segments.
        """
        return self._pcent_of(field, self.InSegs)

    def PcentOutSegs(self, field):
        """
        The value of a field can be provided as a percentage of the total tx
        segments.
        """
        return self._pcent_of(field, self.OutSegs)

    @property
    def _header(self):
        return 'Tcp'

    @property
    def _fields(self):
        return ['InCsumErrors',
                # number of TCP segments received
                'InSegs',
                # number of TCP segments retransmitted
                'RetransSegs',
                # number of TCP segments sent
                'OutSegs']

    def __getattr__(self, fld):
        """
        Fields can be appended with PcentInSegs/PcentOutSegs to get a
        percentage of total rx/tx segments.
        """
        if fld.endswith('PcentInSegs'):
            fld = fld.partition('PcentInSegs')[0]
            return self.PcentInSegs(fld)
        elif fld.endswith('PcentOutSegs'):
            fld = fld.partition('PcentOutSegs')[0]
            return self.PcentOutSegs(fld)

        return super().__getattr__(fld)


class SNMPUdp(SNMPBase):

    @property
    def _header(self):
        return 'Udp'

    def PcentInDatagrams(self, field):
        """
        The value of a field can be provided as a percentage of the total rx
        datagrams.
        """
        return self._pcent_of(field, self.InDatagrams)

    def PcentOutDatagrams(self, field):
        """
        The value of a field can be provided as a percentage of the total tx
        datagrams.
        """
        return self._pcent_of(field, self.OutDatagrams)

    @property
    def _fields(self):
        return ['InDatagrams',
                'NoPorts',
                'InErrors',
                'OutDatagrams',
                'RcvbufErrors',
                'SndbufErrors',
                'InCsumErrors']

    def __getattr__(self, fld):
        """
        Fields can be appended with PcentInDatagrams/PcentOutDatagrams to get a
        percentage of total rx/tx datagrams.
        """
        if fld.endswith('PcentInDatagrams'):
            fld = fld.partition('PcentInDatagrams')[0]
            return self.PcentInDatagrams(fld)
        elif fld.endswith('PcentOutDatagrams'):
            fld = fld.partition('PcentOutDatagrams')[0]
            return self.PcentOutDatagrams(fld)

        return super().__getattr__(fld)


class NetStatBase(ProcNetBase):

    def __init__(self):
        super().__init__()
        self._process_file(os.path.join(HotSOSConfig.data_root,
                                        'proc/net/netstat'))
        self.net_snmp_tcp = SNMPTcp()


class NetStatTCP(NetStatBase):

    @property
    def _header(self):
        return 'TcpExt'

    def PcentInSegs(self, field):
        """
        The value of a field can be provided as a percentage of the total rx
        segments.
        """
        return self._pcent_of(field, self.net_snmp_tcp.InSegs)

    def PcentOutSegs(self, field):
        """
        The value of a field can be provided as a percentage of the total tx
        segments.
        """
        return self._pcent_of(field, self.net_snmp_tcp.OutSegs)

    @property
    def _fields(self):
        return [
            # Times tried to reduce socket memory usage
            'PruneCalled',
            # of skbs collapsed (data combined)
            'TCPRcvCollapsed',
            # Times instructed TCP to drop due to mem press
            'RcvPruned',
            # Times threw away data in ofo queue
            'OfoPruned',
            # Adding skb to TCP backlog queue or C/R obscure case (TCP_REPAIR)
            'TCPBacklogDrop',
            # PFMEMALLOC skb to !MEMALLOC socket or C/R obscure case
            # (TCP_REPAIR).
            'PFMemallocDrop',
            # IP TTL < min TTL (default min TTL == 0) or C/R obscure case
            # (TCP_REPAIR).
            'TCPMinTTLDrop',
            # bare ACK in TCP_DEFER_ACCEPT mode (harmless) or C/R obscure case
            # (TCP_REPAIR)
            'TCPDeferAcceptDrop',
            # Drop after fail rp_filter check
            'IPReversePathFilter',
            # TCP accept queue overflow
            'ListenOverflows',
            # Catch-all for TCP incoming conn request drops or C/R obscure case
            # (TCP_REPAIR)
            'ListenDrops',
            # Drop if OFO and no rmem available for socket
            'TCPOFODrop',
            # Drop due to TCP recv window closed
            'TCPZeroWindowDrop',
            # No rmem when recv segment in ESTABLISHED state or C/R obscure
            # case (TCP_REPAIR).
            'TCPRcvQDrop',
            # req sock queue full (syn flood, syncookies off)
            'TCPReqQFullDrop',
            # req sock queue full (syn flood, syncookies on)
            'TCPReqQFullDoCookies',
            # skb retrans before original left host
            'TCPSpuriousRtxHostQueues']

    def __getattr__(self, fld):
        """
        Fields can be appended with PcentInSegs/PcentOutSegs to get a
        percentage of total rx/tx segments.
        """
        if fld.endswith('PcentInSegs'):
            fld = fld.partition('PcentInSegs')[0]
            return self.PcentInSegs(fld)
        elif fld.endswith('PcentOutSegs'):
            fld = fld.partition('PcentOutSegs')[0]
            return self.PcentOutSegs(fld)

        return super().__getattr__(fld)


class SockStat(ProcNetBase):

    """
    Provides a common way to extract fields from /proc/net/sockstat.

    Expected file format is:

    hdr1: label1 value1 label2 value2...
    hdr2: label1 value1 label2 value2...
    hdr3: label1 value1 label2 value2...
    """
    def __init__(self):
        super().__init__()
        self._process_file(os.path.join(HotSOSConfig.data_root,
                                        'proc/net/sockstat'))
        # Might happen when sockstat file is not present
        if "TCP" not in self._data:
            self._data["TCP"] = {}
        if "UDP" not in self._data:
            self._data["UDP"] = {}

        self._maybe_parse_sysctl_net_ipv4_xmem("TCP")
        self._maybe_parse_sysctl_net_ipv4_xmem("UDP")

    def _maybe_parse_sysctl_net_ipv4_xmem(self, key):
        xmem = getattr(
            SYSCtlFactory(),
            'net.ipv4.{}_mem'.format(key.lower())
        )
        # Some environments may not have all the sysctl
        # parameters present, so make parsing `optional`
        if xmem is not None:
            (mem_min, mem_pressure, mem_max) = xmem.split(" ")
            self._data[key]["sysctl_mem_min"] = int(mem_min)
            self._data[key]["sysctl_mem_pressure"] = int(mem_pressure)
            self._data[key]["sysctl_mem_max"] = int(mem_max)
            if "mem" in self._data[key]:
                self._data[key]["statistics_mem_usage_pct"] = round(
                    (self._data[key]["mem"] /
                        self._data[key]["sysctl_mem_max"] if
                        self._data[key]["sysctl_mem_max"] else 0)
                    * 100.0, 2)

    def _process_file(self, fname):
        if not os.path.exists(fname):
            log.debug("file not found '%s' - skipping load", fname)
            return

        log.debug("start processing %s", fname)
        with open(fname) as fd:
            for line in fd:
                psl = line.split(':')
                if len(psl) != 2:
                    log.warning("badness: line does not match format %s", line)
                    continue
                (label, stats) = psl
                if label not in self._data:
                    self._data[label] = {}
                try:
                    stats = stats.strip().split(' ')
                    stats = dict(stats[i:i+2] for i in range(0, len(stats), 2))
                    # Convert string values to `int``
                    stats = {k: int(v) for k, v in stats.items()}
                    self._data[label] = stats
                except Exception as e:
                    log.warning("badness: failed to parse statistics "
                                "for `%s`, bad data `%s` (%s)",
                                label, stats, e)
                    continue

    @property
    def _header(self):
        # We do not expect this to be used
        raise NotImplementedError()

    @property
    def _fields(self):
        return {
            # Global
            "GlobTcpSocksOrphaned": ("TCP", "orphan"),
            "GlobTcpSocksAllocated": ("TCP", "alloc"),
            "GlobTcpSocksTotalMemPages": ("TCP", "mem"),
            "GlobUdpSocksTotalMemPages": ("UDP", "mem"),
            # Per-netns
            "NsTotalSocksInUse": ("sockets", "used"),
            "NsTcpSocksInUse": ("TCP", "inuse"),
            "NsUdpSocksInUse": ("UDP", "inuse"),
            "NsRawSocksInUse": ("RAW", "inuse"),
            "NsFragSocksInUse": ("FRAG", "inuse"),
            "NsUdpliteSocksInUse": ("UDPLITE", "inuse"),
            "NsTcpSocksInTimeWait": ("TCP", "tw"),
            "NsFragSocksTotalMemPages": ("FRAG", "memory"),
            # These values are from sysctl:
            "SysctlTcpMemMin": ("TCP", "sysctl_mem_min"),
            "SysctlTcpMemPressure": ("TCP", "sysctl_mem_pressure"),
            "SysctlTcpMemMax": ("TCP", "sysctl_mem_max"),
            "SysctlUdpMemMin": ("UDP", "sysctl_mem_min"),
            "SysctlUdpMemPressure": ("UDP", "sysctl_mem_pressure"),
            "SysctlUdpMemMax": ("UDP", "sysctl_mem_max"),
            "UDPMemUsagePct": ("UDP", "statistics_mem_usage_pct"),
            "TCPMemUsagePct": ("TCP", "statistics_mem_usage_pct"),
        }

    def __getattr__(self, fld):
        if fld in self._fields:
            return self._get_field(
                self._fields[fld][0],
                self._fields[fld][1]
            )

        raise AttributeError("{} not found in {}".
                             format(fld, self.__class__.__name__))
