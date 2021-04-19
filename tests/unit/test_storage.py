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
        c = storage_01ceph.get_ceph_checker()
        self.assertEquals(c.get_date_secs(), 1234)

    @mock.patch.object(storage_01ceph.helpers, "get_date")
    def test_get_date_secs_from_timestamp(self, mock_get_date):
        mock_get_date.return_value = "1234\n"
        date_string = "Thu Mar 25 10:55:05 MDT 2021"
        c = storage_01ceph.get_ceph_checker()
        self.assertEquals(c.get_date_secs(date_string),
                          1616691305)

    @mock.patch.object(storage_01ceph.helpers, "get_date")
    def test_get_date_secs_from_timestamp_w_tz(self, mock_get_date):
        mock_get_date.return_value = "1234\n"
        date_string = "Thu Mar 25 10:55:05 UTC 2021"
        c = storage_01ceph.get_ceph_checker()
        self.assertEquals(c.get_date_secs(date_string),
                          1616669705)

    @mock.patch.object(storage_01ceph, "CEPH_INFO", {})
    def test_get_service_info(self):
        result = ['ceph-osd (6)', 'radosgw (1)', 'ceph-mgr (1)',
                  'ceph-mon (1)']
        storage_01ceph.get_ceph_checker()()
        self.assertEqual(storage_01ceph.CEPH_INFO["services"], result)

    @mock.patch.object(storage_01ceph.helpers, "get_ps",
                       lambda: [])
    @mock.patch.object(storage_01ceph, "CEPH_INFO", {})
    def test_get_service_info_unavailable(self):
        storage_01ceph.get_ceph_checker()()
        self.assertFalse("services" in storage_01ceph.CEPH_INFO)

    @mock.patch.object(storage_01ceph, "CEPH_INFO", {})
    def test_get_ceph_versions_mismatch(self):
        result = {'mgr': ['14.2.11'],
                  'mon': ['14.2.11'],
                  'osd': ['14.2.11'],
                  'rgw': ['14.2.11']}
        storage_01ceph.get_ceph_checker()()
        self.assertEqual(storage_01ceph.CEPH_INFO["versions"], result)

    @mock.patch.object(storage_01ceph.helpers, "get_ceph_versions",
                       lambda: [])
    @mock.patch.object(storage_01ceph, "CEPH_INFO", {})
    def test_get_ceph_versions_mismatch_unavailable(self):
        storage_01ceph.get_ceph_checker()()
        self.assertFalse("versions" in storage_01ceph.CEPH_INFO)

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
        c = storage_01ceph.get_ceph_checker()
        c.get_ceph_pg_imbalance()
        self.assertEqual(storage_01ceph.CEPH_INFO, result)

    @mock.patch.object(storage_01ceph, "CEPH_INFO", {})
    def test_get_osd_ids(self):
        c = storage_01ceph.get_ceph_checker()
        c()
        self.assertEqual(c.osd_ids, [63, 81, 90, 109, 101, 70])

    @mock.patch.object(storage_01ceph.helpers, "get_ceph_osd_df_tree",
                       lambda: [])
    @mock.patch.object(storage_01ceph, "CEPH_INFO", {})
    def test_get_ceph_pg_imbalance_unavailable(self):
        c = storage_01ceph.get_ceph_checker()
        c.get_ceph_pg_imbalance()
        self.assertEqual(storage_01ceph.CEPH_INFO, {})

    @mock.patch.object(storage_01ceph, "CEPH_INFO", {})
    def test_get_osd_info(self):
        expected = {63: {'fsid': 'b3885ec9-4d42-4860-a708-d1cbc6e4da29',
                         'dev': '/dev/bcache0', 'rss': '3867M'},
                    70: {'fsid': '12a94d95-fbcc-4c15-875f-aae53274b1a9',
                         'dev': '/dev/bcache4', 'rss': '4041M'},
                    81: {'fsid': 'bd7a98b9-d765-4d7c-b11e-1a430c3a27cb',
                         'dev': '/dev/bcache1', 'rss': '4065M'},
                    90: {'fsid': 'c4539810-2a63-4885-918b-0d23bcd41cf1',
                         'dev': '/dev/bcache2', 'rss': '4114M'},
                    101: {'fsid': '5f74e4b6-7e76-4c11-9533-c393fc9fdebc',
                          'dev': '/dev/bcache3', 'rss': '3965M'},
                    109: {'fsid': '9653fae9-d518-4fe8-abf9-54d015ffea68',
                          'dev': '/dev/bcache5', 'rss': '3898M'}}
        storage_01ceph.get_ceph_checker()()
        self.assertEqual(storage_01ceph.CEPH_INFO["osds"], expected)


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
                                          'osd.85': {'2021-02-13': 4}},
                  'crc-err-bluestore': {'2021-04-01': 2},
                  'crc-err-rocksdb': {'block checksum mismatch': 1}}
        storage_03ceph_daemon_logs.get_daemon_log_info()
        self.assertEqual(storage_03ceph_daemon_logs.DAEMON_INFO, result)
