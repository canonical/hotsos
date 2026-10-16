from unittest import mock

from hotsos.core.config import HotSOSConfig
from hotsos.core.plugins.storage.disks import DiskChecks

from .. import utils


class StorageDisksTestsBase(utils.BaseTestCase):
    """Custom test case that sets the storage plugin context."""

    def setUp(self):
        super().setUp()
        HotSOSConfig.plugin_name = 'storage'


class TestDiskChecks(StorageDisksTestsBase):
    """Unit tests for DiskChecks."""

    @utils.create_data_root({})
    def test_not_runnable_no_data(self):
        """Test is_runnable is False when no lsblk data exists."""
        self.assertFalse(DiskChecks.is_runnable())

    @utils.create_data_root({
        'sos_commands/block/lsblk_-O_-P': (
            'NAME="vda" KNAME="vda" PATH="/dev/vda" TYPE="disk" SIZE="100G" '
            'RO="0" PTTYPE="gpt" PTUUID="uuid-1" FSTYPE="" MOUNTPOINT="" '
            'PKNAME=""\n'
            'NAME="vda1" KNAME="vda1" PATH="/dev/vda1" TYPE="part" '
            'SIZE="100G" RO="0" PTTYPE="" PTUUID="" FSTYPE="ext4" '
            'MOUNTPOINT="/" PKNAME="vda"\n'
            'NAME="vdb" KNAME="vdb" PATH="/dev/vdb" TYPE="disk" SIZE="50G" '
            'RO="0" PTTYPE="" PTUUID="" FSTYPE="" MOUNTPOINT="" PKNAME=""\n'
            'NAME="vdc" KNAME="vdc" PATH="/dev/vdc" TYPE="disk" SIZE="200G" '
            'RO="0" PTTYPE="" PTUUID="" FSTYPE="LVM2_member" MOUNTPOINT="" '
            'PKNAME=""\n'
            'NAME="vdd" KNAME="vdd" PATH="/dev/vdd" TYPE="disk" SIZE="100G" '
            'RO="0" PTTYPE="" PTUUID="" FSTYPE="ext4" MOUNTPOINT="/mnt/data" '
            'PKNAME=""\n'
            'NAME="vde" KNAME="vde" PATH="/dev/vde" TYPE="disk" SIZE="100G" '
            'RO="1" PTTYPE="" PTUUID="" FSTYPE="" MOUNTPOINT="" PKNAME=""\n'
            'NAME="loop0" KNAME="loop0" PATH="/dev/loop0" TYPE="loop" '
            'SIZE="50M" RO="0" PTTYPE="" PTUUID="" FSTYPE="" MOUNTPOINT="" '
            'PKNAME=""\n'
        )})
    def test_unused_disks_detection(self):
        """Test detecting unused disks while ignoring configured/used disks."""
        checks = DiskChecks()
        self.assertTrue(checks.is_runnable())
        self.assertEqual(checks.unused_disks, ['/dev/vdb (50G)'])

    @utils.create_data_root({
        'sos_commands/block/lsblk_-O_-P': (
            'NAME="sda" KNAME="sda" PATH="/dev/sda" TYPE="disk" SIZE="1T" '
            'RO="0" PTTYPE="" PTUUID="" FSTYPE="" MOUNTPOINT="" PKNAME=""\n'
            'NAME="sdb" KNAME="sdb" PATH="/dev/sdb" TYPE="disk" SIZE="1T" '
            'RO="0" PTTYPE="" PTUUID="" FSTYPE="" MOUNTPOINT="" PKNAME=""\n'
        ),
        'sos_commands/multipath/multipath_-ll': (
            'mpatha (3600507630081010) dm-0 IBM,2107900\n'
            'size=1.0T features=\'1 queue_if_no_path\' hwhandler=\'0\' wp=rw\n'
            '`-+- policy=\'service-time 0\' prio=1 status=active\n'
            '  |- 1:0:0:0 sda 8:0  active ready running\n'
            '  `- 2:0:0:0 sdb 8:16 active ready running\n'
        )})
    def test_unused_disks_ignore_multipath(self):
        """Test disks in multipath maps are not marked unused."""
        checks = DiskChecks()
        self.assertEqual(checks.unused_disks, [])

    @utils.create_data_root({
        'sos_commands/block/lsblk_-O_-P': (
            'NAME="vdb" KNAME="vdb" PATH="/dev/vdb" TYPE="disk" SIZE="50G" '
            'RO="0" PTTYPE="" PTUUID="" FSTYPE="" MOUNTPOINT="" PKNAME=""\n'
        )})
    def test_unused_disks_ignore_ceph_osd(self):
        """Test disks configured as Ceph OSD devices are not marked unused."""
        osd_mock = mock.MagicMock()
        osd_mock.dev = '/dev/vdb'
        patch_runnable = mock.patch(
            'hotsos.core.plugins.storage.ceph.common.CephChecks.is_runnable',
            return_value=True)
        patch_osds = mock.patch(
            'hotsos.core.plugins.storage.ceph.common.CephChecks.local_osds',
            new_callable=mock.PropertyMock, return_value=[osd_mock])
        with patch_runnable, patch_osds:
            checks = DiskChecks()
            self.assertEqual(checks.unused_disks, [])


@utils.load_templated_tests('scenarios/storage/disks')
class TestStorageDisksScenarios(StorageDisksTestsBase):
    """Scenario tests for unused disks."""
