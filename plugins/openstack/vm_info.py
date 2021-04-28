#!/usr/bin/python3
import re

from common import (
    helpers,
    plugin_yaml,
)


VM_INFO = []


def get_vm_info():
    for line in helpers.get_ps():
        ret = re.compile(".+product=OpenStack Nova.+").match(line)
        if ret:
            ret = re.compile(r".+uuid\s+([a-z0-9\-]+)[\s,]+.+").match(ret[0])
            if ret:
                VM_INFO.append(ret[1])


if __name__ == "__main__":
    get_vm_info()
    if VM_INFO:
        VM_INFO = {"instances": VM_INFO}
        plugin_yaml.save_part(VM_INFO, priority=1)
