import glob
import os
import re

from common import (
    checks,
    constants,
    plugintools,
    utils,
)
from common.cli_helpers import CLIHelper
from common.searchtools import (
    FileSearcher,
    SequenceSearchDef,
    SearchDef
)


CEPH_SERVICES_EXPRS = [r"ceph-[a-z0-9-]+",
                       r"rados[a-z0-9-:]+"]
CEPH_PKGS_CORE = [r"ceph-[a-z-]+",
                  r"rados[a-z-]+",
                  r"rbd",
                  ]
CEPH_LOGS = "var/log/ceph/"


class StorageChecksBase(plugintools.PluginPartBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)


class CephChecksBase(StorageChecksBase, checks.ServiceChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bcache_info = []
        udevadm_db = CLIHelper().udevadm_info_exportdb()
        if udevadm_db:
            self.udevadm_db = utils.mktemp_dump('\n'.join(udevadm_db))
        else:
            self.udevadm_db = None

    def __del__(self):
        if self.udevadm_db:
            os.unlink(self.udevadm_db)

    @property
    def output(self):
        if self._output:
            return {"ceph": self._output}

    @property
    def bcache_info(self):
        if self._bcache_info:
            return self._bcache_info

        devs = []
        s = FileSearcher()
        sdef = SequenceSearchDef(start=SearchDef(r"^P: .+/(bcache\S+)"),
                                 body=SearchDef(r"^S: disk/by-uuid/(\S+)"),
                                 tag="bcacheinfo")
        s.add_search_term(sdef, self.udevadm_db)
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

    def daemon_pkg_version(self, daemon):
        """Get version of local daemon based on package installed.

        This is prone to inaccuracy since the deamom many not have been
        restarted after package update.
        """
        pkginfo = checks.APTPackageChecksBase(CEPH_PKGS_CORE)
        return pkginfo.get_version(daemon)

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


class CephConfig(checks.SectionalConfigBase):
    def __init__(self, *args, **kwargs):
        path = os.path.join(constants.DATA_ROOT, '/etc/ceph/ceph.conf')
        super().__init__(path=path, *args, **kwargs)


class BcacheChecksBase(StorageChecksBase):

    @property
    def output(self):
        if self._output:
            return {"bcache": self._output}

    def get_sysfs_cachesets(self):
        cachesets = []
        path = os.path.join(constants.DATA_ROOT, "sys/fs/bcache/*")
        for entry in glob.glob(path):
            if os.path.exists(os.path.join(entry, "cache_available_percent")):
                cachesets.append({"path": entry,
                                  "uuid": os.path.basename(entry)})

        for cset in cachesets:
            path = os.path.join(cset['path'], "cache_available_percent")
            with open(path) as fd:
                value = fd.read().strip()
                cset["cache_available_percent"] = int(value)

            # dont include in final output
            del cset["path"]

        return cachesets
