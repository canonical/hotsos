#!/usr/bin/python3
import re

from common import checks


CEPH_SERVICES_EXPRS = [r"ceph-[a-z0-9-]+",
                       r"rados[a-z0-9-:]+"]


class CephChecksBase(checks.ServiceChecksBase):

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
