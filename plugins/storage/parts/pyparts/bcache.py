import os
import re

from common import cli_helpers
from common.known_bugs_utils import add_known_bug
from common.issues_utils import add_issue
from common.issue_types import BcacheWarning
from storage_common import BcacheChecksBase

YAML_PRIORITY = 3
# The real limit is 30 but we go just above in case bcache is flapping
# just above and below the limit.
CACHE_AVAILABLE_PERCENT_LIMIT_LP1900438 = 33


class BcacheDeviceChecks(BcacheChecksBase):

    def get_device_info(self):
        for dev_type in ["bcache", "nvme"]:
            for line in cli_helpers.get_ls_lanR_sys_block():
                expr = r".+[0-9:]+\s+({}[0-9a-z]+)\s+.+".format(dev_type)
                ret = re.compile(expr).match(line)
                if ret:
                    if dev_type not in self._output:
                        self._output[dev_type] = {}

                    devname = ret[1]
                    self._output[dev_type][devname] = {}
                    for line in cli_helpers.get_udevadm_info_dev(devname):
                        expr = r".+\s+disk/by-dname/(.+)"
                        ret = re.compile(expr).match(line)
                        if ret:
                            self._output[dev_type][devname]["dname"] = ret[1]
                        elif "dname" not in self._output[dev_type][devname]:
                            self._output[dev_type][devname]["dname"] = \
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
