#!/usr/bin/python3
import re

from common import (
    helpers,
    plugin_yaml,
)

BCACHE_INFO = {}


class BcacheChecksBase(object):
    pass


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


def get_bcache_checks():
    return BcacheDeviceChecks()


if __name__ == "__main__":
    get_bcache_checks()()
    if BCACHE_INFO:
        plugin_yaml.save_part(BCACHE_INFO, priority=1)
