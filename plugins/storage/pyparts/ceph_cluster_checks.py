from core.issues import (
    issue_types,
    issue_utils,
)
from core.utils import sorted_dict
from core.plugins.storage import ceph
from core.plugins.storage.ceph import CephChecksBase

YAML_PRIORITY = 1
LP1936136_BCACHE_CACHE_LIMIT = 70
OSD_PG_MAX_LIMIT = 500
OSD_PG_OPTIMAL_NUM_MAX = 200
OSD_PG_OPTIMAL_NUM_MIN = 50
OSD_META_LIMIT_KB = (10 * 1024 * 1024)


class CephClusterChecks(CephChecksBase):

    def check_large_omap_objects(self):
        """
        Report PGs with large OMAP objects.

        """
        pg_dump = self.cli.ceph_pg_dump_json_decoded()
        if not pg_dump:
            return

        large_omap_pgs = {}
        for pg in pg_dump['pg_map']['pg_stats']:
            if pg['stat_sum']['num_large_omap_objects'] > 0:
                scrub = "last_scrub_at={}".format(pg['last_scrub_stamp'])
                deep_scrub = ("last_deep_scrub_at={}".
                              format(pg['last_scrub_stamp']))
                large_omap_pgs[pg['pgid']] = [scrub, deep_scrub]

        if large_omap_pgs:
            msg = ("Large omap objects found in the following PGs:{}. "
                   "This is usually resolved by deep-scrubbing the PGs. Check "
                   "'osd_deep_scrub_large_omap_object_key_threshold' and "
                   "'osd_deep_scrub_large_omap_object_value_sum_threshold' "
                   "to find whether the number of keys are high."
                   .format(large_omap_pgs))
            issue_utils.add_issue(issue_types.CephWarning(msg))

    def check_osd_msgr_protocol_versions(self):
        """Check if any OSDs are not using the messenger v2 protocol

        The msgr v2 is the second major revision of Ceph’s on-wire protocol
        and should be the default Nautilus onward.
        """
        if self.release_name <= 'mimic':
            """ v2 only available for >= Nautilus. """
            return

        osd_dump = self.cli.ceph_osd_dump_json_decoded()
        if not osd_dump:
            return

        v1_only_osds = 0
        for osd in osd_dump['osds']:
            for key, val in osd.items():
                if key.endswith('_addrs'):
                    vers = [info['type'] for info in val.get('addrvec', [])]
                    if 'v2' not in vers:
                        v1_only_osds += 1

        if v1_only_osds:
            msg = ("{} osd(s) do not bind to a v2 address".
                   format(v1_only_osds))
            issue_utils.add_issue(issue_types.CephOSDWarning(msg))

    def check_ceph_bluefs_size(self):
        """
        Check if the BlueFS metadata size is too large
        """
        ceph_osd_df_tree = self.cli.ceph_osd_df_tree_json_decoded()
        if not ceph_osd_df_tree:
            return

        bad_meta_osds = []
        for device in ceph_osd_df_tree['nodes']:
            if device['id'] >= 0:
                meta_kb = device['kb_used_meta']
                # Usually the meta data is expected to be in 0-4G range
                # and we check if it's over 10G
                if meta_kb > OSD_META_LIMIT_KB:
                    bad_meta_osds.append(device['name'])

        if bad_meta_osds:
            msg = ("Found {} osd(s) with metadata size larger than 10G. This "
                   "could be the result of a compaction failure/bug and this "
                   "host may be affected by "
                   "https://tracker.ceph.com/issues/45903. "
                   "A workaround (>= Nautilus) is to manually compact using "
                   "'ceph-bluestore-tool'"
                   .format(len(bad_meta_osds)))
            issue_utils.add_issue(issue_types.CephOSDWarning(msg))

    def get_ceph_pg_imbalance(self):
        """ Validate PG counts on OSDs

        Upstream recommends 50-200 OSDs ideally. Higher than 200 is also valid
        if the OSD disks are of different sizes but that tends to be the
        exception rather than the norm.

        We also check for OSDs with excessive numbers of PGs that can cause
        them to fail.
        """
        ceph_osd_df_tree = self.cli.ceph_osd_df_tree_json_decoded()
        if not ceph_osd_df_tree:
            return

        suboptimal_pgs = {}
        error_pgs = {}
        for device in ceph_osd_df_tree['nodes']:
            if device['id'] >= 0:
                osd_id = device['name']
                pgs = device['pgs']
                if pgs > OSD_PG_MAX_LIMIT:
                    error_pgs[osd_id] = pgs

                # allow 30% margin from optimal OSD_PG_OPTIMAL_NUM_* values
                margin_high = OSD_PG_OPTIMAL_NUM_MAX * 1.3
                margin_low = OSD_PG_OPTIMAL_NUM_MIN * .7
                if margin_high < pgs or margin_low > pgs:
                    suboptimal_pgs[osd_id] = pgs

        if error_pgs:
            info = sorted_dict(error_pgs, key=lambda e: e[1], reverse=True)
            self._output['osd-pgs-near-limit'] = info
            msg = ("Found {} osd(s) with > {} pgs - this is close to the hard "
                   "limit at which point they will stop creating pgs and fail "
                   "- please investigate".
                   format(len(error_pgs), OSD_PG_MAX_LIMIT))
            issue = issue_types.CephCrushError(msg)
            issue_utils.add_issue(issue)

        if suboptimal_pgs:
            info = sorted_dict(suboptimal_pgs, key=lambda e: e[1],
                               reverse=True)
            self._output['osd-pgs-suboptimal'] = info
            msg = ("Found {} osd(s) with > 30% margin from optimal {}-{} pgs."
                   .format(len(suboptimal_pgs), OSD_PG_OPTIMAL_NUM_MIN,
                           OSD_PG_OPTIMAL_NUM_MAX))
            issue = issue_types.CephCrushWarning(msg)
            issue_utils.add_issue(issue)

    @staticmethod
    def version_as_a_tuple(ver):
        """
        Return a version string as a tuple for easy comparison
        """
        return tuple(map(int, (ver.split("."))))

    def get_ceph_versions_mismatch(self):
        """
        Get versions of all Ceph daemons.
        """
        versions = ceph.CephCluster().daemon_versions()
        if not versions:
            return

        global_vers = set()
        daemon_version_info = {}

        # these store highest ver and daemon name with highest ver
        h_version = "0.0.0"
        h_daemon = ""

        for daemon_type in versions:
            # skip the catchall
            if daemon_type == 'overall':
                continue

            vers = []
            for version in versions[daemon_type]:
                vers.append(version)
                global_vers.add(version)
                # store the highest version any component has
                if self.version_as_a_tuple(version) > \
                        self.version_as_a_tuple(h_version):
                    h_version = version
                    h_daemon = daemon_type
            if vers:
                daemon_version_info[daemon_type] = vers

        if daemon_version_info:
            self._output['versions'] = daemon_version_info
            if len(global_vers) > 1:
                msg = ('ceph daemon versions not aligned possibly because '
                       'cluster upgrade is incomplete/incorrectly done. '
                       'All daemons, except the clients, should be on the '
                       'same version for ceph to function correctly.')
                issue = issue_types.CephDaemonWarning(msg)
                issue_utils.add_issue(issue)

            # check if mon is lower than highest version we stored earlier
            for version in versions.get('mon', []):
                if self.version_as_a_tuple(version) < \
                      self.version_as_a_tuple(h_version):
                    msg = ("mon version {} is lower than {} version {}"
                           .format(version, h_daemon, h_version))
                    issue = issue_types.CephDaemonVersionsError(msg)
                    issue_utils.add_issue(issue)

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

    def get_crushmap_mixed_buckets(self):
        """
        Report buckets that have mixed type of items,
        as they will cause crush map unable to compute
        the expected up set
        """
        osd_crush_dump = self.cli.ceph_osd_crush_dump_json_decoded()
        if not osd_crush_dump:
            return

        bad_buckets = []
        buckets = self._build_buckets_from_crushdump(osd_crush_dump)
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

        if bad_buckets:
            msg = ("mixed crush bucket types identified in buckets '{}'. "
                   "This can cause data distribution to become skewed - "
                   "please check crush map".format(bad_buckets))
            issue = issue_types.CephCrushWarning(msg)
            issue_utils.add_issue(issue)

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

    def check_crushmap_equal_buckets(self):
        """
        Report when buckets of the failure domain type in a
        CRUSH rule referenced tree are unbalanced.

        Uses the trees and failure domains referenced in the
        CRUSH rules, and checks that all buckets of the failure
        domain type in the referenced tree are equal.
        """
        osd_crush_dump = self.cli.ceph_osd_crush_dump_json_decoded()
        if not osd_crush_dump:
            return

        buckets = {b['id']: b for b in osd_crush_dump["buckets"]}

        to_check = []

        for rule in osd_crush_dump['rules']:
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

        for ruleid, tree, failure_domain in to_check:
            unbalanced = \
                self._is_bucket_imbalanced(buckets, tree, failure_domain)
            if unbalanced:
                msg = ("unbalanced crush buckets identified in CRUSH "
                       "root '{}' using failure domain '{}'. "
                       "Affected CRUSH rule id is '{}'. "
                       "This can cause data distribution to become skewed - "
                       "please check crush map".format(buckets[tree]["name"],
                                                       failure_domain,
                                                       ruleid))
                issue = issue_types.CephCrushWarning(msg)
                issue_utils.add_issue(issue)

    def __call__(self):
        if self.local_osds:
            osds = {}
            for osd in self.local_osds:
                osds.update(osd.to_dict())

            self._output["local-osds"] = sorted_dict(osds)

        self.check_osd_msgr_protocol_versions()
        self.check_ceph_bluefs_size()
        self.get_ceph_pg_imbalance()
        self.get_ceph_versions_mismatch()
        self.get_crushmap_mixed_buckets()
        self.check_large_omap_objects()
        self.check_crushmap_equal_buckets()


class CephCrushChecks(CephChecksBase):
    def get_crush_summary(self):
        """
        Get crush rules summary and the pools using those rules map.
        """

        if self.crush_rules:
            self._output['crush_rules'] = self.crush_rules

    def __call__(self):
        self.get_crush_summary()
