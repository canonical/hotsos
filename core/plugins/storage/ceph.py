import os
import re

from core import (
    checks,
    constants,
    host_helpers,
    utils,
)
from core.cli_helpers import get_ps_axo_flags_available
from core.cli_helpers import CLIHelper
from core.plugins.storage import StorageBase
from core.searchtools import (
    FileSearcher,
    SequenceSearchDef,
    SearchDef
)
from core.utils import mktemp_dump


CEPH_SERVICES_EXPRS = [r"ceph-[a-z0-9-]+",
                       r"rados[a-z0-9-:]+"]
CEPH_PKGS_CORE = [r"ceph",
                  r"rados",
                  r"rbd",
                  ]
CEPH_PKGS_OTHER = []
# Add in clients/deps
for pkg in CEPH_PKGS_CORE:
    CEPH_PKGS_OTHER.append(r"python3?-{}\S*".format(pkg))

CEPH_LOGS = "var/log/ceph/"

CEPH_REL_INFO = {
    'ceph-common': {
        'pacific': '16.0',
        'octopus': '15.0',
        'nautilus': '14.0',
        'mimic': '13.0',
        'luminous': '12.0',
        'kraken': '11.0',
        'jewel': '10.0'},
    }


class CephConfig(checks.SectionalConfigBase):
    def __init__(self, *args, **kwargs):
        path = os.path.join(constants.DATA_ROOT, 'etc/ceph/ceph.conf')
        super().__init__(path=path, *args, **kwargs)


class CephDaemonBase(object):

    def __init__(self, daemon_type):
        self.daemon_type = daemon_type
        self.cli = CLIHelper()
        self.date_in_secs = utils.get_date_secs()
        self._version_info = None
        # create file-based caches of useful commands so they can be searched.
        self.cli_cache = {'ceph_mon_dump': self.cli.ceph_mon_dump(),
                          'ceph_osd_dump': self.cli.ceph_osd_dump(),
                          'ceph_versions': self.cli.ceph_versions()}
        for cmd, output in self.cli_cache.items():
            self.cli_cache[cmd] = utils.mktemp_dump('\n'.join(output))

    def __del__(self):
        """ Ensure temp files/dirs are deleted. """
        for tmpfile in self.cli_cache.values():
            if os.path.exists(tmpfile):
                os.unlink(tmpfile)

    def _get_version_info(self):
        """
        Returns a dict of veph versions info for our daemon type.
        """
        if self._version_info:
            return self._version_info

        out = self.cli_cache['ceph_versions']
        if not out:
            return

        versions = {}
        s = FileSearcher()
        sd = SequenceSearchDef(
            start=SearchDef(r"^\s+\"{}\":".format(self.daemon_type)),
            body=SearchDef([r"\s+\"ceph version (\S+) .+ (\S+) "
                            r"\(\S+\)\":\s+(\d)+$"]),
            end=SearchDef(r"^\s+\"\S+\":"),
            tag="versions")
        s.add_search_term(sd, path=self.cli_cache['ceph_versions'])
        for section in s.search().find_sequence_sections(sd).values():
            for result in section:
                if result.tag == sd.body_tag:
                    version = result.get(1)
                    rname = result.get(2)
                    amount = result.get(3)
                    versions[version] = {'release_name': rname,
                                         'count': int(amount)}

        if versions:
            self._version_info = versions

        return self._version_info

    @property
    def versions(self):
        """
        Returns a dict of versions of our daemon type associated with the
        number of each that is running. Ideally this would only return a single
        version showing that all daemons are in sync but sometimes e.g.
        during an upgrade this may not be the case.
        """
        _versions = {}
        version_info = self._get_version_info()
        if version_info:
            for ver, info in version_info.items():
                _versions[ver] = info['count']

        if _versions:
            return _versions

    @property
    def release_names(self):
        """
        Same as versions property but with release names instead of versions.
        """
        _releases = {}
        version_info = self._get_version_info()
        if version_info:
            for info in version_info.values():
                rname = info['release_name']
                if rname in _releases:
                    _releases[rname] += info['count']
                else:
                    _releases[rname] = info['count']

        if _releases:
            return _releases


class CephMon(CephDaemonBase):

    def __init__(self):
        super().__init__('mon')
        self._mon_dump = None

    @property
    def mon_dump(self):
        if self._mon_dump:
            return self._mon_dump

        out = self.cli_cache['ceph_mon_dump']
        if not out:
            return

        dump = {}
        s = FileSearcher()
        s.add_search_term(SearchDef(r"^(\S+)\s+(.+)", tag='dump'),
                          path=self.cli_cache['ceph_mon_dump'])
        for result in s.search().find_by_tag('dump'):
            dump[result.get(1)] = result.get(2)

        if dump:
            self._mon_dump = dump

        return self._mon_dump


class CephMDS(CephDaemonBase):

    def __init__(self):
        super().__init__('mds')


class CephRGW(CephDaemonBase):

    def __init__(self):
        super().__init__('radosgw')


class CephOSD(CephDaemonBase):

    def __init__(self, id, fsid, device):
        super().__init__('osd')
        self.id = id
        self.fsid = fsid
        self.device = device
        self._devtype = None
        self._etime = None
        self._rss = None
        self._osd_dump = None

    @property
    def osd_dump(self):
        if self._osd_dump:
            return self._osd_dump

        out = self.cli_cache['ceph_osd_dump']
        if not out:
            return

        dump = {}
        s = FileSearcher()
        s.add_search_term(SearchDef(r"^(\S+)\s+(.+)", tag='dump'),
                          path=self.cli_cache['ceph_osd_dump'])
        for result in s.search().find_by_tag('dump'):
            dump[result.get(1)] = result.get(2)

        if dump:
            self._osd_dump = dump

        return self._osd_dump

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

    @property
    def rss(self):
        """Return memory RSS for a given OSD.

        NOTE: this assumes we have ps auxwwwm format.
        """
        if self._rss:
            return self._rss

        f_osd_ps_cmds = mktemp_dump(''.join(self.cli.ps()))

        s = FileSearcher()
        # columns: USER PID %CPU %MEM VSZ RSS TTY STAT START TIME COMMAND
        sd = SearchDef(r"\S+\s+\d+\s+\S+\s+\S+\s+\d+\s+(\d+)\s+.+/ceph-osd\s+"
                       r".+--id\s+{}\s+.+".format(self.id))
        s.add_search_term(sd, path=f_osd_ps_cmds)
        rss = 0
        # we only expect one result
        for result in s.search().find_by_path(f_osd_ps_cmds):
            rss = int(int(result.get(1)) / 1024)
            break

        os.unlink(f_osd_ps_cmds)
        self._rss = "{}M".format(rss)
        return self._rss

    @property
    def etime(self):
        """Return process etime for a given OSD.

        To get etime we have to use ps_axo_flags rather than the default
        ps_auxww.
        """
        if self._etime:
            return self._etime

        if not get_ps_axo_flags_available():
            return

        ps_osds = []
        for line in self.cli.ps_axo_flags():
            ret = re.compile("ceph-osd").search(line)
            if not ret:
                continue

            expt_tmplt = checks.SVC_EXPR_TEMPLATES["absolute"]
            ret = re.compile(expt_tmplt.format("ceph-osd")).search(line)
            if ret:
                ps_osds.append(ret.group(0))

        if not ps_osds:
            return

        for cmd in ps_osds:
            ret = re.compile(r".+\s+.+--id {}\s+.+".format(
                             self.id)).match(cmd)
            if ret:
                osd_start = ' '.join(cmd.split()[13:17])
                if self.date_in_secs and osd_start:
                    osd_start_secs = utils.get_date_secs(datestring=osd_start)
                    osd_uptime_secs = (self.date_in_secs - osd_start_secs)
                    osd_uptime_str = utils.seconds_to_date(osd_uptime_secs)
                    self._etime = osd_uptime_str

        return self._etime

    @property
    def devtype(self):
        if self._devtype:
            return self._devtype

        for line in self.cli.ceph_osd_tree():
            if line.split()[3] == "osd.{}".format(self.id):
                self._devtype = line.split()[1]

        return self._devtype


class CephChecksBase(StorageBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ceph_config = CephConfig()
        self._bcache_info = []
        self._osds = {}
        self.apt_check = checks.APTPackageChecksBase(
                                                core_pkgs=CEPH_PKGS_CORE,
                                                other_pkgs=CEPH_PKGS_OTHER)
        self.cli = CLIHelper()

        # create file-based caches of useful commands so they can be searched.
        self.cli_cache = {'udevadm_info_exportdb':
                          self.cli.udevadm_info_exportdb(),
                          'ceph_volume_lvm_list':
                          self.cli.ceph_volume_lvm_list()}
        for cmd, output in self.cli_cache.items():
            self.cli_cache[cmd] = utils.mktemp_dump('\n'.join(output))

    def __del__(self):
        """ Ensure temp files/dirs are deleted. """
        for tmpfile in self.cli_cache.values():
            if os.path.exists(tmpfile):
                os.unlink(tmpfile)

    @property
    def plugin_runnable(self):
        if self.apt_check.core:
            return True

        return False

    @property
    def output(self):
        if self._output:
            return {"ceph": self._output}

    @property
    def release_name(self):
        relname = 'unknown'

        # First try from package version (TODO: add more)
        pkg = 'ceph-common'
        if pkg in self.apt_check.core:
            for rel, ver in sorted(CEPH_REL_INFO[pkg].items(),
                                   key=lambda i: i[1], reverse=True):
                if self.apt_check.core[pkg] > \
                        checks.DPKGVersionCompare(ver):
                    relname = rel
                    break

        return relname

    @property
    def bind_interfaces(self):
        """
        If ceph is using specific network interfaces, return them as a dict.
        """
        pub_net = self.ceph_config.get('public network')
        pub_addr = self.ceph_config.get('public addr')
        clus_net = self.ceph_config.get('cluster network')
        clus_addr = self.ceph_config.get('cluster addr')

        interfaces = {}
        if not any([pub_net, pub_addr, clus_net, clus_addr]):
            return interfaces

        nethelp = host_helpers.HostNetworkingHelper()

        if pub_net:
            iface = nethelp.get_interface_with_addr(pub_net).to_dict()
            interfaces.update(iface)
        elif pub_addr:
            iface = nethelp.get_interface_with_addr(pub_addr).to_dict()
            interfaces.update(iface)

        if clus_net:
            iface = nethelp.get_interface_with_addr(clus_net).to_dict()
            interfaces.update(iface)
        elif clus_addr:
            iface = nethelp.get_interface_with_addr(clus_addr).to_dict()
            interfaces.update(iface)

        return interfaces

    def _get_osds(self):
        if not self.cli_cache['ceph_volume_lvm_list']:
            return

        s = FileSearcher()
        sd = SequenceSearchDef(start=SearchDef(r"^=+\s+osd\.(\d+)\s+=+.*"),
                               body=SearchDef([r"\s+osd\s+(fsid)\s+(\S+)\s*",
                                               r"\s+(devices)\s+([\S]+)\s*"]),
                               tag="ceph-lvm")
        s.add_search_term(sd, path=self.cli_cache['ceph_volume_lvm_list'])
        osds = []
        for results in s.search().find_sequence_sections(sd).values():
            id = None
            fsid = None
            dev = None
            for result in results:
                if result.tag == sd.start_tag:
                    id = int(result.get(1))
                elif result.tag == sd.body_tag:
                    if result.get(1) == "fsid":
                        fsid = result.get(2)
                    elif result.get(1) == "devices":
                        dev = result.get(2)

            osds.append(CephOSD(id, fsid, dev))

        return osds

    @property
    def osds(self):
        """ Get key information about OSDs. """
        if self._osds:
            return self._osds

        self._osds = self._get_osds()
        return self._osds

    @property
    def bcache_info(self):
        """ If bcache devices exist fetch information and return as a dict. """
        if self._bcache_info:
            return self._bcache_info

        devs = []
        if not self.cli_cache['udevadm_info_exportdb']:
            return devs

        s = FileSearcher()
        sdef = SequenceSearchDef(start=SearchDef(r"^P: .+/(bcache\S+)"),
                                 body=SearchDef(r"^S: disk/by-uuid/(\S+)"),
                                 tag="bcacheinfo")
        s.add_search_term(sdef, self.cli_cache['udevadm_info_exportdb'])
        results = s.search()
        for section in results.find_sequence_sections(sdef).values():
            dev = {}
            for r in section:
                if r.tag == sdef.start_tag:
                    dev["name"] = r.get(1)
                else:
                    dev["by-uuid"] = r.get(1)

            devs.append(dev)

        self._bcache_info = devs
        return self._bcache_info

    def is_bcache_device(self, dev):
        """
        Returns True if the device either is or is based on a bcache device
        e.g. dmcrypt device using bcache dev.
        """
        if dev.startswith("bcache"):
            return True

        if dev.startswith("/dev/bcache"):
            return True

        ret = re.compile(r"/dev/mapper/crypt-(\S+)").search(dev)
        if ret:
            for dev in self.bcache_info:
                if dev.get("by-uuid") == ret.group(1):
                    return True

    @property
    def bluestore_enabled(self):
        """
        If any of the following are enabled in ceph.conf (by the charm) it
        indicates that bluestore=True.
        """
        bs_key_vals = {('enable experimental unrecoverable data corrupting '
                        'features'): 'bluestore',
                       'osd objectstore': 'bluestore'}
        bs_keys = ['bluestore block wal size', 'bluestore block db size',
                   r'bluestore compression .+']

        for keys in self.ceph_config.all.values():
            for conf_key in keys:
                if conf_key in bs_keys:
                    return True

                for key in bs_keys:
                    if re.compile(key).match(conf_key):
                        return True

        for key, val in bs_key_vals.items():
            conf_val = self.ceph_config.get(key)
            if conf_val and val in conf_val:
                return True

        return False


class CephServiceChecksBase(CephChecksBase, checks.ServiceChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(service_exprs=CEPH_SERVICES_EXPRS, *args, **kwargs)


class CephEventChecksBase(CephChecksBase, checks.EventChecksBase):

    def __call__(self):
        ret = self.run_checks()
        if ret:
            self._output.update(ret)
