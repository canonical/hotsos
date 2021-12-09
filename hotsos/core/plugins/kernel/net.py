import abc
import os

from hotsos.core.log import log
from hotsos.core.config import HotSOSConfig


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

    def _process_file(self, fname):
        if not os.path.exists(fname):
            log.info("file not found '%s' - skipping load")
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
        self._process_file(os.path.join(HotSOSConfig.DATA_ROOT,
                                        'proc/net/snmp'))


class SNMPTcp(SNMPBase):

    @property
    def outretrans_pcent(self):
        if not self.OutSegs:
            return 0

        return round((self.RetransSegs * 100.0) / self.OutSegs, 2)

    @property
    def incsumrate_pcent(self):
        """
        Tcp: InCsumErrors    number of TCP segments received with bad checksum
        """
        if not self.InCsumErrors:
            return 0

        # Misc checks
        return round((self.InCsumErrors * 100.0) / self.InSegs, 2)

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


class SNMPUdp(SNMPBase):

    @property
    def _header(self):
        return 'Udp'

    @property
    def inerrors_pcent(self):
        if not self.InErrors or not self.InDatagrams:
            return 0

        return round((self.InErrors * 100.0) / self.InDatagrams, 2)

    @property
    def incsumerrors_pcent(self):
        if not self.InCsumErrors:
            return 0

        return round((self.InCsumErrors * 100.0) / self.InDatagrams, 2)

    @property
    def _fields(self):
        return ['InDatagrams',
                'NoPorts',
                'InErrors',
                'OutDatagrams',
                'RcvbufErrors',
                'SndbufErrors',
                'InCsumErrors']


class NetStatBase(ProcNetBase):

    def __init__(self):
        super().__init__()
        self._process_file(os.path.join(HotSOSConfig.DATA_ROOT,
                                        'proc/net/netstat'))


class NetStatTCP(NetStatBase):

    @property
    def spurrtx_pcent(self):
        if not self.TCPSpuriousRtxHostQueues:
            return 0

        outsegs = SNMPTcp().OutSegs
        return round((self.TCPSpuriousRtxHostQueues * 100.0) / outsegs, 2)

    @property
    def _header(self):
        return 'TcpExt'

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
