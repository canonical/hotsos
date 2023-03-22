import abc
import os
import re
import itertools
from typing import Iterator
from hotsos.core.log import log
from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import SYSCtlFactory, CLIHelper


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


class STOVParser(abc.ABC):
    """Structured table of values parser.

    A common base class for table parsers.
    """

    class LineObject(object):
        def __init__(self, finfos, fvalues) -> None:
            assert len(finfos) == len(fvalues)
            for idx, (fname, ftype_info) in enumerate(finfos):
                fvalue = fvalues[idx]
                if fvalues[idx] is not None:
                    if isinstance(ftype_info, type) or callable(ftype_info):
                        try:
                            fvalue = ftype_info(fvalue)
                        except Exception as e:
                            log.warning(
                                "failed to parse %s as %s", fvalue, ftype_info)
                            raise e
                    else:
                        raise Exception(
                            f"Unknown type info value {ftype_info}")
                setattr(self, fname, fvalue)

        def __str__(self) -> str:
            # Return a | separated list of field_name:field_value's
            return " | ".join(
                # Get all attributes of the LineObject object, filter out
                # the built-in ones and stringify the rest in "name:value"
                # format
                [f" {v}:{str(getattr(self, v))}" for v in filter(
                    lambda x: not x.startswith("__"), dir(self))]
            )

    @abc.abstractmethod
    def header_matcher(self) -> re.Pattern:
        """Regex pattern for matching against the
        table header, if any. It is used as a preliminary
        check to see whether the input is in expected format.
        """

    @abc.abstractmethod
    def field_matcher(self) -> re.Pattern:
        """Regex pattern to extract each field from a
        table row. Each field MUST be represented as a
        regex capture group. The amount of capture groups
        MUST be same with the field number.
        """

    @abc.abstractproperty
    def fields(self):
        """ (name, type|func) pairs, describing each field's
        respective name and the data type (or a parser function).
        All extracted fields will be put as an attribute with the
        designated field name and the "value" will be either;
          - casted to "type" if the second value of the pair is a
            type name
          - passed to "func" as an argument if the second value of
            the pair is a callable "thing". The called "thing" must
            return the desired version of the value to be stored.
        """

    @abc.abstractmethod
    def input(self) -> Iterator[str]:
        """The raw input. The parser will call this function to obtain
        an iterator to the raw data, and use header_matcher & field_matcher
        to parse the data.
        """

    def __init__(self) -> None:
        super().__init__()
        self._data = []

    def data(self):
        return self._data

    def parse(self):
        input = self.input()
        hdr_m = self.header_matcher()
        fld_m = self.field_matcher()

        # Header matcher is optional.
        if hdr_m:
            try:
                # Skip empty lines, if any
                input = itertools.dropwhile(lambda x: x.isspace(), input)
                hline = next(input).lstrip()
                if not hdr_m.match(hline):
                    log.warning(
                        "badness: header line is not in expected format: '%s'",
                        hline)
                    return
            except StopIteration:
                return

        for line in input:
            match = fld_m.match(line)
            if not match:
                log.warning("badness: line does not match format: '%s'", line)
                continue
            try:
                self._data.append(STOVParser.LineObject(
                    self.fields, match.groups()))
            except Exception as e:
                log.warning("badness: failed to parse statistics line "
                            " bad data `%s` (%s)",
                            line, e)


class Lsof(STOVParser):
    """
    Provides a way to extract fields from lsof output.

    Expected file format is:

    COMMAND PID TID USER  FD TYPE DEVICE SIZE/OFF  NODE NAME
    systemd   1        0 cwd  DIR    9,1     4096     2 /
    systemd   1        0 rtd  DIR    9,1     4096     2 /
    systemd   1        0 txt  REG    9,1  1589552 54275 /lib/
    systemd   1        0 mem  REG    9,1    18976 51133 /lib/
    /*...*/
    """

    def header_matcher(self):
        return re.compile(
            r"COMMAND +PID +TID +USER +FD "
            r"+TYPE +DEVICE +SIZE/OFF +NODE +NAME\n")

    def field_matcher(self):
        return re.compile(
            r"([^ ]+) +([^ ]+) +([^ ]+)? +([^ ]+) "
            r"+([^ ]+) +([^ ]+) +([^ ]+) +([^ ]+) "
            r"+([^ ]+) +(.*)\n")

    def input(self):
        yield from CLIHelper().lsof_bMnlP() or []

    @property
    def fields(self):
        return [
            ('command', str),
            ('pid', int),
            ('tid', int),
            ('user', int),
            ('fd', str),
            ('type', str),
            ('device', str),
            ('size_off', str),
            # Although this column is designated as `inode` number,
            # sockets tend to write L4 protocol name (e.g. TCP)
            # here as well..
            ('node', lambda x: int(x) if x.isnumeric() else x),
            ('name', lambda x: x.strip())
        ]

    def __init__(self) -> None:
        super().__init__()
        self.parse()

    def all_with_inode(self, inode):
        return list(filter(lambda x: (x.node == inode), self._data))


class NetLink(STOVParser):
    """
    Provides a way to extract fields from /proc/net/netlink.

    Expected file format is:

    sk               Eth Pid    Groups   Rmem Wmem Dump Locks Drops Inode
    0000000000000000 0   23984  00000113 0    0    0    2     0     129906
    0000000000000000 0   142171 00000113 0    0    0    2     0     411370
    /*...*/
    """

    def header_matcher(self):
        return re.compile(
            r"sk +Eth +Pid +Groups +Rmem +Wmem +Dump +Locks +Drops +Inode\n")

    def field_matcher(self):
        return re.compile(
            r"(\d+) +(\d+) +(\d+) +([\da-fA-F]+) "
            r"+(\d+) +(\d+) +(\d+) +(\d+) +(\d+) "
            r"+(\d+) *\n")

    def input(self):
        path = os.path.join(HotSOSConfig.data_root,
                            'proc/net/netlink')
        if not os.path.exists(path):
            log.debug("file not found '%s' - skipping load", path)
            return []

        yield from open(path)

    @property
    def fields(self):
        return [
            # socket pointer addr
            ('sk_addr', lambda v: int(v, 16)),
            # which protocol this socket belongs in this network family
            ('sk_protocol', int),
            # Netlink port id (Pid)
            ('netlink_port_id', int),
            # Netlink groups
            ('netlink_groups', lambda v: int(v, 16)),
            # Allocated rmem for the socket
            ('sk_rmem', int),
            # Allocated wmem for the socket
            ('sk_wmem', int),
            # Netlink dump running?
            ('netlink_dump', int),
            # Socket reference count
            ('sk_references', int),
            # Dropped packet counter
            ('sk_drops', int),
            # Socket's inode number
            ('sk_inode_num', int)
        ]

    def __init__(self) -> None:
        super().__init__()
        self.parse()

    def all_with_drops(self):
        v = list(filter(lambda x: (x.sk_drops > 0), self._data))
        if v:
            # Correlate netlink sockets with process id's by inode
            # only if there's matching data.
            lsof = Lsof()
            for nlsock in v:
                correlate_result = lsof.all_with_inode(nlsock.sk_inode_num)
                nlsock.procs = set(
                    [f"{v.command}/{v.pid}" for v in correlate_result])
        return v
