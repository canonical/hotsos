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

from unittest import mock

from actions import zap_disk

from test_utils import CharmTestCase


class ZapDiskActionTests(CharmTestCase):
    def setUp(self):
        super(ZapDiskActionTests, self).setUp(
            zap_disk, ['hookenv',
                       'is_block_device',
                       'is_device_mounted',
                       'is_active_bluestore_device',
                       'is_mapped_luks_device',
                       'is_lvm_physical_volume',
                       'kv'])
        self.is_device_mounted.return_value = False
        self.is_block_device.return_value = True
        self.is_active_bluestore_device.return_value = False
        self.is_mapped_luks_device.return_value = False
        self.is_lvm_physical_volume.return_value = False
        self.kv.return_value = self.kv
        self.hookenv.local_unit.return_value = "ceph-osd-test/0"

    @mock.patch('os.path.exists', mock.MagicMock(return_value=True))
    @mock.patch.object(zap_disk, 'zap_disk')
    def test_authorized_zap_single_disk(self,
                                        _zap_disk):
        """Will zap disk with extra config set"""
        def side_effect(arg):
            return {
                'devices': '/dev/vdb',
                'i-really-mean-it': True,
            }.get(arg)

        self.hookenv.action_get.side_effect = side_effect
        self.kv.get.return_value = ['/dev/vdb', '/dev/vdz']
        zap_disk.zap()
        _zap_disk.assert_called_with('/dev/vdb')
        self.kv.get.assert_called_with('osd-devices', [])
        self.kv.set.assert_called_with('osd-devices', ['/dev/vdz'])
        self.hookenv.action_set.assert_called_with({
            'message': "1 disk(s) have been zapped, to use "
                       "them as OSDs, run: \njuju "
                       "run-action ceph-osd-test/0 add-disk "
                       "osd-devices=\"/dev/vdb\""
        })

    @mock.patch('os.path.exists', mock.MagicMock(return_value=True))
    @mock.patch.object(zap_disk, 'zap_disk')
    def test_authorized_zap_multiple_disks(self,
                                           _zap_disk):
        """Will zap disk with extra config set"""
        def side_effect(arg):
            return {
                'devices': '/dev/vdb /dev/vdc',
                'i-really-mean-it': True,
            }.get(arg)

        self.hookenv.action_get.side_effect = side_effect
        self.kv.get.return_value = ['/dev/vdb', '/dev/vdz']
        zap_disk.zap()
        _zap_disk.assert_has_calls([
            mock.call('/dev/vdb'),
            mock.call('/dev/vdc'),
        ])
        self.kv.get.assert_called_with('osd-devices', [])
        self.kv.set.assert_called_with('osd-devices', ['/dev/vdz'])
        self.hookenv.action_set.assert_called_with({
            'message': "2 disk(s) have been zapped, to use "
                       "them as OSDs, run: \njuju "
                       "run-action ceph-osd-test/0 add-disk "
                       "osd-devices=\"/dev/vdb /dev/vdc\""
        })

    @mock.patch('os.path.exists', mock.MagicMock(return_value=True))
    @mock.patch.object(zap_disk, 'zap_disk')
    def test_wont_zap_non_block_device(self,
                                       _zap_disk):
        """Will not zap a disk that isn't a block device"""
        def side_effect(arg):
            return {
                'devices': '/dev/vdb',
                'i-really-mean-it': True,
            }.get(arg)

        self.hookenv.action_get.side_effect = side_effect
        self.is_block_device.return_value = False
        zap_disk.zap()
        _zap_disk.assert_not_called()
        self.hookenv.action_fail.assert_called_with(
            "1 devices are not block devices: /dev/vdb")

    @mock.patch('os.path.exists', mock.MagicMock(return_value=True))
    @mock.patch.object(zap_disk, 'zap_disk')
    def test_wont_zap_mounted_block_device(self,
                                           _zap_disk):
        """Will not zap a disk that is mounted"""
        def side_effect(arg):
            return {
                'devices': '/dev/vdb',
                'i-really-mean-it': True,
            }.get(arg)

        self.hookenv.action_get.side_effect = side_effect
        self.is_device_mounted.return_value = True
        zap_disk.zap()
        _zap_disk.assert_not_called()
        self.hookenv.action_fail.assert_called_with(
            "1 devices are mounted: /dev/vdb")

    @mock.patch('os.path.exists', mock.MagicMock(return_value=True))
    @mock.patch.object(zap_disk, 'zap_disk')
    def test_wont_zap__mounted_bluestore_device(self,
                                                _zap_disk):
        """Will not zap a disk that is mounted"""
        def side_effect(arg):
            return {
                'devices': '/dev/vdb',
                'i-really-mean-it': True,
            }.get(arg)

        self.hookenv.action_get.side_effect = side_effect
        self.is_active_bluestore_device.return_value = True
        zap_disk.zap()
        _zap_disk.assert_not_called()
        self.hookenv.action_fail.assert_called_with(
            "1 devices are mounted: /dev/vdb")

    @mock.patch('os.path.exists', mock.MagicMock(return_value=True))
    @mock.patch.object(zap_disk, 'zap_disk')
    def test_wont_zap__mapped_luks_device(self, _zap_disk):
        """Will not zap a disk that has a LUKS header"""
        def side_effect(arg):
            return {
                'devices': '/dev/vdb',
                'i-really-mean-it': True,
            }.get(arg)

        self.hookenv.action_get.side_effect = side_effect
        self.is_active_bluestore_device.return_value = False
        self.is_mapped_luks_device.return_value = True
        zap_disk.zap()
        _zap_disk.assert_not_called()
        self.hookenv.action_fail.assert_called_with(
            "1 devices are mounted: /dev/vdb")

    @mock.patch('os.path.exists', mock.MagicMock(return_value=True))
    @mock.patch.object(zap_disk, 'zap_disk')
    def test_zap_luks_not_mapped(self, _zap_disk):
        """Will zap disk with extra config set"""
        def side_effect(arg):
            return {
                'devices': '/dev/vdb',
                'i-really-mean-it': True,
            }.get(arg)

        self.is_active_bluestore_device.return_value = False
        self.is_mapped_luks_device.return_value = False

        self.hookenv.action_get.side_effect = side_effect
        self.kv.get.return_value = ['/dev/vdb', '/dev/vdz']
        zap_disk.zap()
        _zap_disk.assert_called_with('/dev/vdb')
        self.kv.get.assert_called_with('osd-devices', [])
        self.kv.set.assert_called_with('osd-devices', ['/dev/vdz'])
        self.hookenv.action_set.assert_called_with({
            'message': "1 disk(s) have been zapped, to use "
                       "them as OSDs, run: \njuju "
                       "run-action ceph-osd-test/0 add-disk "
                       "osd-devices=\"/dev/vdb\""
        })

    @mock.patch.object(zap_disk, 'zap_disk')
    def test_wont_zap_non_existent_device(self, _zap_disk):
        """Won't zap non-existent disk"""
        def side_effect(arg):
            return {
                'devices': '/dev/not-valid-disk',
                'i-really-mean-it': True,
            }.get(arg)

        self.hookenv.action_get.side_effect = side_effect
        zap_disk.zap()
        _zap_disk.assert_not_called()
        self.hookenv.action_fail.assert_called_with(
            'Failed due to: /dev/not-valid-disk: Device does not exist.')
        self.hookenv.action_set.assert_not_called()

    @mock.patch.object(zap_disk, 'zap_disk')
    def test_wont_zap_not_abs_path(self, _zap_disk):
        """Won't zap not absolute path"""
        def side_effect(arg):
            return {
                'devices': 'not-absolute',
                'i-really-mean-it': True,
            }.get(arg)

        self.hookenv.action_get.side_effect = side_effect
        zap_disk.zap()
        _zap_disk.assert_not_called()
        self.hookenv.action_fail.assert_called_with(
            'Failed due to: not-absolute: Not absolute path.')
        self.hookenv.action_set.assert_not_called()

    @mock.patch('os.path.exists', mock.MagicMock(return_value=True))
    @mock.patch.object(zap_disk, 'zap_disk')
    def test_wont_zap_lvm_device(self, _zap_disk):
        """Won't zap lvm disk"""
        def side_effect(arg):
            return {
                'devices': '/dev/vdb',
                'i-really-mean-it': True,
            }.get(arg)

        self.hookenv.action_get.side_effect = side_effect
        self.is_lvm_physical_volume.return_value = True

        zap_disk.zap()
        _zap_disk.assert_not_called()
        self.hookenv.action_fail.assert_called_with(
            '1 devices are lvm devices: /dev/vdb')
        self.hookenv.action_set.assert_not_called()
