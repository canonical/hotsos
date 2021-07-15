import os

import mock
import tempfile

import utils

from plugins.storage.pyparts import (
    bcache,
    ceph_daemon_checks,
    ceph_daemon_logs,
    ceph_general,
)


class TestStoragePluginPartCephGeneral(utils.BaseTestCase):

    def test_get_service_info(self):
        result = ['ceph-mgr (1)', 'ceph-mon (1)', 'ceph-osd (6)',
                  'radosgw (1)']
        inst = ceph_general.get_service_checker()
        inst()
        self.assertEqual(inst.output["ceph"]["services"], result)

    @mock.patch.object(ceph_general.CephChecksBase, "__call__",
                       lambda *args: None)
    def test_get_service_info_unavailable(self):
        inst = ceph_general.get_service_checker()
        inst()
        self.assertIsNone(inst.output)

    def test_get_package_info(self):
        inst = ceph_general.get_pkg_checker()
        inst()
        expected = ['ceph-base 12.2.13-0ubuntu0.18.04.6~cloud0',
                    'ceph-common 12.2.13-0ubuntu0.18.04.6~cloud0',
                    'ceph-mgr 12.2.13-0ubuntu0.18.04.6~cloud0',
                    'ceph-mon 12.2.13-0ubuntu0.18.04.6~cloud0',
                    'ceph-osd 12.2.13-0ubuntu0.18.04.6~cloud0',
                    'python-rbd 12.2.13-0ubuntu0.18.04.6~cloud0',
                    'radosgw 12.2.13-0ubuntu0.18.04.6~cloud0']
        self.assertEquals(inst.output["ceph"]["dpkg"], expected)


class TestStoragePluginPartCephDaemonChecks(utils.BaseTestCase):

    @mock.patch.object(ceph_daemon_checks.cli_helpers, "get_date")
    def test_get_date_secs(self, mock_get_date):
        mock_get_date.return_value = "1234\n"
        c = ceph_daemon_checks.get_osd_checker()
        self.assertEquals(c.get_date_secs(), 1234)

    @mock.patch.object(ceph_daemon_checks.cli_helpers, "get_date")
    def test_get_date_secs_from_timestamp(self, mock_get_date):
        mock_get_date.return_value = "1234\n"
        date_string = "Thu Mar 25 10:55:05 MDT 2021"
        c = ceph_daemon_checks.get_osd_checker()
        self.assertEquals(c.get_date_secs(date_string),
                          1616691305)

    @mock.patch.object(ceph_daemon_checks.cli_helpers, "get_date")
    def test_get_date_secs_from_timestamp_w_tz(self, mock_get_date):
        mock_get_date.return_value = "1234\n"
        date_string = "Thu Mar 25 10:55:05 UTC 2021"
        c = ceph_daemon_checks.get_osd_checker()
        self.assertEquals(c.get_date_secs(date_string),
                          1616669705)

    @mock.patch.object(ceph_daemon_checks, "add_issue")
    def test_get_crushmap_mixed_buckets(self, mock_add_issue):
        inst = ceph_daemon_checks.get_osd_checker()
        inst()
        result = ['default', 'default~ssd']
        self.assertEqual(inst.output["ceph"]["mixed_crush_buckets"], result)
        self.assertTrue(mock_add_issue.called)

    def test_get_ceph_versions_mismatch(self):
        result = {'mgr': ['14.2.11'],
                  'mon': ['14.2.11'],
                  'osd': ['14.2.11'],
                  'rgw': ['14.2.11']}
        inst = ceph_daemon_checks.get_osd_checker()
        inst()
        self.assertEqual(inst.output["ceph"]["versions"], result)

    @mock.patch.object(ceph_daemon_checks.cli_helpers, "get_ceph_versions",
                       lambda: [])
    def test_get_ceph_versions_mismatch_unavailable(self):
        inst = ceph_daemon_checks.get_osd_checker()
        inst()
        self.assertFalse("versions" in inst.output["ceph"])

    @mock.patch.object(ceph_daemon_checks, "add_issue")
    def test_get_ceph_pg_imbalance(self, mock_add_issue):
        result = {'bad-pgs-per-osd': {
                   'osd.0': 295,
                   'osd.1': 150,
                   'osd.15': 49,
                   'osd.16': 316,
                   'osd.17': 370,
                   'osd.2': 127,
                   'osd.34': 392,
                   'osd.36': 0,
                   'osd.37': 406,
                   'osd.60': 140}}
        inst = ceph_daemon_checks.get_osd_checker()
        inst.get_ceph_pg_imbalance()
        self.assertEqual(inst.output["ceph"], result)
        self.assertTrue(mock_add_issue.called)

    def test_get_osd_ids(self):
        inst = ceph_daemon_checks.get_osd_checker()
        inst()
        self.assertEqual(inst.osd_ids, [63, 81, 90, 109, 101, 70])

    @mock.patch.object(ceph_daemon_checks.cli_helpers, "get_ceph_osd_df_tree",
                       lambda: [])
    def test_get_ceph_pg_imbalance_unavailable(self):
        inst = ceph_daemon_checks.get_osd_checker()
        inst.get_ceph_pg_imbalance()
        self.assertEqual(inst.output, None)

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
        inst = ceph_daemon_checks.get_osd_checker()
        inst()
        self.assertEqual(inst.output["ceph"]["osds"], expected)


class TestStoragePluginPartBcache(utils.BaseTestCase):

    def test_get_bcache_dev_info(self):
        result = {'bcache': {
                    'devices': {
                        'bcache': {'bcache0': {'dname': 'bcache1'},
                                   'bcache1': {'dname': 'bcache3'},
                                   'bcache2': {'dname': 'bcache4'},
                                   'bcache3': {'dname': 'bcache5'},
                                   'bcache4': {'dname': 'bcache2'},
                                   'bcache5': {'dname': 'bcache6'},
                                   'bcache6': {'dname': 'bcache0'}},
                        'nvme': {'nvme0n1': {'dname': 'nvme0n1'}}
                        }}}

        inst = bcache.BcacheDeviceChecks()
        inst()
        self.assertEqual(inst.output, result)

    def test_get_bcache_stats_checks(self):
        self.maxDiff = None
        expected = {'bcache': {
                        'cachsets': [{
                            'cache_available_percent': 95,
                            'uuid': '2bb274af-a015-4496-9455-43393ea06aa2'}]
                        }
                    }
        inst = bcache.BcacheStatsChecks()
        inst()
        self.assertEqual(inst.output, expected)

    @mock.patch.object(bcache, "add_known_bug")
    @mock.patch.object(bcache, "add_issue")
    def test_get_bcache_stats_checks_issue_found(self, mock_add_issue,
                                                 mock_add_known_bug):
        expected = {'bcache': {
                        'cachsets': [{
                            'cache_available_percent': 30,
                            'uuid': '123'}]
                        }
                    }
        with tempfile.TemporaryDirectory() as dtmp:
            with mock.patch.object(bcache.BcacheChecksBase,
                                   "get_sysfs_cachesets",
                                   lambda *args: [
                                       {"uuid": "123",
                                        "cache_available_percent": 30}]):
                path = os.path.join(dtmp, "cache_available_percent")
                with open(path, 'w') as fd:
                    fd.write("30\n")

                inst = bcache.BcacheStatsChecks()
                inst()
                self.assertEqual(inst.output, expected)
                self.assertTrue(mock_add_issue.called)
                mock_add_known_bug.assert_has_calls([
                    mock.call(1900438, 'see BcacheWarning for info')])


class TestStoragePluginPartCeph_daemon_logs(utils.BaseTestCase):

    def test_get_ceph_daemon_log_checker(self):
        result = {'osd-reported-failed': {'osd.41': {'2021-02-13': 23},
                                          'osd.85': {'2021-02-13': 4}},
                  'crc-err-bluestore': {'2021-02-12': 5, '2021-02-13': 1,
                                        '2021-04-01': 2},
                  'crc-err-rocksdb': {'2021-02-12': 7},
                  'long-heartbeat-pings': {'2021-02-09': 42},
                  'heartbeat-no-reply': {'2021-02-09': {'osd.0': 1,
                                                        'osd.1': 2}}}
        inst = ceph_daemon_logs.get_ceph_daemon_log_checker()
        inst()
        self.assertEqual(inst.output["ceph"], result)
