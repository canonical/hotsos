import mock

import utils

from plugins.storage import (
    _01ceph,
    _02bcache,
    _03ceph_daemon_logs,
)


class TestStoragePlugin01ceph(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(_01ceph.helpers, "get_date")
    def test_get_date_secs(self, mock_get_date):
        mock_get_date.return_value = "1234\n"
        c = _01ceph.get_ceph_checker()
        self.assertEquals(c.get_date_secs(), 1234)

    @mock.patch.object(_01ceph.helpers, "get_date")
    def test_get_date_secs_from_timestamp(self, mock_get_date):
        mock_get_date.return_value = "1234\n"
        date_string = "Thu Mar 25 10:55:05 MDT 2021"
        c = _01ceph.get_ceph_checker()
        self.assertEquals(c.get_date_secs(date_string),
                          1616691305)

    @mock.patch.object(_01ceph.helpers, "get_date")
    def test_get_date_secs_from_timestamp_w_tz(self, mock_get_date):
        mock_get_date.return_value = "1234\n"
        date_string = "Thu Mar 25 10:55:05 UTC 2021"
        c = _01ceph.get_ceph_checker()
        self.assertEquals(c.get_date_secs(date_string),
                          1616669705)

    @mock.patch.object(_01ceph, "CEPH_INFO", {})
    def test_get_service_info(self):
        result = ['ceph-mgr (1)', 'ceph-mon (1)', 'ceph-osd (6)',
                  'radosgw (1)']
        _01ceph.get_ceph_checker()()
        self.assertEqual(_01ceph.CEPH_INFO["services"], result)

    @mock.patch.object(_01ceph.helpers, "get_ps",
                       lambda: [])
    @mock.patch.object(_01ceph, "CEPH_INFO", {})
    def test_get_service_info_unavailable(self):
        _01ceph.get_ceph_checker()()
        self.assertFalse("services" in _01ceph.CEPH_INFO)

    @mock.patch.object(_01ceph, "CEPH_INFO", {})
    def test_get_crushmap_mixed_buckets(self):
        _01ceph.get_ceph_checker()()
        result = ['default', 'default~ssd']
        self.assertEqual(_01ceph.CEPH_INFO["mixed_crush_buckets"], result)

    @mock.patch.object(_01ceph, "CEPH_INFO", {})
    def test_get_ceph_versions_mismatch(self):
        result = {'mgr': ['14.2.11'],
                  'mon': ['14.2.11'],
                  'osd': ['14.2.11'],
                  'rgw': ['14.2.11']}
        _01ceph.get_ceph_checker()()
        self.assertEqual(_01ceph.CEPH_INFO["versions"], result)

    @mock.patch.object(_01ceph.helpers, "get_ceph_versions",
                       lambda: [])
    @mock.patch.object(_01ceph, "CEPH_INFO", {})
    def test_get_ceph_versions_mismatch_unavailable(self):
        _01ceph.get_ceph_checker()()
        self.assertFalse("versions" in _01ceph.CEPH_INFO)

    @mock.patch.object(_01ceph, "CEPH_INFO", {})
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
        c = _01ceph.get_ceph_checker()
        c.get_ceph_pg_imbalance()
        self.assertEqual(_01ceph.CEPH_INFO, result)

    @mock.patch.object(_01ceph, "CEPH_INFO", {})
    def test_get_osd_ids(self):
        c = _01ceph.get_ceph_checker()
        c()
        self.assertEqual(c.osd_ids, [63, 81, 90, 109, 101, 70])

    @mock.patch.object(_01ceph.helpers, "get_ceph_osd_df_tree",
                       lambda: [])
    @mock.patch.object(_01ceph, "CEPH_INFO", {})
    def test_get_ceph_pg_imbalance_unavailable(self):
        c = _01ceph.get_ceph_checker()
        c.get_ceph_pg_imbalance()
        self.assertEqual(_01ceph.CEPH_INFO, {})

    @mock.patch.object(_01ceph, "CEPH_INFO", {})
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
        _01ceph.get_ceph_checker()()
        self.assertEqual(_01ceph.CEPH_INFO["osds"], expected)


class TestStoragePlugin02bcache(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(_02bcache, "BCACHE_INFO", {})
    def test_get_bcache_info(self):
        result = {'bcache': {'bcache0': {'dname': 'bcache1'},
                             'bcache1': {'dname': 'bcache3'},
                             'bcache2': {'dname': 'bcache4'},
                             'bcache3': {'dname': 'bcache5'},
                             'bcache4': {'dname': 'bcache2'},
                             'bcache5': {'dname': 'bcache6'},
                             'bcache6': {'dname': 'bcache0'}},
                  'nvme': {'nvme0n1': {'dname': 'nvme0n1'}}}
        _02bcache.get_bcache_info()
        self.assertEqual(_02bcache.BCACHE_INFO, result)


class TestStoragePlugin03ceph_daemon_logs(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(_03ceph_daemon_logs, "DAEMON_INFO", {})
    def test_get_daemon_log_info(self):
        result = {'osd-reported-failed': {'osd.41': {'2021-02-13': 23},
                                          'osd.85': {'2021-02-13': 4}},
                  'crc-err-bluestore': {'2021-04-01': 2},
                  'crc-err-rocksdb': {'block checksum mismatch': 1}}
        _03ceph_daemon_logs.get_daemon_log_info()
        self.assertEqual(_03ceph_daemon_logs.DAEMON_INFO, result)
