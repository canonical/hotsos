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
