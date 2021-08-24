import os

import mock
import tempfile

import utils

from common import checks
from common.plugins.storage import CephChecksBase
from plugins.storage.pyparts import (
    bcache,
    ceph_daemon_checks,
    ceph_daemon_logs,
    ceph_general,
)


class StorageTestsBase(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        os.environ['PLUGIN_NAME'] = 'storage'


class TestStoragePluginPartCephGeneral(StorageTestsBase):

    def test_get_service_info(self):
        result = ['ceph-crash (1)', 'ceph-osd (1)']
        inst = ceph_general.CephServiceChecks()
        inst()
        self.assertEqual(inst.output["ceph"]["services"], result)

    @mock.patch.object(checks, 'CLIHelper')
    def test_get_service_info_unavailable(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.ps.return_value = []
        inst = ceph_general.CephServiceChecks()
        inst()
        self.assertIsNone(inst.output)

    def test_get_package_info(self):
        inst = ceph_general.CephPackageChecks()
        inst()
        expected = ['ceph-base 15.2.13-0ubuntu0.20.04.1',
                    'ceph-common 15.2.13-0ubuntu0.20.04.1',
                    'ceph-mds 15.2.13-0ubuntu0.20.04.1',
                    'ceph-mgr 15.2.13-0ubuntu0.20.04.1',
                    'ceph-mgr-modules-core 15.2.13-0ubuntu0.20.04.1',
                    'ceph-mon 15.2.13-0ubuntu0.20.04.1',
                    'ceph-osd 15.2.13-0ubuntu0.20.04.1',
                    'python3-ceph-argparse 15.2.13-0ubuntu0.20.04.1',
                    'python3-ceph-common 15.2.13-0ubuntu0.20.04.1',
                    'python3-rbd 15.2.13-0ubuntu0.20.04.1',
                    'radosgw 15.2.13-0ubuntu0.20.04.1']
        self.assertEquals(inst.output["ceph"]["dpkg"], expected)

    def test_ceph_base_interfaces(self):
        expected = {'br-ens3': {'addresses': ['10.0.0.49'],
                                'hwaddr': '52:54:00:e2:28:a3'}}
        self.assertEqual(CephChecksBase().bind_interfaces, expected)


class TestStoragePluginPartCephDaemonChecks(StorageTestsBase):

    @mock.patch.object(ceph_daemon_checks, 'CLIHelper')
    def test_get_date_secs(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_date = mock.MagicMock()
        mock_helper.return_value.date = mock_date
        mock_date.return_value = "1234\n"
        c = ceph_daemon_checks.CephOSDChecks()
        self.assertEquals(c.get_date_secs(), 1234)

    @mock.patch.object(ceph_daemon_checks, 'CLIHelper')
    def test_get_date_secs_from_timestamp(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_date = mock.MagicMock()
        mock_helper.return_value.date = mock_date
        mock_date.return_value = "1234\n"
        date_string = "Thu Mar 25 10:55:05 MDT 2021"
        c = ceph_daemon_checks.CephOSDChecks()
        self.assertEquals(c.get_date_secs(date_string),
                          1616691305)

    @mock.patch.object(ceph_daemon_checks, 'CLIHelper')
    def test_get_date_secs_from_timestamp_w_tz(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_date = mock.MagicMock()
        mock_helper.return_value.date = mock_date
        mock_date.return_value = "1234\n"
        date_string = "Thu Mar 25 10:55:05 UTC 2021"
        c = ceph_daemon_checks.CephOSDChecks()
        self.assertEquals(c.get_date_secs(date_string),
                          1616669705)

    @mock.patch.object(ceph_daemon_checks, "add_issue")
    def test_get_crushmap_mixed_buckets(self, mock_add_issue):
        inst = ceph_daemon_checks.CephOSDChecks()
        inst()
        result = ['default', 'default~ssd']
        self.assertEqual(inst.output["ceph"]["mixed_crush_buckets"], result)
        self.assertTrue(mock_add_issue.called)

    def test_get_ceph_versions_mismatch(self):
        result = {'mgr': ['14.2.11'],
                  'mon': ['14.2.11'],
                  'osd': ['14.2.11'],
                  'rgw': ['14.2.11']}
        inst = ceph_daemon_checks.CephOSDChecks()
        inst.get_ceph_versions_mismatch()
        self.assertEqual(inst.output["ceph"]["versions"], result)

    @mock.patch.object(ceph_daemon_checks, 'CLIHelper')
    def test_get_ceph_versions_mismatch_unavailable(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.ceph_versions.return_value = []
        inst = ceph_daemon_checks.CephOSDChecks()
        inst.get_ceph_versions_mismatch()
        self.assertIsNone(inst.output)

    @mock.patch.object(ceph_daemon_checks, "add_issue")
    def test_get_ceph_pg_imbalance(self, mock_add_issue):
        result = {'bad-pgs-per-osd': {
                   'osd.0': 295}}
        inst = ceph_daemon_checks.CephOSDChecks()
        inst.get_ceph_pg_imbalance()
        self.assertEqual(inst.output["ceph"], result)
        self.assertTrue(mock_add_issue.called)

    def test_get_osd_ids(self):
        inst = ceph_daemon_checks.CephOSDChecks()
        inst()
        self.assertEqual(inst.osd_ids, [0])

    @mock.patch.object(ceph_daemon_checks, 'CLIHelper')
    def test_get_ceph_pg_imbalance_unavailable(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.ceph_osd_df_tree.return_value = []
        inst = ceph_daemon_checks.CephOSDChecks()
        inst.get_ceph_pg_imbalance()
        self.assertEqual(inst.output, None)

    def test_get_osd_info(self):
        fsid = "51f1b834-3c8f-4cd1-8c0a-81a6f75ba2ea"
        expected = {0: {
                    'dev': '/dev/mapper/crypt-{}'.format(fsid),
                    'fsid': fsid,
                    'rss': '639M'}}
        inst = ceph_daemon_checks.CephOSDChecks()
        inst()
        self.assertEqual(inst.output["ceph"]["osds"], expected)


class TestStoragePluginPartBcache(StorageTestsBase):

    def test_get_bcache_dev_info(self):
        result = {'bcache': {
                    'devices': {
                        'bcache': {'bcache0': {'dname': 'bcache1'},
                                   'bcache1': {'dname': 'bcache0'}}
                        }}}

        inst = bcache.BcacheDeviceChecks()
        inst()
        self.assertEqual(inst.output, result)

    def test_get_bcache_stats_checks(self):
        self.maxDiff = None
        expected = {'bcache': {
                        'cachesets': [{
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
                        'cachesets': [{
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


class TestStoragePluginPartCeph_daemon_logs(StorageTestsBase):

    def test_get_ceph_daemon_log_checker(self):
        result = {'osd-reported-failed': {'osd.41': {'2021-02-13': 23},
                                          'osd.85': {'2021-02-13': 4}},
                  'crc-err-bluestore': {'2021-02-12': 5, '2021-02-13': 1,
                                        '2021-04-01': 2},
                  'crc-err-rocksdb': {'2021-02-12': 7},
                  'long-heartbeat-pings': {'2021-02-09': 42},
                  'heartbeat-no-reply': {'2021-02-09': {'osd.0': 1,
                                                        'osd.1': 2}}}
        inst = ceph_daemon_logs.CephDaemonLogChecks()
        inst()
        self.assertEqual(inst.output["ceph"], result)
