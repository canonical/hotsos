import os
import re

from hotsos.core import (
    checks,
    host_helpers,
    utils,
)
from hotsos.core.config import HotSOSConfig
from hotsos.core.ycheck.events import YEventCheckerBase
from hotsos.core.cli_helpers import get_ps_axo_flags_available
from hotsos.core.cli_helpers import CLIHelper
from hotsos.core.plugins.storage import StorageBase
from hotsos.core.plugins.storage.bcache import BcacheBase
from hotsos.core.searchtools import (
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
        path = os.path.join(HotSOSConfig.DATA_ROOT, 'etc/ceph/ceph.conf')
        super().__init__(*args, path=path, **kwargs)


class CephCrushMap(object):

    def __init__(self):
        self.cli = CLIHelper()
        self._crush_rules = {}
        self._osd_crush_dump = None
        self._ceph_report = None

    def _filter_pools_by_rule(self, pools, crush_rule):
        res_pool = []
        for pool in pools:
            if pool['crush_rule'] == crush_rule:
                pool_str = pool['pool_name'] + ' (' + str(pool['pool']) + ')'
                res_pool.append(pool_str)

        return res_pool

    @property
    def osd_crush_dump(self):
        if self._osd_crush_dump:
            return self._osd_crush_dump

        dump = self.cli.ceph_osd_crush_dump_json_decoded() or {}
        self._osd_crush_dump = dump
        return self._osd_crush_dump

    @property
    def ceph_report(self):
        if self._ceph_report:
            return self._ceph_report

        dump = self.cli.ceph_report_json_decoded() or {}
        self._ceph_report = dump
        return self._ceph_report

    @property
    def rules(self):
        """
        Returns a list of crush rules, mapped to the respective pools.
        """
        if self._crush_rules:
            return self._crush_rules

        if not self.ceph_report:
            return

        rule_to_pool = {}
        for rule in self.ceph_report['crushmap']['rules']:
            rule_id = rule['rule_id']
            rtype = rule['type']
            pools = self.ceph_report['osdmap']['pools']
            pools = self._filter_pools_by_rule(pools, rule_id)
            rule_to_pool[rule['rule_name']] = {'id': rule_id,
                                               'type': CEPH_POOL_TYPE[rtype],
                                               'pools': pools}

        self._crush_rules = rule_to_pool
        return self._crush_rules

    def _build_buckets_from_crushdump(self, crushdump):
        buckets = {}
        # iterate jp for each bucket
        for bucket in crushdump["buckets"]:
            bid = bucket["id"]
            items = []
            for item in bucket["items"]:
                items.append(item["id"])

            buckets[bid] = {"name": bucket["name"],
                            "type_id": bucket["type_id"],
                            "type_name": bucket["type_name"],
                            "items": items}

        return buckets

    @property
    def crushmap_mixed_buckets(self):
        """
        Report buckets that have mixed type of items,
        as they will cause crush map unable to compute
        the expected up set
        """
        if not self.osd_crush_dump:
            return []

        bad_buckets = []
        buckets = self._build_buckets_from_crushdump(self.osd_crush_dump)
        # check all bucket
        for bid in buckets:
            items = buckets[bid]["items"]
            type_ids = []
            for item in items:
                if item >= 0:
                    type_ids.append(0)
                else:
                    type_ids.append(buckets[item]["type_id"])

            if not type_ids:
                continue

            # verify if the type_id list contain mixed type id
            if type_ids.count(type_ids[0]) != len(type_ids):
                bad_buckets.append(buckets[bid]["name"])

        return bad_buckets

    @property
    def crushmap_mixed_buckets_str(self):
        return ','.join(self.crushmap_mixed_buckets)

    def _is_bucket_imbalanced(self, buckets, start_bucket_id, failure_domain):
        """Return whether a tree is unbalanced

        Recursively determine if a given tree (start_bucket_id) is
        balanced at the given failure domain (failure_domain) in the
        CRUSH tree(s) provided by the buckets parameter.
        """
        unbalanced = False
        weight = -1

        for item in buckets[start_bucket_id]["items"]:
            if buckets[item["id"]]["type_name"] != failure_domain:
                unbalanced = self._is_bucket_imbalanced(buckets,
                                                        item["id"],
                                                        failure_domain)
                if unbalanced:
                    return unbalanced
            # Handle items/buckets with 0 weight correctly, by
            # ignoring them.
            # These are excluded from placement consideration,
            # and therefore do not unbalance a tree.
            elif item["weight"] > 0:
                if weight == -1:
                    weight = item["weight"]
                else:
                    if weight != item["weight"]:
                        unbalanced = True
                        return unbalanced

        return unbalanced

    @property
    def crushmap_equal_buckets(self):
        """
        Report when buckets of the failure domain type in a
        CRUSH rule referenced tree are unbalanced.

        Uses the trees and failure domains referenced in the
        CRUSH rules, and checks that all buckets of the failure
        domain type in the referenced tree are equal.
        """
        if not self.osd_crush_dump:
            return []

        buckets = {b['id']: b for b in self.osd_crush_dump["buckets"]}

        to_check = []
        for rule in self.osd_crush_dump.get('rules', []):
            taken = 0
            fdomain = 0
            for i in rule['steps']:
                if i["op"] == "take":
                    taken = i["item"]
                if "type" in i and taken != 0:
                    fdomain = i["type"]
                if taken != 0 and fdomain != 0:
                    to_check.append((rule["rule_id"], taken, fdomain))
                    taken = fdomain = 0

        unequal_buckets = []
        for ruleid, tree, failure_domain in to_check:
            unbalanced = \
                self._is_bucket_imbalanced(buckets, tree, failure_domain)
            if unbalanced:
                unequal_buckets.append({'root': buckets[tree]["name"],
                                        'domain': failure_domain,
                                        'ruleid': ruleid})

        return unequal_buckets

    @property
    def crushmap_equal_buckets_head_root(self):
        unequal = self.crushmap_equal_buckets
        if unequal:
            return unequal[0].get('root')

    @property
    def crushmap_equal_buckets_head_domain(self):
        unequal = self.crushmap_equal_buckets
        if unequal:
            return unequal[0].get('domain')

    @property
    def crushmap_equal_buckets_head_ruleid(self):
        unequal = self.crushmap_equal_buckets
        if unequal:
            return unequal[0].get('ruleid')


class CephCluster(object):
    OSD_META_LIMIT_KB = (10 * 1024 * 1024)
    OSD_PG_MAX_LIMIT = 500
    OSD_PG_OPTIMAL_NUM_MAX = 200
    OSD_PG_OPTIMAL_NUM_MIN = 50

    def __init__(self):
        self.cli = CLIHelper()
        # create file-based caches of useful commands so they can be searched.
        self.cli_cache = {'ceph_versions': self.cli.ceph_versions()}
        for cmd, output in self.cli_cache.items():
            self.cli_cache[cmd] = utils.mktemp_dump('\n'.join(output))

        self.crush_map = CephCrushMap()
        self._large_omap_pgs = {}
        self._bad_meta_osds = []
        self._cluster_osds = []
        self._cluster_mons = []
        self._mon_dump = None
        self._osd_dump = None
        self._pg_dump = None
        self._osd_df_tree = None
        self._osds_pgs = {}

    def __del__(self):
        """ Ensure temp files/dirs are deleted. """
        for tmpfile in self.cli_cache.values():
            if os.path.exists(tmpfile):
                os.unlink(tmpfile)

    @property
    def health_status(self):
        health = None
        status = self.cli.ceph_status_json_decoded()
        if status:
            health = status['health']['status']

        return health

    @property
    def mon_dump(self):
        if self._mon_dump:
            return self._mon_dump

        self._mon_dump = self.cli.ceph_mon_dump_json_decoded() or {}
        return self._mon_dump

    @property
    def osd_dump(self):
        if self._osd_dump:
            return self._osd_dump

        self._osd_dump = self.cli.ceph_osd_dump_json_decoded() or {}
        return self._osd_dump

    @property
    def pg_dump(self):
        if self._pg_dump:
            return self._pg_dump

        self._pg_dump = self.cli.ceph_pg_dump_json_decoded() or {}
        return self._pg_dump

    @property
    def mons(self):
        if self._cluster_mons:
            return self._cluster_mons

        for mon in self.mon_dump.get('mons', {}):
            self._cluster_mons.append(CephMon(mon['name']))

        return self._cluster_mons

    @property
    def osd_df_tree(self):
        if self._osd_df_tree:
            return self._osd_df_tree

        self._osd_df_tree = self.cli.ceph_osd_df_tree_json_decoded() or {}
        return self._osd_df_tree

    @property
    def osds(self):
        """ Returns a list of CephOSD objects for all osds in the cluster. """
        if self._cluster_osds:
            return self._cluster_osds

        for osd in self.osd_dump.get('osds', {}):
            self._cluster_osds.append(CephOSD(osd['osd'], osd['uuid'],
                                              dump=osd))

        return self._cluster_osds

    @property
    def cluster_osds_without_v2_messenger_protocol(self):
        v1_osds = []
        for osd in self.osds:
            for key, val in osd.dump.items():
                if key.endswith('_addrs'):
                    vers = [info['type'] for info in val.get('addrvec', [])]
                    if 'v2' not in vers:
                        v1_osds.append(osd.id)

        return v1_osds

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

    @property
    def osd_release_names(self):
        """
        Same as versions property but with release names instead of versions.
        """
        return self.cluster.daemon_release_names('osd')

    @property
    def require_osd_release(self):
        return self.osd_dump.get('require_osd_release')

    @property
    def osd_daemon_release_names_match_required(self):
        """
        Does the cluster have require_osd_release set to a specific release
        name and if so, do all osds match that release name.
        """
        required_rname = self.require_osd_release
        if not required_rname:
            return True

        rnames = set(self.daemon_release_names('osd').keys())
        return len(rnames) == 1 and required_rname in rnames

    @property
    def laggy_pgs(self):
        if not self.pg_dump:
            return []

        laggy_pgs = []
        for pg in self.pg_dump['pg_map']['pg_stats']:
            for state in ['laggy', 'wait']:
                if state in pg['state']:
                    laggy_pgs.append(pg)
                    break

        return laggy_pgs

    def pool_id_to_name(self, id):
        if not self.osd_dump:
            return

        pools = self.osd_dump.get('pools', [])
        for pool in pools:
            if pool['pool'] == int(id):
                return pool['pool_name']

    @property
    def large_omap_pgs(self):
        if self._large_omap_pgs:
            return self._large_omap_pgs

        if not self.pg_dump:
            return self._large_omap_pgs

        for pg in self.pg_dump['pg_map']['pg_stats']:
            if pg['stat_sum']['num_large_omap_objects'] > 0:
                pg_id = pg['pgid']
                pg_pool_id = pg_id.partition('.')[0]
                self._large_omap_pgs[pg['pgid']] = {
                        'pool': self.pool_id_to_name(pg_pool_id),
                        'last_scrub_stamp': pg['last_scrub_stamp'],
                        'last_deep_scrub_stamp': pg['last_deep_scrub_stamp']
                        }

        return self._large_omap_pgs

    @property
    def large_omap_pgs_str(self):
        if not self.large_omap_pgs:
            return

        return ', '.join(self.large_omap_pgs.keys())

    @property
    def bluefs_oversized_metadata_osds(self):
        if self._bad_meta_osds:
            return self._bad_meta_osds

        if not self.osd_df_tree:
            return self._bad_meta_osds

        for device in self.osd_df_tree['nodes']:
            if device['id'] >= 0:
                meta_kb = device['kb_used_meta']
                # Usually the meta data is expected to be in 0-4G range
                # and we check if it's over 10G
                if meta_kb > self.OSD_META_LIMIT_KB:
                    self._bad_meta_osds.append(device['name'])

        return self._bad_meta_osds

    @staticmethod
    def version_as_a_tuple(ver):
        """
        Converts dotted version strings to a tuple so that they can be
        compared with standard operators.

        For example 1.2.3 becomes (1, 2, 3).
        """
        return tuple(map(int, (ver.split("."))))

    def ceph_daemon_versions_unique(self, exclude_daemons=None):
        """
        Returns dict of unique daemon versions from the Cluster. In an ideal
        world all versions would be the same but it is common for them to get
        out of sync as components are upgraded asynchronously.
        """
        versions = self.daemon_versions()
        if not versions:
            return {}

        unique_versions = {}
        for daemon_type in versions:
            # skip the catchall
            if daemon_type == 'overall':
                continue

            if exclude_daemons:
                if daemon_type in exclude_daemons:
                    continue

            unique_versions[daemon_type] = list(set(versions[daemon_type]))

        return unique_versions

    @property
    def ceph_versions_aligned(self):
        versions = self.ceph_daemon_versions_unique()
        if not versions:
            return True

        gloval_vers = set()
        for vers in versions.values():
            if len(vers) > 1:
                return False

            gloval_vers.add(vers[0])

        return len(gloval_vers) == 1

    @property
    def mon_versions_aligned_with_cluster(self):
        """
        While it is not critical to have minor version mismatches across
        daemons in the cluster, it is required for the Ceph mons to always
        be >= to the rest of the cluster. This returns True if the requirement
        is met otherwise False.
        """
        non_mon = self.ceph_daemon_versions_unique(exclude_daemons='mon')
        mon_versions = self.daemon_versions('mon')
        if not non_mon or not mon_versions:
            return True

        mon_top = sorted(mon_versions.keys(),
                         key=lambda v: self.version_as_a_tuple(v))[0]
        for vers in non_mon.values():
            cl_top = sorted(vers, key=lambda v: self.version_as_a_tuple(v))[0]
            if cl_top > mon_top:
                return False

        return True

    @property
    def osdmaps_count(self):
        report = self.cli.ceph_report_json_decoded()
        if not report:
            return 0

        try:
            return len(report['osdmap_manifest']['pinned_maps'])
        except (ValueError, KeyError):
            return 0

    @property
    def osds_pgs(self):
        if self._osds_pgs:
            return self._osds_pgs

        if not self.osd_df_tree:
            return self._osds_pgs

        for device in self.osd_df_tree['nodes']:
            if device['id'] >= 0:
                self._osds_pgs[device['name']] = device['pgs']

        return self._osds_pgs

    @property
    def osds_pgs_above_max(self):
        _osds_pgs = {}
        for osd, num_pgs in self.osds_pgs.items():
            if num_pgs > self.OSD_PG_MAX_LIMIT:
                _osds_pgs[osd] = num_pgs

        return utils.sorted_dict(_osds_pgs, key=lambda e: e[1], reverse=True)

    @property
    def osds_pgs_suboptimal(self):
        _osds_pgs = {}
        for osd, num_pgs in self.osds_pgs.items():
            # allow 30% margin from optimal OSD_PG_OPTIMAL_NUM_* values
            margin_high = self.OSD_PG_OPTIMAL_NUM_MAX * 1.3
            margin_low = self.OSD_PG_OPTIMAL_NUM_MIN * .7
            if margin_high < num_pgs or margin_low > num_pgs:
                _osds_pgs[osd] = num_pgs

        return utils.sorted_dict(_osds_pgs, key=lambda e: e[1], reverse=True)


class CephDaemonBase(object):

    def __init__(self, daemon_type):
        self.daemon_type = daemon_type
        self.cli = CLIHelper()
        self.date_in_secs = utils.get_date_secs()
        self._version_info = None
        self._etime = None
        self._rss = None
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


class CephMon(CephDaemonBase):

    def __init__(self, name):
        super().__init__('mon')
        self.name = name


class CephMDS(CephDaemonBase):

    def __init__(self):
        super().__init__('mds')


class CephRGW(CephDaemonBase):

    def __init__(self):
        super().__init__('radosgw')


class CephOSD(CephDaemonBase):

    def __init__(self, id, fsid=None, device=None, dump=None):
        super().__init__('osd')
        self.id = id
        self.fsid = fsid
        self.device = device
        self._devtype = None
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

    @property
    def devtype(self):
        if self._devtype:
            return self._devtype

        osd_tree = self.cli.ceph_osd_df_tree_json_decoded()
        if not osd_tree:
            return self._devtype

        for node in osd_tree.get('nodes'):
            if node.get('type') == 'osd' and node['id'] == self.id:
                self._devtype = node['device_class']

        return self._devtype


class CephChecksBase(StorageBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ceph_config = CephConfig()
        self.bcache = BcacheBase()
        self._local_osds = None
        self.apt_check = checks.APTPackageChecksBase(
                                                core_pkgs=CEPH_PKGS_CORE,
                                                other_pkgs=CEPH_PKGS_OTHER)
        self.cluster = CephCluster()
        self.cli = CLIHelper()
        # create file-based caches of useful commands so they can be searched.
        self.cli_cache = {'ceph_volume_lvm_list':
                          self.cli.ceph_volume_lvm_list()}
        for cmd, output in self.cli_cache.items():
            self.cli_cache[cmd] = utils.mktemp_dump('\n'.join(output))

    def __del__(self):
        """ Ensure temp files/dirs are deleted. """
        for tmpfile in self.cli_cache.values():
            if os.path.exists(tmpfile):
                os.unlink(tmpfile)

    @property
    def summary_subkey(self):
        return 'ceph'

    @property
    def plugin_runnable(self):
        if self.apt_check.core:
            return True

        return False

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
    def local_osds_use_bcache(self):
        for osd in self.local_osds:
            if self.bcache.is_bcache_device(osd.device):
                return True

        return False

    @property
    def local_osds(self):
        """
        Returns a list of CephOSD objects for osds found on the local host.
        """
        if self._local_osds:
            return self._local_osds

        self._local_osds = self._get_local_osds()
        return self._local_osds

    @property
    def local_osds_devtypes(self):
        return [osd.devtype for osd in self.local_osds]

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


class CephDaemonConfigShow(object):
    """
    This class is used to lookup config for a given OSD using Ceph admin
    admin socket. Config values are obtained by getting an attribute with
    the name of the config key.

    Config are accessed as attributes on the class object so that they may be
    accessed like properties rather than having to call a method.
    """

    def __init__(self, osd_id):
        self.cli = CLIHelper()
        self.config = {}
        cexpr = re.compile(r'\s*"(\S+)":\s+"(\S+)".*')
        for line in self.cli.ceph_daemon_config_show(osd_id=osd_id):
            ret = re.match(cexpr, line)
            if ret:
                self.config[ret.group(1)] = ret.group(2)

    def __getattr__(self, name):
        if name not in self.config:
            raise AttributeError(name)

        return self.config[name]


class CephDaemonConfigShowAllOSDs(object):
    """
    This class is used to lookup config for all OSDs. When a config value
    is requested, the value for that key is fetch from all OSDs and a
    list of unique values is returned. This can be used to determine whether
    all OSDs are using the same value.

    Config are accessed as attributes on the class object so that they may be
    accessed like properties rather than having to call a method.
    """

    def __init__(self):
        self.ceph_base = CephChecksBase()

    def __getattr__(self, name):
        vals = set()
        for osd in self.ceph_base.local_osds:
            config = CephDaemonConfigShow(osd_id=osd.id)
            if hasattr(config, name):
                vals.add(getattr(config, name))

        return list(vals)


class CephServiceChecksBase(CephChecksBase, checks.ServiceChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, service_exprs=CEPH_SERVICES_EXPRS, **kwargs)


class CephEventChecksBase(CephChecksBase, YEventCheckerBase):

    @property
    def summary(self):
        # mainline all results into summary root
        return self.run_checks()
