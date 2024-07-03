import abc
import os
import re
import subprocess
import sys
from datetime import datetime
from functools import cached_property

from hotsos.core.config import HotSOSConfig
from hotsos.core.factory import FactoryBase
from hotsos.core.host_helpers.cli import get_ps_axo_flags_available
from hotsos.core.host_helpers import (
    APTPackageHelper,
    CLIHelper,
    CLIHelperFile,
    DPKGVersion,
    HostNetworkingHelper,
    PebbleHelper,
    SnapPackageHelper,
    SystemdHelper,
    IniConfigBase,
)
from hotsos.core.log import log
from hotsos.core.plugins.kernel.net import Lsof
from hotsos.core.plugins.storage import StorageBase
from hotsos.core.plugins.storage.bcache import BcacheBase
from hotsos.core.search import (
    FileSearcher,
    SequenceSearchDef,
    SearchDef
)
from hotsos.core.utils import (
    sorted_dict,
    seconds_to_date,
)
from hotsos.core.ycheck.events import EventCallbackBase

CEPH_SERVICES_EXPRS = [r"ceph-[a-z0-9-]+",
                       r"rados[a-z0-9-:]+",
                       r"microceph.(mon|mgr|mds|osd|rgw)"]
CEPH_PKGS_CORE = [r"ceph",
                  r"rados",
                  r"rbd",
                  ]
CEPH_PKGS_OTHER = []
# Add in clients/deps
for ceph_pkg in CEPH_PKGS_CORE:
    CEPH_PKGS_OTHER.append(r"python3?-{}\S*".format(ceph_pkg))

CEPH_SNAPS_CORE = [r'microceph']

# NOTE(tpsilva): when updating this list, refer to the supported Ceph
# versions for Ubuntu page:
# https://ubuntu.com/ceph/docs/supported-ceph-versions
CEPH_EOL_INFO = {
    'reef': datetime(2034, 4, 30),
    'quincy': datetime(2032, 4, 30),
    'pacific': datetime(2024, 4, 30),
    'octopus': datetime(2030, 4, 30),
    'nautilus': datetime(2021, 2, 28),
    'mimic': datetime(2022, 4, 30),
    'luminous': datetime(2028, 4, 30),
    'jewel': datetime(2024, 4, 30)
}

CEPH_REL_INFO = {
    'ceph-common': {
        'reef': '18.0',
        'quincy': '17.0',
        'pacific': '16.0',
        'octopus': '15.0',
        'nautilus': '14.0',
        'mimic': '13.0',
        'luminous': '12.0',
        'kraken': '11.0',
        'jewel': '10.0'},
}

CEPH_POOL_TYPE = {1: 'replicated', 3: 'erasure-coded'}


def csv_to_set(f):
    """
    Decorator used to convert a csv string to a set().
    """
    def csv_to_set_inner(*args, **kwargs):
        val = f(*args, **kwargs)
        if val is not None:
            return set(v.strip(',') for v in val.split())

        return set([])

    return csv_to_set_inner


class CephConfig(IniConfigBase):
    def __init__(self, *args, **kwargs):
        path = os.path.join(HotSOSConfig.data_root, 'etc/ceph/ceph.conf')
        super().__init__(*args, path=path, **kwargs)

    def get(self, key, *args, **kwargs):
        """
        First to get value for key and if not found, try alternative key format
        i.e. ceph config like 'ceph osd debug' and 'ceph_osd_debug' are both
        valid and equivalent so we try both by converting the key name. If that
        still does not match we look for key in this object instance since it
        may have been provided as a property.
        """
        val = super().get(key, *args, **kwargs)
        if val is not None:
            return val

        orig_key = key
        if ' ' in key:
            key = key.replace(' ', '_')
        else:
            key = key.replace('_', ' ')

        val = super().get(key, *args, **kwargs)
        if val is not None:
            return val

        if hasattr(self, orig_key):
            return getattr(self, orig_key)

    @property
    @csv_to_set
    def cluster_network_set(self):
        return self.get('cluster network')

    @property
    @csv_to_set
    def public_network_set(self):
        return self.get('public network')


class CephCrushMap():

    @staticmethod
    def _filter_pools_by_rule(pools, crush_rule):
        res_pool = []
        for pool in pools:
            if pool['crush_rule'] == crush_rule:
                pool_str = pool['pool_name'] + ' (' + str(pool['pool']) + ')'
                res_pool.append(pool_str)

        return res_pool

    @cached_property
    def osd_crush_dump(self):
        return CLIHelper().ceph_osd_crush_dump_json_decoded() or {}

    @cached_property
    def ceph_report(self):
        return CLIHelper().ceph_report_json_decoded() or {}

    @cached_property
    def rules(self):
        """
        Returns a list of crush rules, mapped to the respective pools.
        """
        if not self.ceph_report:
            return {}

        rule_to_pool = {}
        for rule in self.ceph_report['crushmap']['rules']:
            rule_id = rule['rule_id']
            rtype = rule['type']
            pools = self.ceph_report['osdmap']['pools']
            pools = self._filter_pools_by_rule(pools, rule_id)
            rule_to_pool[rule['rule_name']] = {'id': rule_id,
                                               'type': CEPH_POOL_TYPE[rtype],
                                               'pools': pools}

        return rule_to_pool

    @staticmethod
    def _build_buckets_from_crushdump(crushdump):
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

    def _rule_used_by_any_pool(self, rule_id):
        for pool_dict in self.rules.values():
            if (pool_dict['id'] == rule_id) and pool_dict['pools']:
                return True
        return False

    @cached_property
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
        # check all buckets
        for bdict in buckets.values():
            items = bdict["items"]
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
                bad_buckets.append(bdict["name"])

        return bad_buckets

    @cached_property
    def crushmap_mixed_buckets_str(self):
        return ','.join(self.crushmap_mixed_buckets)

    def _is_bucket_imbalanced(self, buckets, start_bucket_id, failure_domain,
                              weight=-1):
        """Return whether a tree is unbalanced

        Recursively determine if a given tree (start_bucket_id) is
        balanced at the given failure domain (failure_domain) in the
        CRUSH tree(s) provided by the buckets parameter.
        """

        for item in buckets[start_bucket_id]["items"]:
            if buckets[item["id"]]["type_name"] != failure_domain:
                if self._is_bucket_imbalanced(buckets, item["id"],
                                              failure_domain, weight):
                    return True
            # Handle items/buckets with 0 weight correctly, by
            # ignoring them.
            # These are excluded from placement consideration,
            # and therefore do not unbalance a tree.
            elif item["weight"] > 0:
                if weight == -1:
                    weight = item["weight"]
                else:
                    if weight != item["weight"]:
                        return True

        return False

    @cached_property
    def crushmap_equal_buckets(self):
        """
        Report when in-use failure domain buckets are unbalanced.

        Uses the trees and failure domains referenced in the
        CRUSH rules, and checks that all buckets of the failure
        domain type in the referenced tree are equal or of zero size.
        """
        if not self.osd_crush_dump:
            return []

        buckets = {b['id']: b for b in self.osd_crush_dump["buckets"]}

        to_check = []
        for rule in self.osd_crush_dump.get('rules', []):
            taken = 0
            fdomain = 0
            rid = rule["rule_id"]
            for i in rule['steps']:
                if i["op"] == "take":
                    taken = i["item"]
                if "type" in i and taken != 0:
                    fdomain = i["type"]
                if taken != 0 and fdomain != 0 and \
                        self._rule_used_by_any_pool(rid):
                    to_check.append((rid, taken, fdomain))
                    taken = fdomain = 0

        unequal_buckets = []
        for _, tree, failure_domain in to_check:
            if self._is_bucket_imbalanced(buckets, tree, failure_domain):
                unequal_buckets.append(
                    "tree '{}' at the '{}' level"
                    .format(buckets[tree]["name"], failure_domain))

        return unequal_buckets

    @cached_property
    def crushmap_equal_buckets_pretty(self):
        unequal = self.crushmap_equal_buckets
        if unequal:
            return ", ".join(unequal)

    @cached_property
    def autoscaler_enabled_pools(self):
        if not self.ceph_report:
            return []

        pools = self.ceph_report['osdmap']['pools']
        return [p for p in pools if p.get('pg_autoscale_mode') == 'on']

    @cached_property
    def autoscaler_disabled_pools(self):
        if not self.ceph_report:
            return []

        pools = self.ceph_report['osdmap']['pools']
        return [p for p in pools if p.get('pg_autoscale_mode') != 'on']

    @cached_property
    def is_rgw_using_civetweb(self):
        if not self.ceph_report:
            return []

        try:
            rgws = self.ceph_report['servicemap']['services']['rgw']['daemons']
            for _, outer_d in rgws.items():
                if isinstance(outer_d, dict):
                    if outer_d['metadata']['frontend_type#0'] == 'civetweb':
                        return True
        except (ValueError, KeyError):
            pass
        return False


class CephCluster():
    OSD_META_LIMIT_PERCENT = 5
    OSD_PG_MAX_LIMIT = 500
    OSD_PG_OPTIMAL_NUM_MAX = 200
    OSD_PG_OPTIMAL_NUM_MIN = 50
    OSD_DISCREPANCY_ALLOWED = 5
    # If a pool's utilisation is below this value, we consider is "empty"
    POOL_EMPTY_THRESHOLD = 2

    def __init__(self):
        self.crush_map = CephCrushMap()

    @cached_property
    def health_status(self):
        status = CLIHelper().ceph_status_json_decoded()
        if status:
            return status['health']['status']

    @cached_property
    def mon_dump(self):
        return CLIHelper().ceph_mon_dump_json_decoded() or {}

    @cached_property
    def osd_dump(self):
        return CLIHelper().ceph_osd_dump_json_decoded() or {}

    @cached_property
    def pg_dump(self):
        return CLIHelper().ceph_pg_dump_json_decoded() or {}

    @cached_property
    def ceph_mgr_module_ls(self):
        return CLIHelper().ceph_mgr_module_ls() or {}

    @cached_property
    def mons(self):
        _mons = []
        for mon in self.mon_dump.get('mons', {}):
            _mons.append(CephMon(mon['name']))

        return _mons

    @cached_property
    def mgr_modules(self):
        """
        Returns a list of modules that are enabled. This includes both
        the 'always on' as well as modules enabled explicitly.
        """
        if not self.ceph_mgr_module_ls:
            return []

        _modules = []
        for category in ['always_on_modules', 'enabled_modules']:
            if self.ceph_mgr_module_ls[category]:
                _modules += self.ceph_mgr_module_ls[category]

        return _modules

    @cached_property
    def osd_df_tree(self):
        return CLIHelper().ceph_osd_df_tree_json_decoded() or {}

    @cached_property
    def ceph_df(self):
        return CLIHelper().ceph_df_json_decoded() or {}

    @cached_property
    def osds(self):
        """ Returns a list of CephOSD objects for all osds in the cluster. """
        _osds = []
        for osd in self.osd_dump.get('osds', {}):
            _osds.append(CephOSD(osd['osd'], osd['uuid'], dump=osd))

        return _osds

    @cached_property
    def cluster_osds_without_v2_messenger_protocol(self):
        v1_osds = []
        for osd in self.osds:
            for key, val in osd.dump.items():
                if key.endswith('_addrs'):
                    vers = [info['type'] for info in val.get('addrvec', [])]
                    if 'v2' not in vers:
                        v1_osds.append(osd.id)

        return v1_osds

    @staticmethod
    def _get_version_info(daemon_type=None):
        """
        Returns a dict of ceph versions info for the provided daemon type. If
        no daemon type provided, version info is collected for all types and
        the resulting dict is keyed by daemon type otherwise it is keyed by
        version (and only versions for that daemon type.)
        """
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

        with CLIHelperFile() as cli:
            s.add(sd, path=cli.ceph_versions())
            for section in s.run().find_sequence_sections(sd).values():
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

    @cached_property
    def osd_release_names(self):
        """
        Same as versions property but with release names instead of versions.
        """
        return self.daemon_release_names('osd')

    @cached_property
    def require_osd_release(self):
        return self.osd_dump.get('require_osd_release')

    @cached_property
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

    @cached_property
    def laggy_pgs(self):
        if not self.pg_dump:
            return []

        laggy_pgs = []
        # The states we consider problematic for network related issues
        laggy_like_states = ['laggy', 'wait']
        for pg in self.pg_dump['pg_map']['pg_stats']:
            if any(x in pg['state'].split('+') for x in laggy_like_states):
                laggy_pgs.append(pg)

        return laggy_pgs

    def pool_id_to_name(self, pool_id):
        if not self.osd_dump:
            return

        pools = self.osd_dump.get('pools', [])
        for pool in pools:
            if pool['pool'] == int(pool_id):
                return pool['pool_name']

    @cached_property
    def large_omap_pgs(self):
        _large_omap_pgs = {}
        if not self.pg_dump:
            return _large_omap_pgs

        for pg in self.pg_dump['pg_map']['pg_stats']:
            if pg['stat_sum']['num_large_omap_objects'] > 0:
                pg_id = pg['pgid']
                pg_pool_id = pg_id.partition('.')[0]
                _large_omap_pgs[pg['pgid']] = {
                    'pool': self.pool_id_to_name(pg_pool_id),
                    'last_scrub_stamp': pg['last_scrub_stamp'],
                    'last_deep_scrub_stamp': pg['last_deep_scrub_stamp']
                }

        return _large_omap_pgs

    @cached_property
    def large_omap_pgs_str(self):
        if not self.large_omap_pgs:
            return

        return ', '.join(self.large_omap_pgs.keys())

    @cached_property
    def bluefs_oversized_metadata_osds(self):
        _bad_meta_osds = []
        if not self.osd_df_tree:
            return _bad_meta_osds

        for device in self.osd_df_tree['nodes']:
            if device['id'] >= 0:
                meta_kb = device['kb_used_meta']
                # Util under under 2G are ignored (treated as non-issue).
                # See #434 for relevant info.
                if meta_kb < (2 * 1024 * 1024):
                    continue
                total_kb = device['kb_used']
                if meta_kb > (self.OSD_META_LIMIT_PERCENT / 100.0 * total_kb):
                    _bad_meta_osds.append(device['name'])

        return sorted(_bad_meta_osds)

    @cached_property
    def cluster_has_non_empty_pools(self):
        """
        Although we say "non-empty", we don't actually expect pools to have
        0% utilisation in practice because:
          - there may test pools after a fresh deployment done by FE/users
          - device_health_metrics pool created automatically
        So we consider that pools empty if the usage is below a threshold.
        """
        if not self.ceph_df:
            return False

        for pool in self.ceph_df['pools']:
            if pool['stats']['percent_used'] > \
                    self.POOL_EMPTY_THRESHOLD / 100.0:
                return True
        return False

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
        for daemon_type, count in versions.items():
            # skip the catchall
            if daemon_type == 'overall':
                continue

            if exclude_daemons:
                if daemon_type in exclude_daemons:
                    continue

            unique_versions[daemon_type] = sorted(
                list(set(count)))

        return unique_versions

    @cached_property
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

    @cached_property
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

    @cached_property
    def osdmaps_count(self):
        report = CLIHelper().ceph_report_json_decoded()
        if not report:
            return 0

        try:
            return len(report['osdmap_manifest']['pinned_maps'])
        except (ValueError, KeyError):
            return 0

    @cached_property
    def osds_pgs(self):
        _osds_pgs = {}
        if not self.osd_df_tree:
            return _osds_pgs

        for device in self.osd_df_tree['nodes']:
            if device['id'] >= 0:
                _osds_pgs[device['name']] = device['pgs']

        return _osds_pgs

    @cached_property
    def osds_pgs_above_max(self):
        _osds_pgs = {}
        for osd, num_pgs in self.osds_pgs.items():
            if num_pgs > self.OSD_PG_MAX_LIMIT:
                _osds_pgs[osd] = num_pgs

        return sorted_dict(_osds_pgs, key=lambda e: e[1], reverse=True)

    @cached_property
    def osds_pgs_suboptimal(self):
        _osds_pgs = {}
        for osd, num_pgs in self.osds_pgs.items():
            # allow 30% margin from optimal OSD_PG_OPTIMAL_NUM_* values
            margin_high = self.OSD_PG_OPTIMAL_NUM_MAX * 1.3
            margin_low = self.OSD_PG_OPTIMAL_NUM_MIN * .7
            if margin_high < num_pgs or margin_low > num_pgs:
                _osds_pgs[osd] = num_pgs

        return sorted_dict(_osds_pgs, key=lambda e: e[1], reverse=True)

    @cached_property
    def ssds_using_bcache(self):
        report = CLIHelper().ceph_report_json_decoded()
        if not report:
            return []

        ssd_osds_using_bcache = []
        for osd in report['osd_metadata']:
            if osd['bluestore_bdev_type'] == 'ssd' and \
                    osd['bluestore_bdev_rotational'] == '0' and \
                    re.search("bcache", osd['bluestore_bdev_devices']):
                ssd_osds_using_bcache.append(osd['id'])

        return sorted(ssd_osds_using_bcache)

    @cached_property
    def osd_raw_usage_higher_than_data(self):
        _bad_osds = []

        if not self.osd_df_tree:
            return _bad_osds

        for osd in self.osd_df_tree['nodes']:
            if osd['id'] >= 0:
                raw_usage = osd['kb_used']
                total_usage = osd['kb_used_data'] + osd['kb_used_omap'] + \
                    osd['kb_used_meta']
                # There's always some additional space used by OSDs that's not
                # by data/omap/meta for journaling, internal structures, etc.
                # Thus we allow 5% discrepancy.
                allowance = total_usage * self.OSD_DISCREPANCY_ALLOWED / 100.0
                if raw_usage > (total_usage + allowance):
                    _bad_osds.append(osd['name'])

        return sorted(_bad_osds)


class CephDaemonBase():

    def __init__(self, daemon_type):
        self.daemon_type = daemon_type
        self.id = None
        self.date_in_secs = self.get_date_secs()

    @classmethod
    def get_date_secs(cls, datestring=None):
        if datestring:
            cmd = ["date", "--utc", "--date={}".format(datestring), "+%s"]
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
            ceph_id = r"--id\s+{}".format(self.id)
        else:
            ceph_id = ''

        expr = (r"\S+\s+\d+\s+\S+\s+\S+\s+\d+\s+(\d+)\s+.+/ceph-{}\s+.+{}\s+.+"
                r".+".format(self.daemon_type, ceph_id))
        sd = SearchDef(expr)
        with CLIHelperFile() as cli:
            ps_out = cli.ps()
            s.add(sd, path=ps_out)
            rss = 0
            # we only expect one result
            for result in s.run().find_by_path(ps_out):
                rss = int(int(result.get(1)) / 1024)
                break

        return "{}M".format(rss)

    @cached_property
    def etime(self):
        """Return process etime for a given daemon.

        To get etime we have to use ps_axo_flags rather than the default
        ps_auxww.
        """
        if not get_ps_axo_flags_available():
            return

        if self.id is None:
            return

        ps_info = []
        daemon = "ceph-{}".format(self.daemon_type)
        for line in CLIHelper().ps_axo_flags():
            ret = re.compile(daemon).search(line)
            if not ret:
                continue

            expt_tmplt = SystemdHelper.PS_CMD_EXPR_TEMPLATES['absolute']
            ret = re.compile(expt_tmplt.format(daemon)).search(line)
            if ret:
                ps_info.append(ret.group(0))

        if not ps_info:
            return

        _etime = None
        for cmd in ps_info:
            ret = re.compile(r".+\s+.+--id {}\s+.+".format(self.id)).match(cmd)
            if ret:
                osd_start = ' '.join(cmd.split()[13:17])
                if self.date_in_secs and osd_start:
                    osd_start_secs = self.get_date_secs(datestring=osd_start)
                    osd_uptime_secs = self.date_in_secs - osd_start_secs
                    osd_uptime_str = seconds_to_date(osd_uptime_secs)
                    _etime = osd_uptime_str

        return _etime


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
            return

        _devtype = None
        for node in osd_tree.get('nodes'):
            if node.get('type') == 'osd' and node['id'] == self.id:
                _devtype = node['device_class']

        return _devtype


class CephChecksBase(StorageBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ceph_config = CephConfig()
        self.bcache = BcacheBase()
        self.apt = APTPackageHelper(core_pkgs=CEPH_PKGS_CORE,
                                    other_pkgs=CEPH_PKGS_OTHER)
        self.snaps = SnapPackageHelper(core_snaps=CEPH_SNAPS_CORE)
        self.pebble = PebbleHelper(service_exprs=CEPH_SERVICES_EXPRS)
        self.systemd = SystemdHelper(service_exprs=CEPH_SERVICES_EXPRS)
        self.cluster = CephCluster()

    @property
    def summary_subkey(self):
        return 'ceph'

    @property
    def plugin_runnable(self):
        if self.apt.core or self.snaps.core:
            return True

        return False

    @cached_property
    def release_name(self):
        relname = 'unknown'

        pkg = 'ceph-common'
        pkg_version = None
        if self.apt.core and pkg in self.apt.core:
            pkg_version = self.apt.core[pkg]
        elif self.snaps.core and 'microceph' in self.snaps.core:
            pkg_version = self.snaps.core['microceph']['version']
            pkg_version = pkg_version.partition("+snap")[0]

        if pkg_version is not None:
            for rel, ver in sorted(CEPH_REL_INFO[pkg].items(),
                                   key=lambda i: i[1], reverse=True):
                if pkg_version > DPKGVersion(ver):
                    relname = rel
                    break

        return relname

    @cached_property
    def days_to_eol(self):
        if self.release_name != 'unknown':
            eol = CEPH_EOL_INFO[self.release_name]
            today = datetime.utcfromtimestamp(int(CLIHelper().date()))
            delta = (eol - today).days
            return delta

    def _get_bind_interfaces(self, iface_type):
        """
        For the given config network type determine what interface ceph is
        binding to.

        @param iface_type: cluster or public
        """
        net = self.ceph_config.get('{} network'.format(iface_type))
        addr = self.ceph_config.get('{} addr'.format(iface_type))
        if not any([net, addr]):
            return {}

        nethelp = HostNetworkingHelper()
        port = None
        if net:
            port = nethelp.get_interface_with_addr(net)
        elif addr:
            port = nethelp.get_interface_with_addr(addr)

        if port:
            return {iface_type: port}

    @cached_property
    def _ceph_bind_interfaces(self):
        """
        Returns a dict of network interfaces used by Ceph daemons on this host.
        The dict has the form {<type>: [<port>, ...]}
        """
        interfaces = {}
        for iface_type in ['cluster', 'public']:
            ret = self._get_bind_interfaces(iface_type)
            if ret:
                interfaces.update(ret)

        return interfaces

    @property
    def bind_interfaces(self):
        return self._ceph_bind_interfaces

    @cached_property
    def bind_interface_names(self):
        """
        Returns a list of names for network interfaces used by Ceph daemons on
        this host.
        """
        names = [iface.name for iface in self.bind_interfaces.values()]
        return ', '.join(list(set(names)))

    @cached_property
    def local_osds(self):
        """
        Returns a list of CephOSD objects for osds found on the local host.
        """
        osds = []

        s = FileSearcher()
        sd = SequenceSearchDef(start=SearchDef(r"^=+\s+osd\.(\d+)\s+=+.*"),
                               body=SearchDef([r"\s+osd\s+(fsid)\s+(\S+)\s*",
                                               r"\s+(devices)\s+([\S]+)\s*"]),
                               tag="ceph-lvm")
        with CLIHelperFile() as cli:
            fout = cli.ceph_volume_lvm_list()
            s.add(sd, path=fout)
            for results in s.run().find_sequence_sections(sd).values():
                osdid = None
                fsid = None
                dev = None
                for result in results:
                    if result.tag == sd.start_tag:
                        osdid = int(result.get(1))
                    elif result.tag == sd.body_tag:
                        if result.get(1) == "fsid":
                            fsid = result.get(2)
                        elif result.get(1) == "devices":
                            dev = result.get(2)

                osds.append(CephOSD(osdid, fsid, dev))

        return osds

    @cached_property
    def local_osds_use_bcache(self):
        """
        Returns True if any local osds are using bcache devices.
        """
        for osd in self.local_osds:
            if self.bcache.is_bcache_device(osd.device):
                return True

        return False

    @cached_property
    def local_osds_devtypes(self):
        return [osd.devtype for osd in self.local_osds]

    @cached_property
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

        for keys in self.ceph_config.all_keys:
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

    @cached_property
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

    @cached_property
    def linked_with_tcmalloc(self):
        """
        Checks that each ceph-osd process has libtcmalloc linked.

        Returns True if every OSD has it linked, otherwise False.
        """
        osds = {}
        tcmalloc_osds = 0
        for row in Lsof():
            if row.COMMAND == 'ceph-osd':
                osds[row.PID] = 1
                if re.search("libtcmalloc", row.NAME):
                    tcmalloc_osds += 1

        return len(osds) == tcmalloc_osds


class CephDaemonCommand():
    """
    This class is used to run a ceph daemon command that must be supported by
    CLIHelper. Attributes of the output can then be retrieved by calling them
    on the returned object.
    """

    def __init__(self, command, *args, **kwargs):
        self.command = command
        self.output = getattr(CLIHelper(), command)(*args, **kwargs)

    def __getattr__(self, name):
        if name in self.output:
            return self.output[name]

        raise AttributeError("{} not found in output of {}".
                             format(name, self.command))


class CephDaemonConfigShow():

    def __init__(self, osd_id):
        self.cmd = CephDaemonCommand('ceph_daemon_osd_config_show',
                                     osd_id=osd_id)

    def __getattr__(self, name):
        return getattr(self.cmd, name)


class CephDaemonDumpMemPools():

    def __init__(self, osd_id):
        self.cmd = CephDaemonCommand('ceph_daemon_osd_dump_mempools',
                                     osd_id=osd_id)

    def __getattr__(self, name):
        val = getattr(self.cmd, 'mempool')
        if val:
            return val.get('by_pool', {}).get(name, {}).get('items')


class CephDaemonAllOSDsCommand():
    """
    This class is used to CephDaemonCommand for all local OSDs.
    """

    def __init__(self, command):
        self.checks_base = CephChecksBase()
        self.command = command

    def __getattr__(self, name=None):
        """
        First instantiates the requested ceph daemon command handler then
        retrieves the requested attribute/operand and returns as a list of
        unique values.
        """
        vals = set()
        for osd in self.checks_base.local_osds:
            try:
                config = getattr(sys.modules[__name__],
                                 self.command)(osd_id=osd.id)
            except ImportError:
                log.warning("no ceph daemon command handler found for '%s'")
                break

            if hasattr(config, name):
                vals.add(getattr(config, name))

        return list(vals)


class CephDaemonAllOSDsFactory(FactoryBase):
    """
    A factory interface to allow dynamic access to ceph daemon commands and
    attributes of the output.
    """

    def __getattr__(self, command):
        return CephDaemonAllOSDsCommand(command)


class CephEventCallbackBase(EventCallbackBase):

    @abc.abstractmethod
    def __call__(self):
        """ Callback method. """
