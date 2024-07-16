import re
from functools import cached_property

from hotsos.core.host_helpers import (
    CLIHelper,
    CLIHelperFile,
)
from hotsos.core.search import (
    FileSearcher,
    SequenceSearchDef,
    SearchDef
)
from hotsos.core.plugins.storage.ceph.daemon import (
    CephMon,
    CephOSD,
)
from hotsos.core.utils import sorted_dict

CEPH_POOL_TYPE = {1: 'replicated', 3: 'erasure-coded'}


class CephCrushMap():
    """
    Representation of a Ceph cluster CRUSH map.
    """
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
                unequal_buckets.append(f"tree '{buckets[tree]['name']}' at "
                                       f"the '{failure_domain}' level")

        return unequal_buckets

    @cached_property
    def crushmap_equal_buckets_pretty(self):
        unequal = self.crushmap_equal_buckets
        if unequal:
            return ", ".join(unequal)

        return None

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


class CephCluster():  # pylint: disable=too-many-public-methods
    """
    Provides an interface to a Ceph cluster.

    NOTE: we disable the too-many-public-methods pylint warning because by
          nature this is going to have a large number of public methods.
    """
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

        return None

    @cached_property
    def _mon_dump(self):
        return CLIHelper().ceph_mon_dump_json_decoded() or {}

    @cached_property
    def _osd_dump(self):
        return CLIHelper().ceph_osd_dump_json_decoded() or {}

    @cached_property
    def pg_dump(self):
        return CLIHelper().ceph_pg_dump_json_decoded() or {}

    @cached_property
    def _ceph_mgr_module_ls(self):
        return CLIHelper().ceph_mgr_module_ls() or {}

    @cached_property
    def mons(self):
        _mons = []
        for mon in self._mon_dump.get('mons', {}):
            _mons.append(CephMon(mon['name']))

        return _mons

    @cached_property
    def mgr_modules(self):
        """
        Returns a list of modules that are enabled. This includes both
        the 'always on' as well as modules enabled explicitly.
        """
        if not self._ceph_mgr_module_ls:
            return []

        _modules = []
        for category in ['always_on_modules', 'enabled_modules']:
            if self._ceph_mgr_module_ls[category]:
                _modules += self._ceph_mgr_module_ls[category]

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
        for osd in self._osd_dump.get('osds', {}):
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
            start = SearchDef(rf"^\s+\"({daemon_type})\":\s+{{")
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
        return self._osd_dump.get('require_osd_release')

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
        if not self._osd_dump:
            return None

        pools = self._osd_dump.get('pools', [])
        for pool in pools:
            if pool['pool'] == int(pool_id):
                return pool['pool_name']

        return None

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
            return None

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
                         key=self.version_as_a_tuple)[0]
        for vers in non_mon.values():
            cl_top = sorted(vers, key=self.version_as_a_tuple)[0]
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
