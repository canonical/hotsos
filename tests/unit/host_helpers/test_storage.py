from hotsos.core.host_helpers.storage import LsblkHelper

from .. import utils


class TestLsblkHelper(utils.BaseTestCase):
    """Unit tests for lsblk parsing."""

    @utils.create_data_root({
        'sos_commands/block/lsblk_-O_-P': (
            'PATH="/dev/vda" KNAME="vda"\n'
            'PATH="/dev/broken KNAME="broken"\n'
            'PATH="/dev/missing-kname"\n'
            'PATH="/dev/vdb" KNAME="vdb" ID-LINK="ceph-osd-0"\n')})
    def test_path_to_kernel_path(self):
        """Test valid device and persistent aliases map to kernel paths."""
        self.assertEqual(LsblkHelper().path_to_kernel_path,
                         {'/dev/vda': '/dev/vda',
                          '/dev/vdb': '/dev/vdb',
                          '/dev/disk/by-id/ceph-osd-0': '/dev/vdb'})

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
            'NAME="loop0" KNAME="loop0" PATH="/dev/loop0" TYPE="loop" '
            'SIZE="50M" RO="0" PTTYPE="" PTUUID="" FSTYPE="" MOUNTPOINT="" '
            'PKNAME=""\n'),
        'sos_commands/block/ls_-lanR_.sys.block': (
            '/sys/block:\n'
            'lrwxrwxrwx 1 0 0 0 Feb 10 09:38 loop0 -> '
            '../devices/virtual/block/loop0\n'
            'lrwxrwxrwx 1 0 0 0 Feb 10 09:38 vda -> '
            '../devices/pci0000:00/00:0b.0/virtio7/block/vda\n'
            'lrwxrwxrwx 1 0 0 0 Feb 10 09:38 vdb -> '
            '../devices/pci0000:00/00:0c.0/virtio8/block/vdb\n')})
    def test_lsblk_properties_and_unused_detection(self):
        """Test parsed devices, hierarchy and entirely unused detection."""
        helper = LsblkHelper()
        self.assertEqual(len(helper.parsed_devices), 4)
        self.assertIn('vda', helper.children_by_parent)
        self.assertEqual(helper.non_virtual_devices, {'vda', 'vdb'})

        dev_map = {d['KNAME']: d for d in helper.parsed_devices}
        # vda has partition table and child partitions -> not unused
        self.assertFalse(helper.is_disk_entirely_unused(dev_map['vda']))
        # vda1 is a partition -> not unused
        self.assertFalse(helper.is_disk_entirely_unused(dev_map['vda1']))
        # loop0 is virtual / loop device -> not unused
        self.assertFalse(helper.is_disk_entirely_unused(dev_map['loop0']))
        # vdb has no partition table, no fs, no children -> unused
        self.assertTrue(helper.is_disk_entirely_unused(dev_map['vdb']))
