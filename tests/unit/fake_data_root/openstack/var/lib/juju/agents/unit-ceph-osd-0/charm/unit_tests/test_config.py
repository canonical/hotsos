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

import os.path
import shutil
import tempfile
import sys
import test_utils

from unittest.mock import patch, MagicMock

# python-apt is not installed as part of test-requirements but is imported by
# some charmhelpers modules so create a fake import.
mock_apt = MagicMock()
sys.modules['apt'] = mock_apt
mock_apt.apt_pkg = MagicMock()


with patch('charmhelpers.contrib.hardening.harden.harden') as mock_dec:
    mock_dec.side_effect = (lambda *dargs, **dkwargs: lambda f:
                            lambda *args, **kwargs: f(*args, **kwargs))
    import ceph_hooks as hooks

TO_PATCH = [
    'config',
    'is_block_device',
    'get_blacklist',
]


class GetDevicesTestCase(test_utils.CharmTestCase):

    def setUp(self):
        super(GetDevicesTestCase, self).setUp(hooks, TO_PATCH)
        self.config.side_effect = self.test_config.get
        self.tmp_dir = tempfile.mkdtemp()
        self.bd = {
            os.path.join(self.tmp_dir, "device1"): True,
            os.path.join(self.tmp_dir, "device1"): True,
            os.path.join(self.tmp_dir, "link"): True,
            os.path.join(self.tmp_dir, "device"): True,
        }
        self.is_block_device.side_effect = lambda x: self.bd.get(x, False)
        self.get_blacklist.return_value = []
        self.addCleanup(shutil.rmtree, self.tmp_dir)

    def test_get_devices_empty(self):
        """
        If osd-devices is set to an empty string, get_devices() returns
        an empty list.
        """
        self.test_config.set("osd-devices", "")
        self.assertEqual([], hooks.get_devices())

    def test_get_devices_non_existing_files(self):
        """
        If osd-devices points to a file that doesn't exist, it's still
        returned by get_devices().
        """
        non_existing = os.path.join(self.tmp_dir, "no-such-file")
        self.test_config.set("osd-devices", non_existing)
        self.assertEqual([non_existing], hooks.get_devices())

    def test_get_devices_multiple(self):
        """
        Multiple devices can be specified in osd-devices by separating
        them with spaces.
        """
        device1 = os.path.join(self.tmp_dir, "device1")
        device2 = os.path.join(self.tmp_dir, "device2")
        self.test_config.set("osd-devices", "{} {}".format(device1, device2))
        self.assertEqual([device1, device2], hooks.get_devices())

    def test_get_devices_extra_spaces(self):
        """
        Multiple spaces do not result in additional devices.
        """
        device1 = os.path.join(self.tmp_dir, "device1")
        device2 = os.path.join(self.tmp_dir, "device2")
        self.test_config.set("osd-devices", "{}  {}".format(device1, device2))
        self.assertEqual([device1, device2], hooks.get_devices())

    def test_get_devices_non_absolute_path(self):
        """
        Charm does not allow relative paths as this may result in a path
        on the root device/within the charm directory.
        """
        device1 = os.path.join(self.tmp_dir, "device1")
        device2 = "foo"
        self.test_config.set("osd-devices", "{} {}".format(device1, device2))
        self.assertEqual([device1], hooks.get_devices())

    def test_get_devices_symlink(self):
        """
        If a symlink is specified in osd-devices, get_devices() does not
        resolve it and returns the symlink provided.
        """
        device = os.path.join(self.tmp_dir, "device")
        link = os.path.join(self.tmp_dir, "link")
        os.symlink(device, link)
        self.test_config.set("osd-devices", link)
        self.assertEqual([link], hooks.get_devices())
