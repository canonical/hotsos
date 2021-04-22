#!/usr/bin/python3
import re

from common import (
    helpers,
    plugin_yaml,
)

BCACHE_INFO = {}


def get_bcache_info():
    for type in ["bcache", "nvme"]:
        for line in helpers.get_ls_lanR_sys_block():
            ret = re.compile(r".+[0-9:]+\s+({}[0-9a-z]+)\s+.+".format(type)
                             ).match(line)
            if ret:
                if type not in BCACHE_INFO:
                    BCACHE_INFO[type] = {}

                devname = ret[1]
                BCACHE_INFO[type][devname] = {}
                for line in helpers.get_udevadm_info_dev(devname):
                    ret = re.compile(r".+\s+disk/by-dname/(.+)").match(line)
                    if ret:
                        BCACHE_INFO[type][devname]["dname"] = ret[1]
                    elif "dname" not in BCACHE_INFO[type][devname]:
                        BCACHE_INFO[type][devname]["dname"] = "<notfound>"


if __name__ == "__main__":
    get_bcache_info()
    if BCACHE_INFO:
        plugin_yaml.dump(BCACHE_INFO)
