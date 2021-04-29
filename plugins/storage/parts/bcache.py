#!/usr/bin/python3
import glob
import os
import re


from common import (
    constants,
    helpers,
    plugin_yaml,
)
from common.known_bugs_utils import add_known_bug
from common.issues_utils import add_issue
from common.issue_types import BcacheWarning

BCACHE_INFO = {}
# The real limit is 30 but we go just above in case bcache is flapping
# just above and below the limit.
CACHE_AVAILABLE_PERCENT_LIMIT_LP1900438 = 33


class BcacheChecksBase(object):

    def get_sysfs_cachesets(self):
        return glob.glob(os.path.join(constants.DATA_ROOT, "sys/fs/bcache/*"))


class BcacheDeviceChecks(BcacheChecksBase):

    def get_device_info(self):
        for dev_type in ["bcache", "nvme"]:
            for line in helpers.get_ls_lanR_sys_block():
                expr = r".+[0-9:]+\s+({}[0-9a-z]+)\s+.+".format(dev_type)
                ret = re.compile(expr).match(line)
                if ret:
                    if dev_type not in BCACHE_INFO:
                        BCACHE_INFO[dev_type] = {}

                    devname = ret[1]
                    BCACHE_INFO[dev_type][devname] = {}
                    for line in helpers.get_udevadm_info_dev(devname):
                        expr = r".+\s+disk/by-dname/(.+)"
                        ret = re.compile(expr).match(line)
                        if ret:
                            BCACHE_INFO[dev_type][devname]["dname"] = ret[1]
                        elif "dname" not in BCACHE_INFO[dev_type][devname]:
                            BCACHE_INFO[dev_type][devname]["dname"] = \
                                "<notfound>"

    def __call__(self):
        self.get_device_info()


class BcacheStatsChecks(BcacheChecksBase):

    def check_stats(self):
        if not self.get_sysfs_cachesets():
            return

        for path in self.get_sysfs_cachesets():
            path = os.path.join(path, "cache_available_percent")
            with open(path) as fd:
                value = fd.read().strip()
                limit = CACHE_AVAILABLE_PERCENT_LIMIT_LP1900438
                if int(value) <= limit:
                    msg = ("bcache cache_available_percent ({}) is <= {} - "
                           "this node could be suffering from bug 1900438".
                           format(value, limit))
                    add_issue(BcacheWarning(msg))
                    add_known_bug(1900438, "see BcacheWarning for info")

    def __call__(self):
        self.check_stats()


def get_bcache_dev_checks():
    return BcacheDeviceChecks()


def get_bcache_stats_checks():
    return BcacheStatsChecks()


if __name__ == "__main__":
    get_bcache_dev_checks()()
    get_bcache_stats_checks()()
    if BCACHE_INFO:
        plugin_yaml.save_part(BCACHE_INFO, priority=1)
