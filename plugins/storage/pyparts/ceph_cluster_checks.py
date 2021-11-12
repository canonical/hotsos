from core.checks import DPKGVersionCompare
from core.issues import (
    issue_types,
    issue_utils,
)
from core.utils import sorted_dict
from core.plugins.storage import (
    bcache,
    ceph,
)
from core.plugins.storage.ceph import CephChecksBase
from core.plugins.kernel import KernelChecksBase

YAML_PRIORITY = 1
LP1936136_BCACHE_CACHE_LIMIT = 70
OSD_PG_MAX_LIMIT = 500
OSD_PG_OPTIMAL_NUM = 200
OSD_META_LIMIT_KB = (10 * 1024 * 1024)
OSD_MAPS_LIMIT = 500  # mon_min_osdmap_epochs default


class CephClusterChecks(CephChecksBase):

    def check_health_status(self):
        if not self.health_status:
            # only available from a ceph-mon
            return

        if self.health_status != 'HEALTH_OK':
            msg = ("Ceph cluster is in '{}' state. Please check 'ceph status' "
                   "for details".format(self.health_status))
            issue_utils.add_issue(issue_types.CephHealthWarning(msg))

    def check_laggy_pgs(self):
        pg_dump = self.cli.ceph_pg_dump_json_decoded()
        if not pg_dump:
            return

        laggy_pgs = []
        for pg in pg_dump['pg_map']['pg_stats']:
            for state in ['laggy', 'wait']:
                if state in pg['state']:
                    laggy_pgs.append(pg)
                    break

        if laggy_pgs:
            msg = ("Ceph cluster is reporting {} laggy/wait PGs. This "
                   "suggests a potential network or storage issue - please "
                   "check".format(len(laggy_pgs)))
            issue_utils.add_issue(issue_types.CephWarning(msg))

    def check_osdmaps_size(self):
        """
        Check if there are too many osdmaps

        By default mon_min_osdmaps_epochs (=500) osdmaps are stored by the
        monitors. However, if the cluster isn't healthy for a long time,
        the number of osdmaps stored will keep increasing which can result
        in more disk utilization, possibly slower mons, etc.

        Doc: https://docs.ceph.com/en/latest/dev/mon-osdmap-prune/
        """

        report = self.cli.ceph_report_json_decoded()
        if not report:
            return

        try:
            osdmaps_count = len(report['osdmap_manifest']['pinned_maps'])
            # mon_min_osdmap_epochs (= 500) maps are held by default. Anything
            # over the limit, we need to look at and decide whether this could
            # be temporary or needs further investigation.
            if osdmaps_count > OSD_MAPS_LIMIT:
                msg = ("Found {} pinned osdmaps. This can affect mon's "
                       "performance and also indicate bugs such as "
                       "https://tracker.ceph.com/issues/44184 and "
                       "https://tracker.ceph.com/issues/47290"
                       .format(osdmaps_count))
                issue_utils.add_issue(issue_types.CephMapsWarning(msg))
        except (ValueError, KeyError):
            return

    def check_require_osd_release(self):
        cluster = ceph.CephCluster()
        expected_rname = cluster.daemon_dump('osd').get('require_osd_release')
        if not expected_rname:
            return

        for rname in cluster.daemon_release_names('osd'):
            if expected_rname != rname:
                msg = ("require_osd_release is {} but one or more osds is on "
                       "release {} - needs fixing".format(expected_rname,
                                                          rname))
                issue_utils.add_issue(issue_types.CephOSDError(msg))

    def check_osd_msgr_protocol_versions(self):
        """Check if any OSDs are not using the messenger v2 protocol

        The msgr v2 is the second major revision of Ceph’s on-wire protocol
        and should be the default Nautilus onward.
        """
        if self.release_name <= 'mimic':
            """ v2 only available for >= Nautilus. """
            return

        v1_osds = []
        cluster = ceph.CephCluster()
        osd_dump = cluster.daemon_dump('osd')
        if not osd_dump:
            return

        osd_count = int(cluster.daemon_dump('osd').get('max_osd', 0))
        if osd_count < 1:
            return

        counter = 0
        while counter < osd_count:
            key = "osd.{}".format(counter)
            version_info = cluster.daemon_dump('osd').get(key)
            if version_info and version_info.find("v2:") == -1:
                v1_osds.append(counter+1)

            counter = counter + 1

        if v1_osds:
            msg = ("{} osd(s) do not bind to a v2 address".
                   format(len(v1_osds)))
            issue_utils.add_issue(issue_types.CephOSDWarning(msg))

    def check_ceph_bluefs_size(self):
        """
        Check if the BlueFS metadata size is too large
        """
        bad_meta_osds = []
        ceph_osd_df_tree = self.cli.ceph_osd_df_tree_json_decoded()
        if not ceph_osd_df_tree:
            return

        for device in ceph_osd_df_tree['nodes']:
            if device['id'] >= 0:
                meta_kb = device['kb_used_meta']
                # Usually the meta data is expected to be in 0-4G range
                # and we check if it's over 10G
                if meta_kb > OSD_META_LIMIT_KB:
                    bad_meta_osds.append(device['name'])

        if bad_meta_osds:
            msg = ("{} osd(s) have metadata size larger than 10G. This "
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
        suboptimal_pgs = {}
        error_pgs = {}
        ceph_osd_df_tree = self.cli.ceph_osd_df_tree_json_decoded()
        if not ceph_osd_df_tree:
            return

        for device in ceph_osd_df_tree['nodes']:
            if device['id'] >= 0:
                osd_id = device['name']
                pgs = device['pgs']
                if pgs > OSD_PG_MAX_LIMIT:
                    error_pgs[osd_id] = pgs

                margin = abs(100 - (100.0 / OSD_PG_OPTIMAL_NUM * pgs))
                # allow 30% margin from optimal OSD_PG_OPTIMAL_NUM value
                if margin > 30:
                    suboptimal_pgs[osd_id] = pgs

        if error_pgs:
            info = sorted_dict(error_pgs, key=lambda e: e[1], reverse=True)
            self._output['osd-pgs-near-limit'] = info
            msg = ("{} osd(s) found with > {} pgs - this is close to the hard "
                   "limit at which point they will stop creating pgs and fail "
                   "- please investigate".
                   format(len(error_pgs), OSD_PG_MAX_LIMIT))
            issue = issue_types.CephCrushError(msg)
            issue_utils.add_issue(issue)

        if suboptimal_pgs:
            info = sorted_dict(suboptimal_pgs, key=lambda e: e[1],
                               reverse=True)
            self._output['osd-pgs-suboptimal'] = info
            msg = ("{} osd(s) found with > 10% margin from optimal {} pgs.".
                   format(len(suboptimal_pgs), OSD_PG_OPTIMAL_NUM))
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

    def check_bcache_vulnerabilities(self):
        has_bcache = False
        for osd in self.local_osds:
            dev = osd.device
            if self.is_bcache_device(dev):
                has_bcache = True

        if not has_bcache:
            return

        for cset in bcache.BcacheChecksBase().get_sysfs_cachesets():
            if (cset.get("cache_available_percent") >=
                    LP1936136_BCACHE_CACHE_LIMIT):
                return

        # Get version of osd based on package installed. This is prone to
        # inaccuracy since the daemon many not have been restarted after
        # package update.
        current = self.apt_check.get_version('ceph-osd')
        if current <= DPKGVersionCompare("13.0.1"):
            return
        if current >= DPKGVersionCompare("14.2.10") and \
           current <= DPKGVersionCompare("14.2.21"):
            return
        if current >= DPKGVersionCompare("15.2.2") and \
           current <= DPKGVersionCompare("15.2.12"):
            return
        if current == DPKGVersionCompare("16.1.0") or \
           current == DPKGVersionCompare("17.0.0"):
            return

        if KernelChecksBase().version >= "5.4":
            return

        bluefs_buffered_io = self.ceph_config.get('bluefs_buffered_io')
        if bluefs_buffered_io is False:
            return

        # NOTE: we need a way to check that actual osd config

        # then bluefs_buffered_io is True by default
        msg = ("host may be vulnerable to bcache bug LP 1936136 - please "
               "ensure bluefs_buffered_io is set to False or upgrade to "
               "kernel >= 5.4")
        issue = issue_types.CephCrushWarning(msg)
        issue_utils.add_issue(issue)

    def __call__(self):
        if self.local_osds:
            osds = {}
            for osd in self.local_osds:
                osds.update(osd.to_dict())

            self._output["local-osds"] = sorted_dict(osds)

            self.check_bcache_vulnerabilities()

        self.check_health_status()
        self.check_require_osd_release()
        self.check_osd_msgr_protocol_versions()
        self.check_ceph_bluefs_size()
        self.get_ceph_pg_imbalance()
        self.get_ceph_versions_mismatch()
        self.get_crushmap_mixed_buckets()
        self.check_osdmaps_size()
        self.check_laggy_pgs()


class CephCrushChecks(CephChecksBase):
    def get_crush_summary(self):
        """
        Get crush rules summary and the pools using those rules map.
        """

        if self.crush_rules:
            self._output['crush_rules'] = self.crush_rules

    def __call__(self):
        self.get_crush_summary()
