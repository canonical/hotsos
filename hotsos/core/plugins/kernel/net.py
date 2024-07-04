import abc
import os
from collections import OrderedDict, UserList

from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import SYSCtlFactory, CLIHelperFile
from hotsos.core.log import log
from hotsos.core.search import FileSearcher, SearchDef, ResultFieldInfo


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

    @property
    @abc.abstractmethod
    def _header(self):
        """
        """

    @property
    @abc.abstractmethod
    def _fields(self):
        """
        """

    def __getattr__(self, fld):
        if fld in self._fields:
            return self._get_field(self._header, fld)

        raise AttributeError(f"{fld} not found in {self.__class__.__name__}")


class SNMPBase(ProcNetBase):

    def __init__(self):
        super().__init__()
        self._process_file(os.path.join(HotSOSConfig.data_root,
                                        'proc/net/snmp'))


class SNMPTcp(SNMPBase):

    def _percent_in_segs(self, field):
        """
        The value of a field can be provided as a percentage of the total rx
        segments.
        """
        return self._pcent_of(field, self.InSegs)

    def _percent_out_segs(self, field):
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
            return self._percent_in_segs(fld)
        if fld.endswith('PcentOutSegs'):
            fld = fld.partition('PcentOutSegs')[0]
            return self._percent_out_segs(fld)

        return super().__getattr__(fld)


class SNMPUdp(SNMPBase):

    @property
    def _header(self):
        return 'Udp'

    def _percent_in_datagrams(self, field):
        """
        The value of a field can be provided as a percentage of the total rx
        datagrams.
        """
        return self._pcent_of(field, self.InDatagrams)

    def _percent_out_datagrams(self, field):
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
            return self._percent_in_datagrams(fld)
        if fld.endswith('PcentOutDatagrams'):
            fld = fld.partition('PcentOutDatagrams')[0]
            return self._percent_out_datagrams(fld)

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

    def _percent_in_segs(self, field):
        """
        The value of a field can be provided as a percentage of the total rx
        segments.
        """
        return self._pcent_of(field, self.net_snmp_tcp.InSegs)

    def _percent_out_segs(self, field):
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
            return self._percent_in_segs(fld)
        if fld.endswith('PcentOutSegs'):
            fld = fld.partition('PcentOutSegs')[0]
            return self._percent_out_segs(fld)

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
        xmem = getattr(SYSCtlFactory(), f'net.ipv4.{key.lower()}_mem')
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
                        self._data[key]["sysctl_mem_max"] else 0) * 100.0, 2)

    def _process_file(self, fname):
        if not os.path.exists(fname):
            log.debug("file not found '%s' - skipping load", fname)
            return None

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
                    stats = dict(stats[i:i + 2]
                                 for i in range(0, len(stats), 2))
                    # Convert string values to `int``
                    stats = {k: int(v) for k, v in stats.items()}
                    self._data[label] = stats
                except ValueError as e:
                    log.warning("badness: failed to parse statistics "
                                "for `%s`, bad data `%s` (%s)",
                                label, stats, e)
                    continue

        return None

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

        raise AttributeError(f"{fld} not found in {self.__class__.__name__}")


class STOVParserBase(UserList):

    def __init__(self):
        super().__init__()
        self._load()

    @abc.abstractmethod
    def _load(self):
        """ Load data from source. """

    @property
    @abc.abstractmethod
    def _search_field_info(self):
        """
        Returns a ResultFieldInfo object to make columns addressable by their
        name as well as mapping them to a specific type.
        """

    @property
    @abc.abstractmethod
    def _header_matcher(self):
        """ python.re regular expression to match each header. """

    @property
    @abc.abstractmethod
    def _field_matcher(self):
        """ python.re regular expression to match each row. """

    @property
    @abc.abstractmethod
    def fields(self):
        """
        This is a dictionary of fields exposed by this object along with their
        type. This provides an opportunity to split/translate fields into sub
        fields but can also mirror _search_field_info.
        """


class FieldTranslator():

    def __init__(self, result, translations):
        self.result = result
        self.translations = translations

    def __getattr__(self, key):
        if key in self.translations:
            return self.translations[key](self.result)

        return getattr(self.result, key)


class Lsof(STOVParserBase):
    """
    Provides a way to extract fields from lsof output.

    Expected file format is:

    COMMAND PID USER  FD TYPE DEVICE SIZE/OFF  NODE NAME
    systemd   1 0 cwd  DIR    9,1     4096     2 /
    systemd   1 0 rtd  DIR    9,1     4096     2 /
    systemd   1 0 txt  REG    9,1  1589552 54275 /lib/
    systemd   1 0 mem  REG    9,1    18976 51133 /lib/
    /*...*/
    """

    def _load(self):
        search = FileSearcher()
        with CLIHelperFile() as cli:
            fout = cli.lsof_Mnlc()
            search.add(SearchDef(self._header_matcher, tag='header'), fout)
            search.add(SearchDef(self._field_matcher, tag='content',
                                 field_info=self._search_field_info), fout)
            results = search.run()
            for r in results.find_by_tag('content'):
                self.data.append(r)

    @staticmethod
    def _int_if_numeric(value):
        if value.isnumeric():
            return int(value)

        return value

    @staticmethod
    def _strip(value):
        return value.strip()

    @property
    def _search_field_info(self):
        finfo = OrderedDict({'COMMAND': str, 'PID': int, 'USER': int,
                             'FD': str, 'TYPE': str, 'DEVICE': str,
                             'SIZE/OFF': str,
                             # NOTE(mkg): Although this column is designated as
                             #            `inode` number, sockets tend to write
                             #            L4 protocol name (e.g. TCP) here as
                             #            well..
                             'NODE': self._int_if_numeric,
                             'NAME': self._strip})
        return ResultFieldInfo(finfo)

    @property
    def _header_matcher(self):
        return r'\s+'.join(self._search_field_info.keys())

    @property
    def _field_matcher(self):
        expr = []
        for key, vtype in self._search_field_info.items():
            if vtype == int:
                _expr = r'(\d+)'
            elif key == 'NAME':
                _expr = r'(\S+\s*\S*)'
            else:
                _expr = r'(\S+)'

            # These fields can be empty/None
            if key in ['TYPE', 'DEVICE', 'SIZE/OFF', 'NODE']:
                _expr = f'{_expr}?'

            expr.append(_expr)

        return r'\s*' + r'\s+'.join(expr)

    @property
    def fields(self):
        """ This has a one-to-one mapping. """
        return self._search_field_info

    def all_with_inode(self, inode):
        return list(filter(lambda x: (x.NODE == inode), self.data))


class NetLink(STOVParserBase):
    """
    Provides a way to extract fields from /proc/net/netlink.

    Expected file format is:

    sk               Eth Pid    Groups   Rmem Wmem Dump Locks Drops Inode
    0000000000000000 0   23984  00000113 0    0    0    2     0     129906
    0000000000000000 0   142171 00000113 0    0    0    2     0     411370
    /*...*/
    """

    def _load(self):
        search = FileSearcher()
        path = os.path.join(HotSOSConfig.data_root, 'proc/net/netlink')
        search.add(SearchDef(self._header_matcher, tag='header'), path)
        search.add(SearchDef(self._field_matcher, tag='content',
                             field_info=self._search_field_info), path)
        results = search.run()
        for r in results.find_by_tag('content'):
            self.data.append(FieldTranslator(r, self.fields))

    @property
    def _search_field_info(self):
        finfo = OrderedDict({'sk': int, 'Eth': int, 'Pid': int,
                             'Groups': str, 'Rmem': int, 'Wmem': int,
                             'Dump': int, 'Locks': int, 'Drops': int,
                             'Inode': int})
        return ResultFieldInfo(finfo)

    @property
    def _header_matcher(self):
        return r'\s+'.join(self._search_field_info.keys())

    @property
    def _field_matcher(self):
        expr = []
        for vtype in self._search_field_info.values():
            if vtype == int:
                _expr = r'(\d+)'
            else:
                _expr = r'(\S+)'

            expr.append(_expr)

        return r'\s*' + r'\s+'.join(expr)

    @property
    def fields(self):
        return {
            # socket pointer addr
            'sk_addr': lambda result: int(str(getattr(result, 'sk')), 16),
            # which protocol this socket belongs in this network family
            'sk_protocol': lambda result: getattr(result, 'sk'),
            # Netlink port id (Pid)
            'netlink_port_id': lambda result: getattr(result, 'Pid'),
            # Netlink groups
            'netlink_groups': lambda result: int(str(getattr(result,
                                                             'Groups')), 16),
            # Allocated rmem for the socket
            'sk_rmem': lambda result: getattr(result, 'Rmem'),
            # Allocated wmem for the socket
            'sk_wmem': lambda result: getattr(result, 'Wmem'),
            # Netlink dump running?
            'netlink_dump': lambda result: getattr(result, 'Dump'),
            # Socket reference count
            'sk_references': lambda result: getattr(result, 'Locks'),
            # Dropped packet counter
            'sk_drops': lambda result: getattr(result, 'Drops'),
            # Socket's inode number
            'sk_inode_num': lambda result: getattr(result, 'Inode'),
        }

    @property
    def all_with_drops(self):
        v = list(filter(lambda x: (x.sk_drops > 0), self.data))
        if v:
            # Correlate netlink sockets with process id's by inode
            # only if there's matching data.
            lsof = Lsof()
            for nlsock in v:
                correlate_result = lsof.all_with_inode(nlsock.sk_inode_num)
                nlsock.procs = set(
                    f"{v.COMMAND}/{v.PID}" for v in correlate_result)
        return v

    @property
    def all_with_drops_str(self):
        if not self.all_with_drops:
            return None

        drops_info = [
            f"\tnlsock inode `{nlsock.sk_inode_num}`: "
            f"procs[{','.join(nlsock.procs)}]"
            for nlsock in self.all_with_drops]
        return "\n".join(drops_info)
