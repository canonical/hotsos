import glob
import os
import re

from hotsos.core.config import HotSOSConfig
from hotsos.core.cli_helpers import CLIHelper
from hotsos.core.plugins.storage import StorageBase
from hotsos.core.searchtools import (
    FileSearcher,
    SequenceSearchDef,
    SearchDef
)
from hotsos.core import utils


class BcacheBase(StorageBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._bcache_devs = []
        self.cli = CLIHelper()

    @property
    def bcache_enabled(self):
        """ Return True if there are any backing devices configured. """
        for cset in self.get_cachesets():
            if self.get_cacheset_bdevs(cset):
                return True

    def get_cachesets(self):
        return glob.glob(os.path.join(HotSOSConfig.DATA_ROOT,
                                      'sys/fs/bcache/*'))

    def get_cacheset_bdevs(self, cset):
        return glob.glob(os.path.join(cset, 'bdev*'))

    def get_sysfs_cachesets(self):
        cachesets = []
        for entry in self.get_cachesets():
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

    @property
    def udev_bcache_devs(self):
        """ If bcache devices exist fetch information and return as a list. """
        if self._bcache_devs:
            return self._bcache_devs

        udevadm_info = self.cli.udevadm_info_exportdb()
        if not udevadm_info:
            return self._bcache_devs

        s = FileSearcher()
        sdef = SequenceSearchDef(start=SearchDef(r"^P: .+/(bcache\S+)"),
                                 body=SearchDef(r"^S: disk/by-uuid/(\S+)"),
                                 tag="bcacheinfo")
        s.add_search_term(sdef, utils.mktemp_dump('\n'.join(udevadm_info)))
        results = s.search()
        devs = []
        for section in results.find_sequence_sections(sdef).values():
            dev = {}
            for r in section:
                if r.tag == sdef.start_tag:
                    dev["name"] = r.get(1)
                else:
                    dev["by-uuid"] = r.get(1)

            devs.append(dev)

        self._bcache_devs = devs
        return self._bcache_devs

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
            for dev in self.udev_bcache_devs:
                if dev.get("by-uuid") == ret.group(1):
                    return True

        return False


class CachesetsConfig(BcacheBase):

    def get(self, key):
        for cset in self.get_cachesets():
            cfg = os.path.join(cset, key)
            if os.path.exists(cfg):
                with open(cfg) as fd:
                    return fd.read().strip()


class BdevsConfig(BcacheBase):

    def get(self, key):
        for cset in self.get_cachesets():
            for bdev in self.get_cacheset_bdevs(cset):
                cfg = os.path.join(bdev, key)
                if os.path.exists(cfg):
                    with open(cfg) as fd:
                        return fd.read().strip()


class BcacheChecksBase(BcacheBase):

    @property
    def summary_subkey(self):
        return 'bcache'

    @property
    def plugin_runnable(self):
        return self.bcache_enabled
