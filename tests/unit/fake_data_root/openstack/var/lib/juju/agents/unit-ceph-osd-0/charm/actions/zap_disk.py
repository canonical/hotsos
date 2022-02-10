#!/usr/bin/env python3
#
# Copyright 2018 Canonical Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import os
import sys

sys.path.append('lib')
sys.path.append('hooks')

import charmhelpers.core.hookenv as hookenv
from charmhelpers.contrib.storage.linux.utils import (
    is_block_device,
    is_device_mounted,
    zap_disk,
)
from charmhelpers.core.unitdata import kv
from charms_ceph.utils import is_active_bluestore_device
from charms_ceph.utils import is_mapped_luks_device
from charmhelpers.contrib.storage.linux.lvm import is_lvm_physical_volume
from charmhelpers.core.hookenv import log


class ZapDiskError(Exception):
    pass


def get_devices():
    """Parse 'devices' action parameter, returns list."""
    devices, errors = [], []

    for path in hookenv.action_get('devices').split(' '):
        path = path.strip()
        if not os.path.isabs(path):
            errors.append('{}: Not absolute path.'.format(path))
        elif not os.path.exists(path):
            errors.append('{}: Device does not exist.'.format(path))
        else:
            devices.append(path)

    if errors:
        raise ZapDiskError(", ".join(errors))

    return devices


def zap():
    if not hookenv.action_get('i-really-mean-it'):
        hookenv.action_fail('i-really-mean-it is a required parameter')
        return

    failed_devices = []
    not_block_devices = []
    lvm_devices = []
    try:
        devices = get_devices()
    except ZapDiskError as error:
        hookenv.action_fail("Failed due to: {}".format(error))
        return

    for device in devices:
        if is_lvm_physical_volume(device):
            lvm_devices.append(device)
        if not is_block_device(device):
            not_block_devices.append(device)
        if (is_device_mounted(device) or
                is_active_bluestore_device(device) or
                is_mapped_luks_device(device)):
            failed_devices.append(device)

    if lvm_devices or failed_devices or not_block_devices:
        message = ""
        if lvm_devices:
            log('Cannot zap a device used by lvm')
            message = "{} devices are lvm devices: {}".format(
                len(lvm_devices),
                ", ".join(lvm_devices))
        if failed_devices:
            message += "{} devices are mounted: {}".format(
                len(failed_devices),
                ", ".join(failed_devices))
        if not_block_devices:
            if len(message):
                message += "\n\n"
            message += "{} devices are not block devices: {}".format(
                len(not_block_devices),
                ", ".join(not_block_devices))
        hookenv.action_fail(message)
        return
    db = kv()
    used_devices = db.get('osd-devices', [])
    for device in devices:
        zap_disk(device)
        if device in used_devices:
            used_devices.remove(device)
    db.set('osd-devices', used_devices)
    db.flush()
    hookenv.action_set({
        'message': "{} disk(s) have been zapped, to use them as OSDs, run: \n"
                   "juju run-action {} add-disk osd-devices=\"{}\"".format(
                       len(devices),
                       hookenv.local_unit(),
                       " ".join(devices))
    })


if __name__ == "__main__":
    zap()
