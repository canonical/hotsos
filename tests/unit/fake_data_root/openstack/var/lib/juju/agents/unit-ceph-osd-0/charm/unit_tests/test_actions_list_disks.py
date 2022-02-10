from actions import list_disks

from test_utils import CharmTestCase


class ListDisksActionTests(CharmTestCase):
    def setUp(self):
        super(ListDisksActionTests, self).setUp(
            list_disks, ['hookenv',
                         'charms_ceph',
                         'utils',
                         'os'])
        self.charms_ceph.utils.unmounted_disks.return_value = ['/dev/sda',
                                                               '/dev/sdm']

    def test_list_disks_journal_symbol_link(self):
        self.utils.get_journal_devices.return_value = {'/dev/disk/ceph/sdm'}
        self.os.path.realpath.return_value = '/dev/sdm'
        self.charms_ceph.utils.is_active_bluestore_device.return_value = False
        self.charms_ceph.utils.is_pristine_disk.return_value = False
        self.utils.get_blacklist.return_value = []
        list_disks.list_disk()
        self.hookenv.action_set.assert_called_with({
            'disks': ['/dev/sda'],
            'blacklist': [],
            'non-pristine': ['/dev/sda']
        })
