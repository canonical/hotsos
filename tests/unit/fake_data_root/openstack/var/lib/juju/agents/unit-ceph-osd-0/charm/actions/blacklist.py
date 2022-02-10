#!/usr/bin/env python3
#
# Copyright 2017 Canonical Ltd
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

sys.path.append('hooks')

import charmhelpers.core.hookenv as hookenv
import charmhelpers.core.unitdata as unitdata

BLACKLIST_KEY = 'osd-blacklist'


class Error(Exception):
    def __init__(self, message):
        self.message = message

    def __str__(self):
        return repr(self.message)


def get_devices():
    """Parse 'osd-devices' action parameter, returns list."""
    devices = []
    for path in hookenv.action_get('osd-devices').split(' '):
        path = path.strip()
        if not os.path.isabs(path):
            raise Error('{}: Not absolute path.'.format(path))
        devices.append(path)
    return devices


def blacklist_add():
    """
    Add devices given in 'osd-devices' action parameter to
    unit-local devices blacklist.
    """
    db = unitdata.kv()
    blacklist = db.get(BLACKLIST_KEY, [])
    for device in get_devices():
        if not os.path.exists(device):
            raise Error('{}: No such file or directory.'.format(device))
        if device not in blacklist:
            blacklist.append(device)
    db.set(BLACKLIST_KEY, blacklist)
    db.flush()


def blacklist_remove():
    """
    Remove devices given in 'osd-devices' action parameter from
    unit-local devices blacklist.
    """
    db = unitdata.kv()
    blacklist = db.get(BLACKLIST_KEY, [])
    for device in get_devices():
        try:
            blacklist.remove(device)
        except ValueError:
            raise Error('{}: Device not in blacklist.'.format(device))
    db.set(BLACKLIST_KEY, blacklist)
    db.flush()


# A dictionary of all the defined actions to callables
ACTIONS = {
    "blacklist-add-disk": blacklist_add,
    "blacklist-remove-disk": blacklist_remove,
}


def main(args):
    """Main program"""
    action_name = os.path.basename(args[0])
    try:
        action = ACTIONS[action_name]
    except KeyError:
        return "Action {} undefined".format(action_name)
    else:
        try:
            action()
        except Exception as e:
            hookenv.action_fail("Action {} failed: {}"
                                "".format(action_name, str(e)))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
