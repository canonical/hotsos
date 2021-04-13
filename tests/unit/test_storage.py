import mock
import os

from importlib.util import spec_from_loader, module_from_spec
from importlib.machinery import SourceFileLoader

import utils

os.environ["VERBOSITY_LEVEL"] = "1000"

# need this for non-standard import
specs = {}
for plugin in ["01ceph", "02bcache", "03ceph_daemon_logs"]:
    loader = SourceFileLoader("storage_{}".format(plugin),
                              "plugins/storage/{}".format(plugin))
    specs[plugin] = spec_from_loader("storage_{}".format(plugin), loader)

storage_01ceph = module_from_spec(specs["01ceph"])
specs["01ceph"].loader.exec_module(storage_01ceph)

storage_02bcache = module_from_spec(specs["02bcache"])
specs["02bcache"].loader.exec_module(storage_02bcache)

storage_03ceph_daemon_logs = module_from_spec(specs["03ceph_daemon_logs"])
specs["03ceph_daemon_logs"].loader.exec_module(storage_03ceph_daemon_logs)


class TestStoragePlugin01ceph(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(storage_01ceph.helpers, "get_date")
    def test_get_date_secs(self, mock_get_date):
        mock_get_date.return_value = "1234\n"
        self.assertEquals(storage_01ceph.get_date_secs(), 1234)

    @mock.patch.object(storage_01ceph.helpers, "get_date")
    def test_get_date_secs_from_timestamp(self, mock_get_date):
        mock_get_date.return_value = "1234\n"
        date_string = "Thu Mar 25 10:55:05 MDT 2021"
        self.assertEquals(storage_01ceph.get_date_secs(date_string),
                          1616691305)

    @mock.patch.object(storage_01ceph.helpers, "get_date")
    def test_get_date_secs_from_timestamp_w_tz(self, mock_get_date):
        mock_get_date.return_value = "1234\n"
        date_string = "Thu Mar 25 10:55:05 UTC 2021"
        self.assertEquals(storage_01ceph.get_date_secs(date_string),
                          1616669705)

    @mock.patch.object(storage_01ceph, "CEPH_INFO", {})
    def test_get_service_info(self):
        result = {'services': ['ceph-osd (6)']}
        storage_01ceph.get_service_info()
        self.assertEqual(storage_01ceph.CEPH_INFO, result)

    @mock.patch.object(storage_01ceph.helpers, "get_ps",
                       lambda: [])
    @mock.patch.object(storage_01ceph, "CEPH_INFO", {})
    def test_get_service_info_unavailable(self):
        storage_01ceph.get_service_info()
        self.assertEqual(storage_01ceph.CEPH_INFO, {})

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

    @mock.patch.object(storage_01ceph.helpers, "get_ceph_versions",
                       lambda: [])
    @mock.patch.object(storage_01ceph, "CEPH_INFO", {})
    def test_get_ceph_versions_mismatch_unavailable(self):
        storage_01ceph.get_ceph_versions_mismatch()
        self.assertEqual(storage_01ceph.CEPH_INFO, {})

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

    @mock.patch.object(storage_01ceph.helpers, "get_ceph_osd_df_tree",
                       lambda: [])
    @mock.patch.object(storage_01ceph, "CEPH_INFO", {})
    def test_get_ceph_pg_imbalance_unavailable(self):
        storage_01ceph.get_ceph_pg_imbalance()
        self.assertEqual(storage_01ceph.CEPH_INFO, {})

    @mock.patch.object(storage_01ceph, "CEPH_INFO", {})
    def test_get_osd_info(self):
        expected = {'osds': {63: {'dev': '/dev/bcache0', 'rss': '3867M'},
                             70: {'dev': '/dev/bcache4', 'rss': '4041M'},
                             81: {'dev': '/dev/bcache1', 'rss': '4065M'},
                             90: {'dev': '/dev/bcache2', 'rss': '4114M'},
                             101: {'dev': '/dev/bcache3', 'rss': '3965M'},
                             109: {'dev': '/dev/bcache5', 'rss': '3898M'}}}
        storage_01ceph.get_osd_info()
        self.assertEqual(storage_01ceph.CEPH_INFO, expected)


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


class TestStoragePlugin03ceph_daemon_logs(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(storage_03ceph_daemon_logs, "DAEMON_INFO", {})
    def test_get_daemon_log_info(self):
        result = {'osd-reported-failed': {'osd.41': {'2021-02-13': 23},
                                          'osd.85': {'2021-02-13': 4}}}
        storage_03ceph_daemon_logs.get_daemon_log_info()
        self.assertEqual(storage_03ceph_daemon_logs.DAEMON_INFO, result)
