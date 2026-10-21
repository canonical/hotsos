from hotsos.core.host_helpers.storage import LsblkHelper

from .. import utils


class TestLsblkHelper(utils.BaseTestCase):
    """Unit tests for lsblk parsing."""

    @utils.create_data_root({
        'sos_commands/block/lsblk_-O_-P': (
            'PATH="/dev/vda" KNAME="vda"\n'
            'PATH="/dev/broken KNAME="broken"\n'
            'PATH="/dev/missing-kname"\n'
            'PATH="/dev/vdb" KNAME="vdb" '
            'ID-LINK="ceph-osd-0\\x0awnn-0x5000"\n')})
    def test_path_to_kernel_path(self):
        """Test valid device and persistent aliases map to kernel paths."""
        self.assertEqual(LsblkHelper().path_to_kernel_path,
                         {'/dev/vda': '/dev/vda',
                          '/dev/vdb': '/dev/vdb',
                          '/dev/disk/by-id/ceph-osd-0': '/dev/vdb',
                          '/dev/disk/by-id/wnn-0x5000': '/dev/vdb'})

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

    @utils.create_data_root({
        'sos_commands/block/lsblk_-O_-P': (
            'NAME="vda" KNAME="vda" PATH="/dev/vda" TYPE="disk" SIZE="100G" '
            'RO="0" PTTYPE="gpt" PTUUID="uuid-1" FSTYPE="" MOUNTPOINT="" '
            'PKNAME=""\n'
            'NAME="vda1" KNAME="vda1" PATH="/dev/vda1" TYPE="part" '
            'SIZE="1M" RO="0" PTTYPE="" PTUUID="" FSTYPE="" '
            'MOUNTPOINT="" PKNAME="vda" PARTTYPENAME="BIOS boot"\n'
            'NAME="vda2" KNAME="vda2" PATH="/dev/vda2" TYPE="part" '
            'SIZE="50G" RO="0" PTTYPE="" PTUUID="" FSTYPE="ext4" '
            'MOUNTPOINT="/" PKNAME="vda"\n'
            'NAME="vda3" KNAME="vda3" PATH="/dev/vda3" TYPE="part" '
            'SIZE="40G" RO="0" PTTYPE="" PTUUID="" FSTYPE="" '
            'MOUNTPOINT="" PKNAME="vda"\n'),
        'sos_commands/block/ls_-lanR_.sys.block': (
            '/sys/block:\n'
            'lrwxrwxrwx 1 0 0 0 Feb 10 09:38 vda -> '
            '../devices/pci0000:00/00:0b.0/virtio7/block/vda\n')})
    def test_is_partition_unused(self):
        """Test empty partition detection and filtering of boot partitions."""
        helper = LsblkHelper()
        dev_map = {d['KNAME']: d for d in helper.parsed_devices}
        # vda is a disk -> not unused partition
        self.assertFalse(helper.is_partition_unused(dev_map['vda']))
        # vda1 is BIOS boot partition (1M) -> not unused partition
        self.assertFalse(helper.is_partition_unused(dev_map['vda1']))
        # vda2 has ext4 filesystem -> not unused partition
        self.assertFalse(helper.is_partition_unused(dev_map['vda2']))
        # vda3 has no fs, no mount, size 40G -> empty unused partition
        self.assertTrue(helper.is_partition_unused(dev_map['vda3']))

    def test_parse_size_bytes(self):
        """Test parsing human-readable size strings to bytes."""
        self.assertEqual(LsblkHelper.parse_size_bytes(''), 0)
        self.assertEqual(LsblkHelper.parse_size_bytes(None), 0)
        self.assertEqual(LsblkHelper.parse_size_bytes('invalid'), 0)
        self.assertEqual(LsblkHelper.parse_size_bytes('512B'), 512)
        self.assertEqual(LsblkHelper.parse_size_bytes('10M'), 10 * 1024**2)
        self.assertEqual(LsblkHelper.parse_size_bytes('1,5G'),
                         int(1.5 * 1024**3))
        self.assertEqual(LsblkHelper.parse_size_bytes('<99.98g'),
                         int(99.98 * 1024**3))
        self.assertEqual(LsblkHelper.parse_size_bytes('2GiB'), 2 * 1024**3)
        self.assertEqual(LsblkHelper.parse_size_bytes('1E'), 1024**6)

    def test_parse_size_uncertainty_bytes(self):
        """Test computing rounding uncertainty for human-readable sizes."""
        self.assertEqual(LsblkHelper.parse_size_uncertainty_bytes(''), 0)
        self.assertEqual(LsblkHelper.parse_size_uncertainty_bytes(None), 0)
        self.assertEqual(LsblkHelper.parse_size_uncertainty_bytes('512B'), 0)
        self.assertEqual(
            LsblkHelper.parse_size_uncertainty_bytes('1.8T'),
            54975581389)

    def test_format_size_bytes(self):
        """Test formatting byte counts into human-readable size strings."""
        self.assertEqual(LsblkHelper.format_size_bytes(0), '0B')
        self.assertEqual(LsblkHelper.format_size_bytes(-10), '0B')
        self.assertEqual(LsblkHelper.format_size_bytes(512), '512B')
        self.assertEqual(LsblkHelper.format_size_bytes(2048), '2K')
        self.assertEqual(LsblkHelper.format_size_bytes(10 * 1024**2), '10M')
        self.assertEqual(LsblkHelper.format_size_bytes(int(1.5 * 1024**3)),
                         '1.5G')
        self.assertEqual(LsblkHelper.format_size_bytes(60 * 1024**3), '60G')

    @utils.create_data_root({
        'sos_commands/block/lsblk_-O_-P': (
            'NAME="vda" KNAME="vda" PATH="/dev/vda" TYPE="disk" SIZE="100G" '
            'RO="0" PTTYPE="gpt" PTUUID="uuid-1" FSTYPE="" MOUNTPOINT="" '
            'PKNAME=""\n'
            'NAME="vda1" KNAME="vda1" PATH="/dev/vda1" TYPE="part" '
            'SIZE="1M" RO="0" PTTYPE="" PTUUID="" FSTYPE="" '
            'MOUNTPOINT="" PKNAME="vda" PARTTYPENAME="BIOS boot"\n'
            'NAME="vda2" KNAME="vda2" PATH="/dev/vda2" TYPE="part" '
            'SIZE="98G" RO="0" PTTYPE="" PTUUID="" FSTYPE="ext4" '
            'MOUNTPOINT="/" PKNAME="vda"\n'
            'NAME="vdb" KNAME="vdb" PATH="/dev/vdb" TYPE="disk" SIZE="100G" '
            'RO="0" PTTYPE="gpt" PTUUID="uuid-2" FSTYPE="" MOUNTPOINT="" '
            'PKNAME=""\n'
            'NAME="vdb1" KNAME="vdb1" PATH="/dev/vdb1" TYPE="part" '
            'SIZE="40G" RO="0" PTTYPE="" PTUUID="" FSTYPE="ext4" '
            'MOUNTPOINT="/data" PKNAME="vdb"\n'
            'NAME="vdc" KNAME="vdc" PATH="/dev/vdc" TYPE="disk" SIZE="100G" '
            'RO="0" PTTYPE="dos" PTUUID="uuid-3" FSTYPE="" MOUNTPOINT="" '
            'PKNAME=""\n'
            'NAME="vdc1" KNAME="vdc1" PATH="/dev/vdc1" TYPE="part" '
            'SIZE="100G" RO="0" PTTYPE="dos" PTUUID="" FSTYPE="" '
            'MOUNTPOINT="" PKNAME="vdc" PARTTYPE="0x5" '
            'PARTTYPENAME="Extended"\n'
            'NAME="vdc5" KNAME="vdc5" PATH="/dev/vdc5" TYPE="part" '
            'SIZE="40G" RO="0" PTTYPE="dos" PTUUID="" FSTYPE="ext4" '
            'MOUNTPOINT="/srv" PKNAME="vdc"\n'
            'NAME="vdd" KNAME="vdd" PATH="/dev/vdd" TYPE="disk" SIZE="100G" '
            'RO="0" PTTYPE="gpt" PTUUID="uuid-4" FSTYPE="" MOUNTPOINT="" '
            'PKNAME=""\n'
            'NAME="vde" KNAME="vde" PATH="/dev/vde" TYPE="disk" SIZE="1.8T" '
            'RO="0" PTTYPE="gpt" PTUUID="uuid-5" FSTYPE="" MOUNTPOINT="" '
            'PKNAME=""\n'
            'NAME="vde1" KNAME="vde1" PATH="/dev/vde1" TYPE="part" '
            'SIZE="1.7T" RO="0" PTTYPE="" PTUUID="" FSTYPE="ext4" '
            'MOUNTPOINT="/srv2" PKNAME="vde"\n'),
        'sos_commands/block/blockdev_--report': (
            'RO    RA   SSZ   BSZ   StartSec            Size   Device\n'
            'rw   256   512  4096          0    107374182400   /dev/vdb\n'
            'rw   256   512  4096       2048     42949672960   /dev/vdb1\n')})
    def test_get_disk_unallocated_bytes(self):
        """Test detecting unallocated space on partitioned disks."""
        helper = LsblkHelper()
        dev_map = {d['KNAME']: d for d in helper.parsed_devices}
        # vda has 98G+1M allocated out of 100G (< 5% unallocated) -> 0
        self.assertEqual(helper.get_disk_unallocated_bytes(dev_map['vda']), 0)
        # vdb has 40G allocated out of 100G -> 60G unallocated
        self.assertEqual(helper.get_disk_unallocated_bytes(dev_map['vdb']),
                         60 * 1024**3)
        # vdc has extended container vdc1 (100G, ignored) + logical vdc5 (40G)
        # -> 60G unallocated
        self.assertEqual(helper.get_disk_unallocated_bytes(dev_map['vdc']),
                         60 * 1024**3)
        # vdd has GPT partition table but 0 partitions -> 100G unallocated
        self.assertEqual(helper.get_disk_unallocated_bytes(dev_map['vdd']),
                         100 * 1024**3)
        # vde has rounded 1.8T disk and 1.7T partition without blockdev report
        # -> within rounding uncertainty of < 5%, so do not false-positive
        self.assertEqual(helper.get_disk_unallocated_bytes(dev_map['vde']), 0)

    @utils.create_data_root({
        'sos_commands/lvm2/vgs_-v_-o_'
        'vg_mda_count_vg_mda_free_vg_mda_size_vg_mda_used_count_'
        'vg_tags_systemid_--config_global_metadata_read_only_1_'
        '--nolocking_--foreign': (
            '  Reloading config files\n'
            '  WARNING: File locking is disabled.\n'
            '  VG    Attr   Ext   #PV #LV #SN VSize    VFree   VG UUID\n'
            '  vg0   wz--n- 4.00m   1   1   0 <100.00g <60.00g uuid-0\n'
            '  vg1   wz--n- 4.00m   1   1   0  100.00g   2.00g uuid-1\n'
            '  vg2   wz--n- 4.00m   1   1   0   50.00m   4.00m uuid-2\n')})
    def test_unallocated_volume_groups(self):
        """Test detecting LVM volume groups with significant free space."""
        helper = LsblkHelper()
        self.assertEqual(helper.unallocated_volume_groups, ['vg0 (60G)'])
