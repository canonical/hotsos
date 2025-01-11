import re
import subprocess
from functools import cached_property

from hotsos.core.host_helpers.common import get_ps_axo_flags_available
from hotsos.core.host_helpers import (
    CLIHelper,
    CLIHelperFile,
    SystemdHelper,
)
from hotsos.core.search import (
    FileSearcher,
    SearchDef
)
from hotsos.core.utils import seconds_to_date


class CephDaemonBase():
    """ Base class for all Ceph daemon implementations. """
    def __init__(self, daemon_type):
        self.daemon_type = daemon_type
        self.id = None
        self.date_in_secs = self.get_date_secs()

    @classmethod
    def get_date_secs(cls, datestring=None):
        if datestring:
            cmd = ["date", "--utc", f"--date={datestring}", "+%s"]
            date_in_secs = subprocess.check_output(cmd)
        else:
            date_in_secs = CLIHelper().date() or 0
            if date_in_secs:
                date_in_secs = date_in_secs.strip()

        return int(date_in_secs)

    @cached_property
    def rss(self):
        """Return memory RSS for a given daemon.

        NOTE: this assumes we have ps auxwwwm format.
        """
        s = FileSearcher()
        # columns: USER PID %CPU %MEM VSZ RSS TTY STAT START TIME COMMAND
        if self.id is not None:
            ceph_id = rf"--id\s+{self.id}"
        else:
            ceph_id = ''

        expr = (r"\S+\s+\d+\s+\S+\s+\S+\s+\d+\s+(\d+)\s+.+/ceph-"
                rf"{self.daemon_type}\s+.+{ceph_id}\s+.+.+")
        sd = SearchDef(expr)
        with CLIHelperFile() as cli:
            ps_out = cli.ps()
            s.add(sd, path=ps_out)
            rss = 0
            # we only expect one result
            for result in s.run().find_by_path(ps_out):
                rss = int(int(result.get(1)) / 1024)
                break

        return f"{rss}M"

    @cached_property
    def etime(self):
        """Return process etime for a given daemon.

        To get etime we have to use ps_axo_flags rather than the default
        ps_auxww.
        """
        if not get_ps_axo_flags_available():
            return None

        if self.id is None:
            return None

        ps_info = []
        daemon = f"ceph-{self.daemon_type}"
        for line in CLIHelper().ps_axo_flags():
            ret = re.compile(daemon).search(line)
            if not ret:
                continue

            expt_tmplt = SystemdHelper.PS_CMD_EXPR_TEMPLATES['absolute']
            ret = re.compile(expt_tmplt.format(daemon)).search(line)
            if ret:
                ps_info.append(ret.group(0))

        if not ps_info:
            return None

        _etime = None
        for cmd in ps_info:
            ret = re.compile(rf".+\s+.+--id {self.id}\s+.+").match(cmd)
            if ret:
                osd_start = ' '.join(cmd.split()[13:17])
                if self.date_in_secs and osd_start:
                    osd_start_secs = self.get_date_secs(datestring=osd_start)
                    osd_uptime_secs = self.date_in_secs - osd_start_secs
                    osd_uptime_str = seconds_to_date(osd_uptime_secs)
                    _etime = osd_uptime_str

        return _etime


class CephMon(CephDaemonBase):
    """ Representation of a Ceph Mon """
    def __init__(self, name):
        super().__init__('mon')
        self.name = name


class CephMDS(CephDaemonBase):
    """ Representation of a Ceph MDS """
    def __init__(self):
        super().__init__('mds')


class CephRGW(CephDaemonBase):
    """ Representation of a Ceph RGW """
    def __init__(self):
        super().__init__('radosgw')


class CephOSD(CephDaemonBase):
    """ Representation of a Ceph OSD """
    def __init__(self, ceph_id, fsid=None, device=None, dump=None):
        super().__init__('osd')
        self.id = ceph_id
        self.fsid = fsid
        self.device = device
        self.dump = dump

    def to_dict(self):
        d = {self.id: {
             'fsid': self.fsid,
             'dev': self.device}}

        if self.devtype:
            d[self.id]['devtype'] = self.devtype

        if self.etime:
            d[self.id]['etime'] = self.etime

        if self.rss:
            d[self.id]['rss'] = self.rss

        return d

    @cached_property
    def devtype(self):
        osd_tree = CLIHelper().ceph_osd_df_tree_json_decoded()
        if not osd_tree:
            return None

        _devtype = None
        for node in osd_tree.get('nodes'):
            if node.get('type') == 'osd' and node['id'] == self.id:
                _devtype = node['device_class']

        return _devtype
