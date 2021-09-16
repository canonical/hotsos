import glob
import os

from core import constants
from core.plugins.storage import StorageBase


class BcacheBase(StorageBase):

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


class BcacheChecksBase(BcacheBase):

    @property
    def plugin_runnable(self):
        # TODO: define whether this plugin should run or not.
        return True

    @property
    def output(self):
        if self._output:
            return {"bcache": self._output}
