import mock
import os

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


class TestStoragePlugin01ceph(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(storage_01ceph, "CEPH_INFO", {})
    def test_get_service_info(self):
        result = {'services': ['ceph-osd (6)']}
        storage_01ceph.get_service_info()
        self.assertEqual(storage_01ceph.CEPH_INFO, result)

    @mock.patch.object(storage_01ceph, "CEPH_INFO", {})
    def test_get_ceph_versions_mismatch(self):
        result = {'versions': {
                  'mgr': ['14.2.11'],
                  'mon': ['14.2.11'],
                  'osd': ['14.2.11'],
                  'rgw': ['14.2.11']
                  }}
        storage_01ceph.get_ceph_versions_mismatch()
        self.assertEqual(storage_01ceph.CEPH_INFO, result)

    @mock.patch.object(storage_01ceph, "CEPH_INFO", {})
    def test_get_ceph_pg_imbalance(self):
        result = {'pgs-per-osd': {
                   'osd.0': 295,
                   'osd.3': 214,
                   'osd.15': 49,
                   'osd.16': 316,
                   'osd.17': 370,
                   'osd.34': 392,
                   'osd.37': 406,
                   'osd.56': 209,
                   'osd.72': 206}}
        storage_01ceph.get_ceph_pg_imbalance()
        self.assertEqual(storage_01ceph.CEPH_INFO, result)


class TestStoragePlugin02bcache(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(storage_02bcache, "BCACHE_INFO", {})
    def test_get_bcache_info(self):
        result = {'bcache': {'bcache0': {'dname': 'bcache1'},
                             'bcache1': {'dname': 'bcache3'},
                             'bcache2': {'dname': 'bcache4'},
                             'bcache3': {'dname': 'bcache5'},
                             'bcache4': {'dname': 'bcache2'},
                             'bcache5': {'dname': 'bcache6'},
                             'bcache6': {'dname': 'bcache0'}},
                  'nvme': {'nvme0n1': {'dname': 'nvme0n1'}}}
        storage_02bcache.get_bcache_info()
        self.assertEqual(storage_02bcache.BCACHE_INFO, result)
