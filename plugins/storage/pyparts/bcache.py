import re

from core.cli_helpers import CLIHelper
from core.known_bugs_utils import add_known_bug
from core.issues import (
    issue_types,
    issue_utils,
)
from core.plugins.storage.bcache import BcacheChecksBase

YAML_PRIORITY = 3
# The real limit is 30 but we go just above in case bcache is flapping
# just above and below the limit.
CACHE_AVAILABLE_PERCENT_LIMIT_LP1900438 = 33


class BcacheDeviceChecks(BcacheChecksBase):

    def get_device_info(self):
        devs = {}
        for dev_type in ["bcache", "nvme"]:
            for line in CLIHelper().ls_lanR_sys_block():
                expr = r".+[0-9:]+\s+({}[0-9a-z]+)\s+.+".format(dev_type)
                ret = re.compile(expr).match(line)
                if ret:
                    if dev_type not in devs:
                        devs[dev_type] = {}

                    devname = ret[1]
                    devs[dev_type][devname] = {}
                    for line in CLIHelper().udevadm_info_dev(device=devname):
                        expr = r".+\s+disk/by-dname/(.+)"
                        ret = re.compile(expr).match(line)
                        if ret:
                            devs[dev_type][devname]["dname"] = ret[1]
                        elif "dname" not in devs[dev_type][devname]:
                            devs[dev_type][devname]["dname"] = \
                                "<notfound>"

        if devs:
            self._output["devices"] = devs

    def __call__(self):
        self.get_device_info()


class BcacheStatsChecks(BcacheChecksBase):

    def get_info(self):
        csets = self.get_sysfs_cachesets()
        if csets:
            self._output["cachesets"] = csets

    def check_stats(self):
        if not self.get_sysfs_cachesets():
            return

        for cset in self.get_sysfs_cachesets():
            limit = CACHE_AVAILABLE_PERCENT_LIMIT_LP1900438
            key = 'cache_available_percent'
            if cset[key] <= limit:
                lp_bug = 1900438
                msg = ("bcache {} ({}) is <= {} - this node could be "
                       "suffering from bug LP {}".
                       format(key, cset[key], limit, lp_bug))
                issue_utils.add_issue(issue_types.BcacheWarning(msg))
                add_known_bug(lp_bug, 'see BcacheWarning for info')

    def __call__(self):
        self.get_info()
        self.check_stats()
