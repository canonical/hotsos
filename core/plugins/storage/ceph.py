import os
import re

from core import (
    checks,
    constants,
    host_helpers,
    utils,
)
from core.ycheck.events import YEventCheckerBase
from core.cli_helpers import get_ps_axo_flags_available
from core.cli_helpers import CLIHelper
from core.plugins.storage import StorageBase
from core.searchtools import (
    FileSearcher,
    SequenceSearchDef,
    SearchDef
)


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

CEPH_POOL_TYPE = {1: 'replicated', 3: 'erasure-coded'}


class CephConfig(checks.SectionalConfigBase):
    def __init__(self, *args, **kwargs):
        path = os.path.join(constants.DATA_ROOT, 'etc/ceph/ceph.conf')
        super().__init__(path=path, *args, **kwargs)


class CephCluster(object):

    def __init__(self):
        self.cli = CLIHelper()
        # create file-based caches of useful commands so they can be searched.
        self.cli_cache = {'ceph_versions': self.cli.ceph_versions()}
        for cmd, output in self.cli_cache.items():
            self.cli_cache[cmd] = utils.mktemp_dump('\n'.join(output))

    def __del__(self):
        """ Ensure temp files/dirs are deleted. """
        for tmpfile in self.cli_cache.values():
            if os.path.exists(tmpfile):
                os.unlink(tmpfile)

    def _get_version_info(self, daemon_type=None):
        """
        Returns a dict of ceph versions info for the provided daemon type. If
        no daemon type provided, version info is collected for all types and
        the resulting dict is keyed by daemon type otherwise it is keyed by
        version (and only versions for that daemon type.)
        """
        out = self.cli_cache['ceph_versions']
        if not out:
            return

        versions = {}
        s = FileSearcher()
        body = SearchDef(r"\s+\"ceph version (\S+) .+ (\S+) "
                         r"\(\S+\)\":\s+(\d)+,?$")
        if daemon_type is None:
            # all/any - start matches any so no seq ending needed
            sd = SequenceSearchDef(start=SearchDef(r"^\s+\"(\S+)\":\s+{"),
                                   body=body, tag='versions')
        else:
            start = SearchDef(r"^\s+\"({})\":\s+{{".format(daemon_type))
            sd = SequenceSearchDef(start=start, body=body,
                                   end=SearchDef(r"^\s+\"\S+\":\s+{"),
                                   tag='versions')

        s.add_search_term(sd, path=self.cli_cache['ceph_versions'])
        for section in s.search().find_sequence_sections(sd).values():
            _versions = {}
            for result in section:
                if result.tag == sd.start_tag:
                    _daemon_type = result.get(1)
                    versions[_daemon_type] = _versions
                elif result.tag == sd.body_tag:
                    version = result.get(1)
                    rname = result.get(2)
                    amount = result.get(3)
                    _versions[version] = {'release_name': rname,
                                          'count': int(amount)}

        # If specific daemon_type provided only return version for that type
        # otherwise all.
        if daemon_type is not None:
            versions = versions.get(daemon_type)

        return versions

    def daemon_versions(self, daemon_type=None):
        """
        Returns a dict of versions of daemon type associated with the
        number of each that is running. Ideally this would only return a single
        version showing that all daemons are in sync but sometimes e.g.
        during an upgrade this may not be the case.
        """
        _versions = {}
        version_info = self._get_version_info(daemon_type)
        if version_info:
            if daemon_type:
                for ver, info in version_info.items():
                    _versions[ver] = info['count']
            else:
                for daemon, _version_info in version_info.items():
                    for ver, info in _version_info.items():
                        if daemon not in _versions:
                            _versions[daemon] = {}

                        _versions[daemon][ver] = info['count']

        return _versions

    def daemon_release_names(self, daemon_type=None):
        """
        Same as versions property but with release names instead of versions.
        """
        _releases = {}
        version_info = self._get_version_info(daemon_type)
        if version_info:
            if daemon_type:
                for info in version_info.values():
                    rname = info['release_name']
                    if rname in _releases:
                        _releases[rname] += info['count']
                    else:
                        _releases[rname] = info['count']
            else:
                for daemon, _version_info in version_info.items():
                    for info in _version_info.values():
                        if daemon not in _releases:
                            _releases[daemon] = {}

                        rname = info['release_name']
                        if rname in _releases:
                            _releases[daemon][rname] += info['count']
                        else:
                            _releases[daemon][rname] = info['count']

        return _releases


class CephDaemonBase(object):

    def __init__(self, daemon_type):
        self.daemon_type = daemon_type
        self.cli = CLIHelper()
        self.date_in_secs = utils.get_date_secs()
        self._version_info = None
        self._etime = None
        self._rss = None
        self.cluster = CephCluster()
        # create file-based caches of useful commands so they can be searched.
        self.cli_cache = {'ps': self.cli.ps()}
        for cmd, output in self.cli_cache.items():
            self.cli_cache[cmd] = utils.mktemp_dump('\n'.join(output))

    def __del__(self):
        """ Ensure temp files/dirs are deleted. """
        for tmpfile in self.cli_cache.values():
            if os.path.exists(tmpfile):
                os.unlink(tmpfile)

    @property
    def rss(self):
        """Return memory RSS for a given daemon.

        NOTE: this assumes we have ps auxwwwm format.
        """
        if self._rss:
            return self._rss

        s = FileSearcher()
        # columns: USER PID %CPU %MEM VSZ RSS TTY STAT START TIME COMMAND
        sd = SearchDef(r"\S+\s+\d+\s+\S+\s+\S+\s+\d+\s+(\d+)\s+.+/ceph-{}\s+"
                       r".+--id\s+{}\s+.+".format(self.daemon_type, self.id))
        s.add_search_term(sd, path=self.cli_cache['ps'])
        rss = 0
        # we only expect one result
        for result in s.search().find_by_path(self.cli_cache['ps']):
            rss = int(int(result.get(1)) / 1024)
            break

        self._rss = "{}M".format(rss)
        return self._rss

    @property
    def etime(self):
        """Return process etime for a given daemon.

        To get etime we have to use ps_axo_flags rather than the default
        ps_auxww.
        """
        if self._etime:
            return self._etime

        if not get_ps_axo_flags_available():
            return

        ps_info = []
        daemon = "ceph-{}".format(self.daemon_type)
        for line in self.cli.ps_axo_flags():
            ret = re.compile(daemon).search(line)
            if not ret:
                continue

            expt_tmplt = checks.SVC_EXPR_TEMPLATES["absolute"]
            ret = re.compile(expt_tmplt.format(daemon)).search(line)
            if ret:
                ps_info.append(ret.group(0))

        if not ps_info:
            return

        for cmd in ps_info:
            ret = re.compile(r".+\s+.+--id {}\s+.+".format(self.id)).match(cmd)
            if ret:
                osd_start = ' '.join(cmd.split()[13:17])
                if self.date_in_secs and osd_start:
                    osd_start_secs = utils.get_date_secs(datestring=osd_start)
                    osd_uptime_secs = (self.date_in_secs - osd_start_secs)
                    osd_uptime_str = utils.seconds_to_date(osd_uptime_secs)
                    self._etime = osd_uptime_str

        return self._etime

    @property
    def versions(self):
        """
        Returns a dict of versions of our daemon type associated with the
        number of each that is running. Ideally this would only return a single
        version showing that all daemons are in sync but sometimes e.g.
        during an upgrade this may not be the case.
        """
        return self.cluster.daemon_versions(self.daemon_type)

    @property
    def release_names(self):
        """
        Same as versions property but with release names instead of versions.
        """
        return self.cluster.daemon_release_names(self.daemon_type)


class CephMon(CephDaemonBase):

    def __init__(self):
        super().__init__('mon')

    @property
    def osdmaps_count(self):
        report = self.cli.ceph_report_json_decoded()
        if not report:
            return 0

        try:
            return len(report['osdmap_manifest']['pinned_maps'])
        except (ValueError, KeyError):
            return 0


class CephMDS(CephDaemonBase):

    def __init__(self):
        super().__init__('mds')


class CephRGW(CephDaemonBase):

    def __init__(self):
        super().__init__('radosgw')


class CephOSD(CephDaemonBase):

    def __init__(self, id, fsid=None, device=None):
        super().__init__('osd')
        self.id = id
        self.fsid = fsid
        self.device = device
        self._devtype = None

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
        self._crush_rules = []
        self._local_osds = None
        self._cluster_osds = None
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
    def health_status(self):
        health = None
        status = self.cli.ceph_status_json_decoded()
        if status:
            health = status['health']['status']

        return health

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

    def _get_bind_interfaces(self, type):
        """
        For the given config network type determine what interface ceph is
        binding to.

        @param type: cluster or public
        """
        net = self.ceph_config.get('{} network'.format(type))
        addr = self.ceph_config.get('{} addr'.format(type))
        if not any([net, addr]):
            return {}

        nethelp = host_helpers.HostNetworkingHelper()
        port = None
        if net:
            port = nethelp.get_interface_with_addr(net)
        elif addr:
            port = nethelp.get_interface_with_addr(addr)

        if port:
            return {type: port}

    @property
    def bind_interfaces(self):
        """
        Returns a dict of network interfaces used by Ceph daemons on this host.
        The dict has the form {<type>: [<port>, ...]}
        """
        interfaces = {}
        for type in ['cluster', 'public']:
            ret = self._get_bind_interfaces(type)
            if ret:
                interfaces.update(ret)

        return interfaces

    @property
    def bind_interface_names(self):
        """
        Returns a list of names for network interfaces used by Ceph daemons on
        this host.
        """
        names = [iface.name for iface in self.bind_interfaces.values()]
        return ', '.join(list(set(names)))

    @property
    def osd_dump(self):
        return self.cli.ceph_osd_dump_json_decoded()

    def _get_cluster_osds(self):
        cluster_osds = []
        for osd in self.osd_dump.get('osds', {}):
            cluster_osds.append(CephOSD(osd['osd']))

        return cluster_osds

    def _get_local_osds(self):
        if not self.cli_cache['ceph_volume_lvm_list']:
            return

        s = FileSearcher()
        sd = SequenceSearchDef(start=SearchDef(r"^=+\s+osd\.(\d+)\s+=+.*"),
                               body=SearchDef([r"\s+osd\s+(fsid)\s+(\S+)\s*",
                                               r"\s+(devices)\s+([\S]+)\s*"]),
                               tag="ceph-lvm")
        s.add_search_term(sd, path=self.cli_cache['ceph_volume_lvm_list'])
        local_osds = []
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

            local_osds.append(CephOSD(id, fsid, dev))

        return local_osds

    @property
    def cluster_osds(self):
        """ Returns a list of CephOSD objects for all osds in the cluster. """
        if self._cluster_osds:
            return self._cluster_osds

        self._cluster_osds = self._get_cluster_osds()
        return self._cluster_osds

    @property
    def local_osds(self):
        """
        Returns a list of CephOSD objects for osds found on the local host.
        """
        if self._local_osds:
            return self._local_osds

        self._local_osds = self._get_local_osds()
        return self._local_osds

    def _filter_pools_by_rule(self, pools, crush_rule):
        res_pool = []
        for pool in pools:
            if pool['crush_rule'] == crush_rule:
                pool_str = pool['pool_name'] + ' (' + str(pool['pool']) + ')'
                res_pool.append(pool_str)

        return res_pool

    @property
    def crush_rules(self):
        """
        Returns a list of crush rules, mapped to the respective pools.
        """
        if self._crush_rules:
            return self._crush_rules

        ceph_report = self.cli.ceph_report_json_decoded()
        if not ceph_report:
            return

        rule_to_pool = {}
        for rule in ceph_report['crushmap']['rules']:
            rule_id = rule['rule_id']
            rtype = rule['type']
            pools = self._filter_pools_by_rule(ceph_report['osdmap']['pools'],
                                               rule_id)
            rule_to_pool[rule['rule_name']] = {'id': rule_id,
                                               'type': CEPH_POOL_TYPE[rtype],
                                               'pools': pools}

        self._crush_rules = rule_to_pool
        return self._crush_rules

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

    @property
    def has_interface_errors(self):
        """
        Checks if any network interfaces used by Ceph are showing packet
        errors.

        Returns True if errors found otherwise False.
        """
        for port in self.bind_interfaces.values():
            for stats in port.stats.values():
                if stats.get('errors'):
                    return True

        return False


class CephServiceChecksBase(CephChecksBase, checks.ServiceChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(service_exprs=CEPH_SERVICES_EXPRS, *args, **kwargs)


class CephEventChecksBase(CephChecksBase, YEventCheckerBase):

    def __call__(self):
        ret = self.run_checks()
        if ret:
            self._output.update(ret)
