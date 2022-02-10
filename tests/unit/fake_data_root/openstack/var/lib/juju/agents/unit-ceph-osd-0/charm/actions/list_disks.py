#!/usr/bin/env python3
#
# Copyright 2016 Canonical Ltd
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

"""
List disks

The 'disks' key is populated with block devices that are known by udev,
are not mounted and not mentioned in 'osd-journal' configuration option.

The 'blacklist' key is populated with osd-devices in the blacklist stored
in the local kv store of this specific unit.

The 'non-pristine' key is populated with block devices that are known by
udev, are not mounted, not mentioned in 'osd-journal' configuration option
and are currently not eligible for use because of presence of foreign data.
"""

import sys
import os

sys.path.append('hooks/')
sys.path.append('lib/')

import charmhelpers.core.hookenv as hookenv

import charms_ceph.utils
import utils


def list_disk():
    non_pristine = []
    osd_journal = []
    for journal in utils.get_journal_devices():
        osd_journal.append(os.path.realpath(journal))

    for dev in list(set(charms_ceph.utils.unmounted_disks()) -
                    set(osd_journal)):
        if (not charms_ceph.utils.is_active_bluestore_device(dev) and
                not charms_ceph.utils.is_pristine_disk(dev)):
            non_pristine.append(dev)

    hookenv.action_set({
        'disks': list(set(charms_ceph.utils.unmounted_disks()) -
                      set(osd_journal)),
        'blacklist': utils.get_blacklist(),
        'non-pristine': non_pristine,
    })


if __name__ == '__main__':
    list_disk()
