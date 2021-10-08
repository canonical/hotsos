import json
import mock
import os
import tempfile
import utils

from core import checks
from core.issues import issue_types
from core.plugins.storage import (
    bcache as bcache_core,
    ceph as ceph_core,
)
from plugins.storage.pyparts import (
    bcache,
    ceph_daemon_checks,
    ceph_daemon_logs,
    ceph_general,
)

CEPH_CONF_NO_BLUESTORE = """
[global]
[osd]
osd objectstore = filestore
osd journal size = 1024
filestore xattr use omap = true
"""

CEPH_VERSIONS_MISMATCHED_MAJOR = """
{
    "mon": {
        "ceph version 15.2.13 (c44bc49e7a57a87d84dfff2a077a2058aa2172e2) octopus (stable)": 1
    },
    "mgr": {
        "ceph version 15.2.13 (c44bc49e7a57a87d84dfff2a077a2058aa2172e2) octopus (stable)": 1
    },
    "osd": {
        "ceph version 15.2.13 (c44bc49e7a57a87d84dfff2a077a2058aa2172e2) octopus (stable)": 2,
        "ceph version 14.2.18 (b77bc49e3a57a87d84df112a087a2058aa217118) nautilus (stable)": 1
    },
    "mds": {},
    "overall": {
        "ceph version 15.2.13 (c44bc49e7a57a87d84dfff2a077a2058aa2172e2) octopus (stable)": 5
    }
}
"""  # noqa


CEPH_VERSIONS_MISMATCHED_MINOR = """
{
    "mon": {
        "ceph version 15.2.11 (e3523634d9c2227df9af89a4eac33d16738c49cb) octopus (stable)": 3
    },
    "mgr": {
        "ceph version 15.2.11 (e3523634d9c2227df9af89a4eac33d16738c49cb) octopus (stable)": 3
    },
    "osd": {
        "ceph version 15.2.11 (e3523634d9c2227df9af89a4eac33d16738c49cb) octopus (stable)": 208,
        "ceph version 15.2.13 (c44bc49e7a57a87d84dfff2a077a2058aa2172e2) octopus (stable)": 16
    },
    "mds": {},
    "overall": {
        "ceph version 15.2.11 (e3523634d9c2227df9af89a4eac33d16738c49cb) octopus (stable)": 217,
        "ceph version 15.2.13 (c44bc49e7a57a87d84dfff2a077a2058aa2172e2) octopus (stable)": 16
    }
}
"""  # noqa


OSD_V2FAIL = """
max_osd 3
osd.0 up   in  weight 1 up_from 651 up_thru 658 down_at 650 last_clean_interval [635,645) [v1:10.0.0.49:6801/33943] [v1:10.0.0.49:6803/33943] exists,up 51f1b834-3c8f-4cd1-8c0a-81a6f75ba2ea
osd.1 up   in  weight 1 up_from 658 up_thru 658 down_at 652 last_clean_interval [638,645) [v1:10.0.0.48:6801/24136] [v1:10.0.0.48:6803/24136] exists,up 625f0760-586e-4032-bd89-c7fc5080ed05
osd.2 up   in  weight 1 up_from 655 up_thru 658 down_at 652 last_clean_interval [631,645) [v1:10.0.0.50:6801/31448] [v1:10.0.0.50:6803/31448] exists,up c42942cd-878c-43e7-afb3-2667f65a2e41
 """  # noqa

CEPH_OSD_CRUSH_DUMP = """
{
        "buckets": [
            {
                "id": -1,
                "name": "default",
                "type_id": 11,
                "type_name": "root",
                "weight": 1926,
                "alg": "straw2",
                "hash": "rjenkins1",
                "items": [
                    {
                        "id": -3,
                        "weight": 642,
                        "pos": 0
                    },
                    {
                        "id": -5,
                        "weight": 642,
                        "pos": 1
                    },
                    {
                        "id": -7,
                        "weight": 642,
                        "pos": 2
                    }
                ]
            },
            {
                "id": -3,
                "name": "juju-94442c-oct00-1",
                "type_id": 1,
                "type_name": "host",
                "weight": 642,
                "alg": "straw2",
                "hash": "rjenkins1",
                "items": [
                    {
                        "id": 1,
                        "weight": 642,
                        "pos": 0
                    }
                ]
            },
            {
                "id": -5,
                "name": "juju-94442c-oct00-3",
                "type_id": 1,
                "type_name": "host",
                "weight": 642,
                "alg": "straw2",
                "hash": "rjenkins1",
                "items": [
                    {
                        "id": 0,
                        "weight": 642,
                        "pos": 0
                    }
                ]
            },
            {
                "id": -7,
                "name": "juju-94442c-oct00-2",
                "type_id": 3,
                "type_name": "rack00",
                "weight": 642,
                "alg": "straw2",
                "hash": "rjenkins1",
                "items": [
                    {
                        "id": 2,
                        "weight": 642,
                        "pos": 0
                    }
                ]
            }
        ]
    }
"""


class StorageTestsBase(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        os.environ['PLUGIN_NAME'] = 'storage'


class TestStorageCephChecksBase(StorageTestsBase):

    def test_release_name(self):
        release_name = ceph_core.CephChecksBase().release_name
        self.assertEqual(release_name, 'octopus')

    def test_bluestore_enabled(self):
        enabled = ceph_core.CephChecksBase().bluestore_enabled
        self.assertTrue(enabled)

    def test_bluestore_not_enabled(self):
        with tempfile.TemporaryDirectory() as dtmp:
            path = os.path.join(dtmp, 'etc/ceph')
            os.makedirs(path)
            with open(os.path.join(path, 'ceph.conf'), 'w') as fd:
                fd.write(CEPH_CONF_NO_BLUESTORE)

            os.environ['DATA_ROOT'] = dtmp
            enabled = ceph_core.CephChecksBase().bluestore_enabled
            self.assertFalse(enabled)


class TestStorageCephDaemons(StorageTestsBase):

    def test_osd_versions(self):
        versions = ceph_core.CephOSD(1, 1234, '/dev/foo').versions
        self.assertEqual(versions, {'15.2.13': 3})

    def test_mon_versions(self):
        versions = ceph_core.CephMon().versions
        self.assertEqual(versions, {'15.2.13': 1})

    def test_mds_versions(self):
        versions = ceph_core.CephMDS().versions
        self.assertEqual(versions, {})

    def test_rgw_versions(self):
        versions = ceph_core.CephRGW().versions
        self.assertEqual(versions, {})

    def test_osd_release_name(self):
        release_names = ceph_core.CephOSD(1, 1234, '/dev/foo').release_names
        self.assertEqual(release_names, {'octopus': 3})

    def test_mon_release_name(self):
        release_names = ceph_core.CephMon().release_names
        self.assertEqual(release_names, {'octopus': 1})

    def test_mon_dump(self):
        dump = ceph_core.CephMon().mon_dump
        self.assertEqual(dump['min_mon_release'], '15 (octopus)')

    def test_osd_dump(self):
        dump = ceph_core.CephOSD(1, 1234, '/dev/foo').osd_dump
        self.assertEqual(dump['require_osd_release'], 'octopus')


class TestStoragePluginPartCephGeneral(StorageTestsBase):

    def test_get_service_info(self):
        expected = {'ceph': {
                        'network': {
                            'cluster': {
                                'br-ens3': {
                                    'addresses': ['10.0.0.49'],
                                    'hwaddr': '52:54:00:e2:28:a3',
                                    'state': 'UP'}},
                            'public': {
                                'br-ens3': {
                                    'addresses': ['10.0.0.49'],
                                    'hwaddr': '52:54:00:e2:28:a3',
                                    'state': 'UP'}}
                            },
                        'services': [
                            'ceph-crash (1)', 'ceph-osd (1)'],
                        'release': 'octopus',
                    }}
        inst = ceph_general.CephServiceChecks()
        inst()
        self.assertEqual(inst.output, expected)

    @mock.patch.object(checks, 'CLIHelper')
    def test_get_service_info_unavailable(self, mock_helper):
        expected = {'ceph': {
                        'network': {
                            'cluster': {
                                'br-ens3': {
                                    'addresses': ['10.0.0.49'],
                                    'hwaddr': '52:54:00:e2:28:a3',
                                    'state': 'UP'}},
                            'public': {
                                'br-ens3': {
                                    'addresses': ['10.0.0.49'],
                                    'hwaddr': '52:54:00:e2:28:a3',
                                    'state': 'UP'}}
                            },
                        'release': 'unknown'}}

        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.ps.return_value = []
        mock_helper.return_value.dpkg_l.return_value = []
        inst = ceph_general.CephServiceChecks()
        inst()
        self.assertEqual(inst.output, expected)

    def test_get_package_info(self):
        inst = ceph_general.CephPackageChecks()
        inst()
        expected = ['ceph 15.2.13-0ubuntu0.20.04.1',
                    'ceph-base 15.2.13-0ubuntu0.20.04.1',
                    'ceph-common 15.2.13-0ubuntu0.20.04.1',
                    'ceph-mds 15.2.13-0ubuntu0.20.04.1',
                    'ceph-mgr 15.2.13-0ubuntu0.20.04.1',
                    'ceph-mgr-modules-core 15.2.13-0ubuntu0.20.04.1',
                    'ceph-mon 15.2.13-0ubuntu0.20.04.1',
                    'ceph-osd 15.2.13-0ubuntu0.20.04.1',
                    'python3-ceph-argparse 15.2.13-0ubuntu0.20.04.1',
                    'python3-ceph-common 15.2.13-0ubuntu0.20.04.1',
                    'python3-cephfs 15.2.13-0ubuntu0.20.04.1',
                    'python3-rados 15.2.13-0ubuntu0.20.04.1',
                    'python3-rbd 15.2.13-0ubuntu0.20.04.1',
                    'radosgw 15.2.13-0ubuntu0.20.04.1']
        self.assertEquals(inst.output["ceph"]["dpkg"], expected)

    def test_ceph_base_interfaces(self):
        expected = {'cluster': {'br-ens3': {'addresses': ['10.0.0.49'],
                                            'hwaddr': '52:54:00:e2:28:a3',
                                            'state': 'UP'}},
                    'public': {'br-ens3': {'addresses': ['10.0.0.49'],
                                           'hwaddr': '52:54:00:e2:28:a3',
                                           'state': 'UP'}}}
        ports = ceph_core.CephChecksBase().bind_interfaces
        _ports = {}
        for config, port in ports.items():
            _ports.update({config: port.to_dict()})

        self.assertEqual(_ports, expected)


class TestStoragePluginPartCephDaemonChecks(StorageTestsBase):

    @mock.patch.object(ceph_daemon_checks, 'issue_utils')
    def test_get_crushmap_mixed_buckets(self, mock_issue_utils):
        with mock.patch.object(ceph_core, 'CLIHelper') as mock_helper:
            mock_helper.return_value = mock.MagicMock()
            mock_helper.return_value.ceph_osd_crush_dump_json_decoded.\
                return_value = json.loads(CEPH_OSD_CRUSH_DUMP)
            inst = ceph_daemon_checks.CephOSDChecks()
            inst.get_crushmap_mixed_buckets()
            self.assertTrue(mock_issue_utils.add_issue.called)

    @mock.patch.object(ceph_daemon_checks, 'issue_utils')
    def test_get_crushmap_no_mixed_buckets(self, mock_issue_utils):
        inst = ceph_daemon_checks.CephOSDChecks()
        inst.get_crushmap_mixed_buckets()
        self.assertFalse(mock_issue_utils.add_issue.called)

    def test_get_ceph_versions_mismatch_pass(self):
        result = {'mgr': ['15.2.13'],
                  'mon': ['15.2.13'],
                  'osd': ['15.2.13']}
        inst = ceph_daemon_checks.CephOSDChecks()
        inst.get_ceph_versions_mismatch()
        self.assertEqual(inst.output["ceph"]["versions"], result)

    def test_get_ceph_versions_mismatch_fail(self):
        result = {'mgr': ['15.2.11'],
                  'mon': ['15.2.11'],
                  'osd': ['15.2.11',
                          '15.2.13']}
        with mock.patch.object(ceph_core, 'CLIHelper') as mock_helper:
            mock_helper.return_value = mock.MagicMock()
            mock_helper.return_value.ceph_versions.return_value = \
                CEPH_VERSIONS_MISMATCHED_MINOR.split('\n')
            inst = ceph_daemon_checks.CephOSDChecks()
            inst.get_ceph_versions_mismatch()
            self.assertEqual(inst.output["ceph"]["versions"], result)

    @mock.patch.object(ceph_daemon_checks.issue_utils, "add_issue")
    def test_get_ceph_mon_lower_version(self, mock_add_issue):
        issues = []

        def fake_add_issue(issue):
            issues.append(issue)

        mock_add_issue.side_effect = fake_add_issue
        with mock.patch.object(ceph_core, 'CLIHelper') as mock_helper:
            mock_helper.return_value = mock.MagicMock()
            mock_helper.return_value.ceph_versions.return_value = \
                CEPH_VERSIONS_MISMATCHED_MINOR.split('\n')
            inst = ceph_daemon_checks.CephOSDChecks()
            inst.get_ceph_versions_mismatch()

        types = {}
        for issue in issues:
            t = type(issue)
            if t in types:
                types[t] += 1
            else:
                types[t] = 1

        self.assertEqual(types[issue_types.CephDaemonVersionsError], 1)
        self.assertTrue(mock_add_issue.called)

    @mock.patch.object(ceph_core, 'CLIHelper')
    def test_get_ceph_versions_mismatch_unavailable(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.ceph_versions.return_value = []
        inst = ceph_daemon_checks.CephOSDChecks()
        inst.get_ceph_versions_mismatch()
        self.assertIsNone(inst.output)

    @mock.patch.object(ceph_daemon_checks, 'issue_utils')
    def test_check_require_osd_release(self, mock_issue_utils):
        osd_dump = ceph_core.CLIHelper().ceph_osd_dump()
        with mock.patch.object(ceph_core, 'CLIHelper') as mock_helper:
            mock_helper.return_value = mock.MagicMock()
            mock_helper.return_value.ceph_versions.return_value = \
                CEPH_VERSIONS_MISMATCHED_MAJOR.split('\n')
            mock_helper.return_value.ceph_osd_dump.return_value = osd_dump
            inst = ceph_daemon_checks.CephOSDChecks()
            inst.check_require_osd_release()
            self.assertTrue(mock_issue_utils.add_issue.called)

    @mock.patch.object(ceph_daemon_checks, 'issue_utils')
    def test_check_osd_v2(self, mock_issue_utils):
        with mock.patch.object(ceph_core, 'CLIHelper') as mock_helper:
            mock_helper.return_value = mock.MagicMock()
            mock_helper.return_value.ceph_osd_dump.return_value = \
                OSD_V2FAIL.split('\n')
            inst = ceph_daemon_checks.CephOSDChecks()
            inst.check_osd_msgr_protocol_versions()
            self.assertTrue(mock_issue_utils.add_issue.called)

    @mock.patch.object(ceph_daemon_checks, 'issue_utils')
    def test_check_osdmaps_size(self, mock_issue_utils):
        ceph_report = ceph_core.CLIHelper().ceph_report_json_decoded()
        with mock.patch.object(ceph_core, 'CLIHelper') as mock_helper:
            mock_helper.return_value = mock.MagicMock()
            mock_helper.return_value.ceph_report_json_decoded.return_value = \
                ceph_report
            inst = ceph_daemon_checks.CephOSDChecks()
            inst.check_osdmaps_size()
            self.assertTrue(mock_issue_utils.add_issue.called)

    @mock.patch.object(ceph_daemon_checks, 'issue_utils')
    def test_check_ceph_bluefs_size(self, mock_issue_utils):
        inst = ceph_daemon_checks.CephOSDChecks()
        inst.check_ceph_bluefs_size()
        self.assertTrue(mock_issue_utils.add_issue.called)

    @mock.patch.object(ceph_daemon_checks.issue_utils, "add_issue")
    def test_get_ceph_pg_imbalance(self, mock_add_issue):
        issues = []

        def fake_add_issue(issue):
            issues.append(issue)

        mock_add_issue.side_effect = fake_add_issue
        result = {'osd-pgs-suboptimal': {
                   'osd.0': 295,
                   'osd.1': 501},
                  'osd-pgs-near-limit': {
                      'osd.1': 501}
                  }
        inst = ceph_daemon_checks.CephOSDChecks()
        inst.get_ceph_pg_imbalance()
        self.assertEqual(inst.output["ceph"], result)

        types = {}
        for issue in issues:
            t = type(issue)
            if t in types:
                types[t] += 1
            else:
                types[t] = 1

        self.assertEqual(len(issues), 2)
        self.assertEqual(types[issue_types.CephCrushError], 1)
        self.assertEqual(types[issue_types.CephCrushWarning], 1)
        self.assertTrue(mock_add_issue.called)

    def test_get_osd_ids(self):
        inst = ceph_daemon_checks.CephOSDChecks()
        inst()
        self.assertEqual([osd.id for osd in inst.local_osds], [0])

    def test_get_cluster_osd_ids(self):
        inst = ceph_daemon_checks.CephOSDChecks()
        inst()
        self.assertEqual([osd.id for osd in inst.cluster_osds], [0, 1, 2])

    @mock.patch.object(ceph_core, 'CLIHelper')
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
                    'devtype': 'ssd',
                    'fsid': fsid,
                    'rss': '639M'}}
        inst = ceph_daemon_checks.CephOSDChecks()
        inst()
        self.assertEqual(inst.output["ceph"]["local-osds"], expected)

    @mock.patch.object(ceph_daemon_checks, 'KernelChecksBase')
    @mock.patch.object(ceph_daemon_checks.bcache, 'BcacheChecksBase')
    @mock.patch.object(ceph_daemon_checks.issue_utils, "add_issue")
    def test_check_bcache_vulnerabilities(self, mock_add_issue, mock_bcb,
                                          mock_kcb):
        mock_kcb.return_value = mock.MagicMock()
        mock_kcb.return_value.version = '5.3'
        mock_cset = mock.MagicMock()
        mock_cset.get.return_value = 60
        mock_bcb.get_sysfs_cachesets.return_value = mock_cset
        inst = ceph_daemon_checks.CephOSDChecks()
        with mock.patch.object(inst, 'is_bcache_device') as mock_ibd:
            mock_ibd.return_value = True
            with mock.patch.object(inst, 'apt_check') as mock_apt_check:
                mock_apt_check.get_version.return_value = "15.2.13"
                inst.check_bcache_vulnerabilities()
                self.assertTrue(mock_add_issue.called)


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
    @mock.patch.object(bcache.issue_utils, "add_issue")
    def test_get_bcache_stats_checks_issue_found(self, mock_add_issue,
                                                 mock_add_known_bug):
        expected = {'bcache': {
                        'cachesets': [{
                            'cache_available_percent': 30,
                            'uuid': '123'}]
                        }
                    }
        with tempfile.TemporaryDirectory() as dtmp:
            with mock.patch.object(bcache_core.BcacheChecksBase,
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
