import os
import mock

from importlib.util import spec_from_loader, module_from_spec
from importlib.machinery import SourceFileLoader

import utils

os.environ["VERBOSITY_LEVEL"] = "1000"

# need this for non-standard import
specs = {}
for plugin in ["01ceph", "02bcache"]:
    loader = SourceFileLoader("storage_{}".format(plugin),
                              "plugins/storage/{}".format(plugin))
    specs[plugin] = spec_from_loader("storage_{}".format(plugin), loader)

storage_01ceph = module_from_spec(specs["01ceph"])
specs["01ceph"].loader.exec_module(storage_01ceph)

storage_02bcache = module_from_spec(specs["02bcache"])
specs["02bcache"].loader.exec_module(storage_02bcache)

PS = """
root       11722  0.0  0.0  18028  1536 ?        Ss    2020   0:00 bash /lib/systemd/system/jujud-unit-ceph-osd-no-fixed-wal-7/exec-start.sh
root       11736  1.2  0.0 3706068 413888 ?      Sl    2020 4094:00 /var/lib/juju/tools/unit-ceph-osd-no-fixed-wal-7/jujud unit --data-dir /var/lib/juju --unit-name ceph-osd-no-fixed-wal/7 --debug
ceph       28718 12.4  0.7 6288484 3960044 ?     Ssl   2020 42280:23 /usr/bin/ceph-osd -f --cluster ceph --id 63 --setuser ceph --setgroup ceph
ceph       30119 11.0  0.7 6510576 4163504 ?     Ssl   2020 37296:54 /usr/bin/ceph-osd -f --cluster ceph --id 81 --setuser ceph --setgroup ceph
ceph       30824 11.0  0.7 6484804 4213288 ?     Ssl   2020 37513:17 /usr/bin/ceph-osd -f --cluster ceph --id 90 --setuser ceph --setgroup ceph
ceph       32278 11.1  0.7 7482112 3991568 ?     Ssl   2020 37791:59 /usr/bin/ceph-osd -f --cluster ceph --id 109 --setuser ceph --setgroup ceph
ceph     2054740 10.5  0.7 6041588 4060788 ?     Ssl   2020 9653:21 /usr/bin/ceph-osd -f --cluster ceph --id 101 --setuser ceph --setgroup ceph
ceph     2054743 16.4  0.7 6558232 4138916 ?     Ssl   2020 15089:10 /usr/bin/ceph-osd -f --cluster ceph --id 70 --setuser ceph --setgroup ceph
"""  # noqa

LS_LANR_SYS_BLOCK = """
/sys/block:
total 0
drwxr-xr-x  2 0 0 0 Jun 19  2020 .
dr-xr-xr-x 13 0 0 0 Jun 19  2020 ..
lrwxrwxrwx  1 0 0 0 Jun 19  2020 bcache0 -> ../devices/virtual/block/bcache0
lrwxrwxrwx  1 0 0 0 Jun 19  2020 dm-0 -> ../devices/virtual/block/dm-0
lrwxrwxrwx  1 0 0 0 Jun 19  2020 dm-1 -> ../devices/virtual/block/dm-1
lrwxrwxrwx  1 0 0 0 Jun 19  2020 dm-2 -> ../devices/virtual/block/dm-2
lrwxrwxrwx  1 0 0 0 Jun 19  2020 dm-3 -> ../devices/virtual/block/dm-3
lrwxrwxrwx  1 0 0 0 Jun 19  2020 dm-4 -> ../devices/virtual/block/dm-4
lrwxrwxrwx  1 0 0 0 Jun 19  2020 dm-5 -> ../devices/virtual/block/dm-5
lrwxrwxrwx  1 0 0 0 Jun 19  2020 nvme0n1 -> ../devices/pci0000:ae/0000:ae:00.0/0000:af:00.0/nvme/nvme0/nvme0n1
lrwxrwxrwx  1 0 0 0 Jun 19  2020 sda -> ../devices/pci0000:17/0000:17:00.0/0000:18:00.0/host6/port-6:0/end_device-6:0/target6:0:0/6:0:0:0/block/sda
lrwxrwxrwx  1 0 0 0 Jun 19  2020 sdb -> ../devices/pci0000:17/0000:17:00.0/0000:18:00.0/host6/port-6:1/end_device-6:1/target6:0:1/6:0:1:0/block/sdb
"""  # noqa

UDEVADM_INFO_DEV = """
P: /devices/virtual/block/bcache0
N: bcache0
S: bcache/by-label/bcache1
S: bcache/by-uuid/d400ab68-b08a-460f-905f-ae722b848f1c
S: disk/by-dname/bcache1
S: disk/by-id/lvm-pv-uuid-8IBGzW-fm7a-IPY0-mUPB-bN01-dDoU-bRteXY
E: DEVLINKS=/dev/disk/by-dname/bcache1 /dev/disk/by-id/lvm-pv-uuid-8IBGzW-fm7a-IPY0-mUPB-bN01-dDoU-bRteXY /dev/bcache/by-label/bcache1 /dev/bcache/by-uuid/d400ab68-b08a-460f-905f-ae722b848f1c
E: DEVNAME=/dev/bcache0
E: DEVPATH=/devices/virtual/block/bcache0
E: DEVTYPE=disk
E: ID_FS_TYPE=LVM2_member
E: ID_FS_USAGE=raid
E: ID_FS_UUID=8IBGzW-fm7a-IPY0-mUPB-bN01-dDoU-bRteXY
E: ID_FS_UUID_ENC=8IBGzW-fm7a-IPY0-mUPB-bN01-dDoU-bRteXY
E: ID_FS_VERSION=LVM2 001
E: MAJOR=252
E: MINOR=0
E: SUBSYSTEM=block
E: TAGS=:systemd:
E: USEC_INITIALIZED=8684720
"""  # noqa


def fake_ps():
    return [line + '\n' for line in PS.split('\n')]


def fake_ls_lanR_sys_block():
    return [line + '\n' for line in LS_LANR_SYS_BLOCK.split('\n')]


def fake_get_udevadm_info_dev(devname):
    return [line + '\n' for line in UDEVADM_INFO_DEV.split('\n')]


class TestStoragePlugin01ceph(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(storage_01ceph, "CEPH_INFO", {})
    @mock.patch.object(storage_01ceph.helpers, 'get_ps', fake_ps)
    def test_get_service_info(self):
        result = {'services': ['ceph-osd (6)']}
        storage_01ceph.get_service_info()
        self.assertEqual(storage_01ceph.CEPH_INFO, result)


class TestStoragePlugin02bcache(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(storage_02bcache, "BCACHE_INFO", {})
    @mock.patch.object(storage_02bcache.helpers, 'get_ls_lanR_sys_block',
                       fake_ls_lanR_sys_block)
    @mock.patch.object(storage_02bcache.helpers, 'get_udevadm_info_dev',
                       fake_get_udevadm_info_dev)
    def test_get_bcache_info(self):
        result = {'bcache': {'bcache0': {'dname': 'bcache1'}},
                  'nvme': {'nvme0n1': {'dname': 'bcache1'}}}
        storage_02bcache.get_bcache_info()
        self.assertEqual(storage_02bcache.BCACHE_INFO, result)
