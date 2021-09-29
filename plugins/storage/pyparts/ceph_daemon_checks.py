import re

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
from core.plugins.kernel import KernelChecksBase

YAML_PRIORITY = 1
LP1936136_BCACHE_CACHE_LIMIT = 70
OSD_PG_MAX_LIMIT = 500
OSD_PG_OPTIMAL_NUM = 200


class CephOSDChecks(ceph.CephChecksBase):

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
            msg = ("{} OSDs do not bind to v2 address".format(len(v1_osds)))
            issue_utils.add_issue(issue_types.CephOSDWarning(msg))

    def get_ceph_pg_imbalance(self):
        """ Validate PG counts on OSDs

        Upstream recommends 50-200 OSDs ideally. Higher than 200 is also valid
        if the OSD disks are of different sizes but that tends to be the
        exception rather than the norm.

        We also check for OSDs with excessive numbers of PGs that can cause
        them to fail.
        """
        ceph_osd_df_tree = self.cli.ceph_osd_df_tree()
        if not ceph_osd_df_tree:
            return

        # Find index of PGS column in output.
        pgs_idx = None
        header = ceph_osd_df_tree[0].split()
        for i, col in enumerate(header):
            if col == "PGS":
                pgs_idx = i + 1
                break

        if not pgs_idx:
            return

        pgs_idx = -(len(header) - pgs_idx)
        suboptimal_pgs = {}
        error_pgs = {}
        for line in ceph_osd_df_tree:
            try:
                ret = re.compile(r"\s+(osd\.\d+)\s*$").search(line)
                if ret:
                    osd_id = ret.group(1)
                    pgs = int(line.split()[pgs_idx])
                    if pgs > OSD_PG_MAX_LIMIT:
                        error_pgs[osd_id] = pgs

                    margin = abs(100 - (float(100) / OSD_PG_OPTIMAL_NUM * pgs))
                    # allow 30% margin from optimal OSD_PG_OPTIMAL_NUM value
                    if margin > 30:
                        suboptimal_pgs[osd_id] = pgs
            except IndexError:
                pass

        if error_pgs:
            info = sorted_dict(error_pgs, key=lambda e: e[1], reverse=True)
            self._output['osd-pgs-near-limit'] = info
            msg = ("{} osds found with > {} pgs - this is close to the hard "
                   "limit at which point OSDs will stop creating pgs and fail "
                   "- please investigate".
                   format(len(error_pgs), OSD_PG_MAX_LIMIT))
            issue = issue_types.CephCrushError(msg)
            issue_utils.add_issue(issue)

        if suboptimal_pgs:
            info = sorted_dict(suboptimal_pgs, key=lambda e: e[1],
                               reverse=True)
            self._output['osd-pgs-suboptimal'] = info
            msg = ("{} osds found with > 10% margin from optimal {} pgs.".
                   format(len(suboptimal_pgs), OSD_PG_OPTIMAL_NUM))
            issue = issue_types.CephCrushWarning(msg)
            issue_utils.add_issue(issue)

    def get_ceph_versions_mismatch(self):
        """
        Get versions of all Ceph daemons.
        """
        versions = ceph.CephCluster().daemon_versions()
        if not versions:
            return

        global_vers = set()
        daemon_version_info = {}
        for daemon_type in versions:
            # skip the catchall
            if daemon_type == 'overall':
                continue

            vers = []
            for version in versions[daemon_type]:
                vers.append(version)
                global_vers.add(version)

            if vers:
                daemon_version_info[daemon_type] = vers

        if daemon_version_info:
            self._output['versions'] = daemon_version_info
            if len(global_vers) > 1:
                msg = ('ceph daemon versions not aligned')
                issue = issue_types.CephDaemonWarning(msg)
                issue_utils.add_issue(issue)

    def build_buckets_from_crushdump(self, crushdump):
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
        buckets = self.build_buckets_from_crushdump(osd_crush_dump)
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
            msg = ("mixed crush buckets identified (see --storage for more "
                   "info)")
            issue = issue_types.CephCrushWarning(msg)
            issue_utils.add_issue(issue)
            self._output["mixed_crush_buckets"] = bad_buckets

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
        msg = ("host may be vulnerable to bcache bug 1936136 - please ensure "
               "bluefs_buffered_io is set to False or upgrade to kernel "
               ">= 5.4")
        issue = issue_types.CephCrushWarning(msg)
        issue_utils.add_issue(issue)

    def __call__(self):
        if self.local_osds:
            osds = {}
            for osd in self.local_osds:
                osds.update(osd.to_dict())

            self._output["local-osds"] = sorted_dict(osds)

            self.check_bcache_vulnerabilities()

        self.check_require_osd_release()
        self.check_osd_msgr_protocol_versions()
        self.get_ceph_pg_imbalance()
        self.get_ceph_versions_mismatch()
        self.get_crushmap_mixed_buckets()
