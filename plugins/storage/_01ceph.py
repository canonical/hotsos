#!/usr/bin/python3
import json
import re
import subprocess

from common import (
    checks,
    helpers,
    issues_utils,
    plugin_yaml,
)
from common.issue_types import CephCrushWarning

CEPH_SERVICES_EXPRS = [r"ceph-[a-z0-9-]+",
                       r"rados[a-z0-9-:]+"]
CEPH_INFO = {}


class CephChecks(checks.ServiceChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ceph_volume_lvm_list = helpers.get_ceph_volume_lvm_list()
        self.ceph_osd_tree = helpers.get_ceph_osd_tree()
        self.ceph_osd_df_tree = helpers.get_ceph_osd_df_tree()
        self.ceph_versions = helpers.get_ceph_versions()
        self.date_in_secs = self.get_date_secs()

    @staticmethod
    def seconds_to_date(secs):
        days = secs / 86400
        hours = secs / 3600 % 24
        mins = secs / 60 % 60
        secs = secs % 60

        return '{}d:{}h:{}m:{}s'.format(int(days), int(hours),
                                        int(mins), int(secs))

    def get_date_secs(self, datestring=None):
        if datestring:
            cmd = ["date", "--utc", "--date={}".format(datestring), "+%s"]
            date_in_secs = subprocess.check_output(cmd)
        else:
            date_in_secs = helpers.get_date() or 0
            if date_in_secs:
                date_in_secs = date_in_secs.strip()

        return int(date_in_secs)

    @property
    def osd_ids(self):
        """Return list of ceph-osd ids."""
        ceph_osds = self.services.get("ceph-osd")
        if not ceph_osds:
            return []

        osd_ids = []
        for cmd in ceph_osds["ps_cmds"]:
            ret = re.compile(r".+\s+.*--id\s+([0-9]+)\s+.+").match(cmd)
            if ret:
                osd_ids.append(int(ret[1]))

        return osd_ids

    def get_osd_rss(self, osd_id):
        """Return memory RSS for a given OSD."""
        ceph_osds = self.services.get("ceph-osd")
        if not ceph_osds:
            return []

        for cmd in ceph_osds["ps_cmds"]:
            ret = re.compile(r".+/ceph-osd\s+.+--id {}\s+.+".format(
                             osd_id)).match(cmd)
            if ret:
                return int(int(cmd.split()[5]) / 1024)

        return 0

    def get_osd_etime(self, osd_id):
        """Return process etime for a given OSD."""
        if not self.has_ps_axo_flags:
            return

        ceph_osds = self.services.get("ceph-osd")
        if not ceph_osds:
            return []

        for cmd in ceph_osds["ps_cmds"]:
            ret = re.compile(r".+\s+.+--id {}\s+.+".format(
                             osd_id)).match(cmd)
            if ret:
                osd_start = ' '.join(cmd.split()[13:17])
                if self.date_in_secs and osd_start:
                    osd_start_secs = self.get_date_secs(
                                                  datestring=osd_start)
                    osd_uptime_secs = (self.date_in_secs - osd_start_secs)
                    osd_uptime_str = self.seconds_to_date(osd_uptime_secs)
                    return osd_uptime_str

    def get_osd_lvm_info(self, osd_id):
        if not self.ceph_volume_lvm_list:
            return

        info = {}
        for line in self.ceph_volume_lvm_list:
            ret = re.compile(".*==== osd.{} ====.*".format(osd_id)).match(line)
            if ret:
                info['marker'] = 1

            if info.get('marker') is None:
                continue

            if "fsid" not in info:
                ret = re.compile(r"\s+osd\s+fsid\s+([a-z0-9-]+)\s*"
                                 ).match(line)
                if ret:
                    info["fsid"] = ret[1]

            if "dev" not in info:
                ret = re.compile(r"\s+devices\s+([\S]+)\s*").match(line)
                if ret:
                    info["dev"] = ret[1]

            if info.get("dev") and info.get("fsid"):
                break

        if "marker" in info:
            del info["marker"]
            return info

    def get_osd_devtype(self, osd_id):
        if not self.ceph_osd_tree:
            return

        for line in self.ceph_osd_tree:
            if line.split()[3] == "osd.{}".format(osd_id):
                return line.split()[1]

    def get_ceph_pg_imbalance(self):
        """
        Validate PG range.
        Upstream recommends 50-200 OSDs ideally. Higher than 200 is
        also valid if the OSD disks are of different sizes but such
        are generally outliers.
        """
        if not self.ceph_osd_df_tree:
            return

        bad_pgs = {}
        for line in self.ceph_osd_df_tree:
            try:
                if line:
                    last = line.split()[-1]

                if re.compile(r"^osd\.[0-9]+").match(last):
                    osd = line.split()[-1]
                    pg = int(line.split()[-3])
                    if pg > 0 and (pg < 50 or pg > 200):
                        bad_pgs.update({osd: pg})
            except IndexError:
                pass

        if bad_pgs:
            CEPH_INFO["pgs-per-osd"] = bad_pgs

    def get_ceph_versions_mismatch(self):
        """
        Get versions of all Ceph daemons.
        """
        if not self.ceph_versions:
            return

        try:
            data = json.loads(''.join(self.ceph_versions))
        except ValueError:
            return

        daemon_version_info = {}
        if data:
            for unit, _ in data.items():
                if unit == "overall":
                    continue

                vers = []
                for key, _ in data[unit].items():
                    if re.compile(r"ceph version.+").match(key):
                        d_ver = key.split()[2]
                        if d_ver not in vers:
                            vers.append(d_ver)
                if vers:
                    daemon_version_info[unit] = vers

        if daemon_version_info:
            CEPH_INFO["versions"] = daemon_version_info

    def get_osd_info(self):
        osd_info = {}
        for osd_id in self.osd_ids:
            osd_info[osd_id] = {}
            osd_lvm_info = self.get_osd_lvm_info(osd_id)
            if osd_lvm_info:
                osd_info[osd_id].update(osd_lvm_info)

            osd_rss = self.get_osd_rss(osd_id)
            if osd_rss:
                osd_info[osd_id]["rss"] = "{}M".format(osd_rss)

            osd_etime = self.get_osd_etime(osd_id)
            if osd_etime:
                osd_info[osd_id]["etime"] = osd_etime

            osd_devtype = self.get_osd_devtype(osd_id)
            if osd_devtype:
                osd_info[osd_id]["devtype"]

        if osd_info:
            CEPH_INFO["osds"] = osd_info

    def get_running_services_info(self):
        """Get string info for running services."""
        if self.services:
            CEPH_INFO["services"] = self.get_service_info_str()

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
        osd_crush_dump = helpers.get_osd_crush_dump_json_decoded()
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

            # verify if the type_id list contain mixed type id
            if type_ids.count(type_ids[0]) != len(type_ids):
                bad_buckets.append(buckets[bid]["name"])

        if bad_buckets:
            issue = CephCrushWarning("mixed crush buckets indentified (see "
                                     "--storage for more info)")
            issues_utils.add_issue(issue)
            CEPH_INFO["mixed_crush_buckets"] = bad_buckets

    def __call__(self):
        super().__call__()
        self.get_running_services_info()
        self.get_osd_info()
        self.get_ceph_pg_imbalance()
        self.get_ceph_versions_mismatch()
        self.get_crushmap_mixed_buckets()


def get_ceph_checker():
    # Do this way to make it easier to write unit tests.
    return CephChecks(CEPH_SERVICES_EXPRS, use_ps_axo_flags=True)


if __name__ == "__main__":
    get_ceph_checker()()
    if CEPH_INFO:
        plugin_yaml.dump({"ceph": CEPH_INFO})
