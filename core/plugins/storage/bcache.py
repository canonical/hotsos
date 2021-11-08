import glob
import os

from core import constants
from core.plugins.storage import StorageBase


class BcacheBase(StorageBase):

    def get_cachesets(self):
        return glob.glob(os.path.join(constants.DATA_ROOT, 'sys/fs/bcache/*'))

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
    def plugin_runnable(self):
        # TODO: define whether this plugin should run or not.
        return True

    @property
    def output(self):
        if self._output:
            return {"bcache": self._output}
