import re

from core.cli_helpers import CLIHelper
from core.plugins.storage.bcache import BcacheChecksBase


class BcacheSummary(BcacheChecksBase):

    def __summary_cachesets(self):
        csets = self.get_sysfs_cachesets()
        if csets:
            return csets

    def __summary_devices(self):
        devs = {}
        for dev_type in ['bcache', 'nvme']:
            for line in CLIHelper().ls_lanR_sys_block():
                expr = r".+[0-9:]+\s+({}[0-9a-z]+)\s+.+".format(dev_type)
                ret = re.compile(expr).match(line)
                if ret:
                    if dev_type not in devs:
                        devs[dev_type] = {}

                    devname = ret[1]
                    devs[dev_type][devname] = {}
                    for line in CLIHelper().udevadm_info_dev(device=devname):
                        expr = r'.+\s+disk/by-dname/(.+)'
                        ret = re.compile(expr).match(line)
                        if ret:
                            devs[dev_type][devname]['dname'] = ret[1]
                        elif 'dname' not in devs[dev_type][devname]:
                            devs[dev_type][devname]['dname'] = \
                                '<notfound>'

        if devs:
            return devs
