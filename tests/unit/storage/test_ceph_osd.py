import os
import tempfile

import mock

from tests.unit import utils

from core import checks
from core import known_bugs_utils
from core.ycheck.bugs import YBugChecker
from core.ycheck.configs import YConfigChecker
from core.plugins.storage import (
    ceph as ceph_core,
)
from plugins.storage.pyparts import (
    ceph_summary,
    ceph_event_checks,
)

CEPH_CONF_NO_BLUESTORE = """
[global]
[osd]
osd objectstore = filestore
osd journal size = 1024
filestore xattr use omap = true
"""


class StorageCephOSDTestsBase(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        os.environ['PLUGIN_NAME'] = 'storage'


class TestOSDCephChecksBase(StorageCephOSDTestsBase):

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

    def test_daemon_osd_config(self):
        config = ceph_core.CephDaemonConfigShow(osd_id=0)
        with self.assertRaises(AttributeError):
            config.foo

        self.assertEqual(config.bluefs_buffered_io, 'true')

    def test_daemon_osd_config_no_exist(self):
        config = ceph_core.CephDaemonConfigShow(osd_id=100)
        with self.assertRaises(AttributeError):
            config.bluefs_buffered_io

    def test_daemon_osd_all_config(self):
        config = ceph_core.CephDaemonConfigShowAllOSDs()
        self.assertEqual(config.foo, [])
        self.assertEqual(config.bluefs_buffered_io, ['true'])


class TestOSDCephSummary(StorageCephOSDTestsBase):

    def test_get_local_osd_ids(self):
        inst = ceph_summary.CephSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(list(actual['local-osds'].keys()),  [0])

    def test_get_local_osd_info(self):
        fsid = "48858aa1-71a3-4f0e-95f3-a07d1d9a6749"
        expected = {0: {
                    'dev': '/dev/mapper/crypt-{}'.format(fsid),
                    'fsid': fsid,
                    'rss': '317M'}}
        inst = ceph_summary.CephSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual["local-osds"], expected)

    def test_get_service_info(self):
        svc_info = {'systemd': {'enabled': [
                                    'ceph-crash',
                                    'ceph-osd',
                                    ],
                                'disabled': [
                                    'ceph-mds',
                                    'ceph-mgr',
                                    'ceph-mon',
                                    'ceph-radosgw',
                                    ],
                                'indirect': ['ceph-volume'],
                                'generated': ['radosgw']},
                    'ps': ['ceph-crash (1)', 'ceph-osd (1)']}
        inst = ceph_summary.CephSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['services'], svc_info)
        self.assertEqual(actual['release'], 'octopus')

    def test_get_network_info(self):
        expected = {'cluster': {
                        'br-ens3': {
                            'addresses': ['10.0.0.128'],
                            'hwaddr': '22:c2:7b:1c:12:1b',
                            'state': 'UP',
                            'speed': 'unknown'}},
                    'public': {
                        'br-ens3': {
                            'addresses': ['10.0.0.128'],
                            'hwaddr': '22:c2:7b:1c:12:1b',
                            'state': 'UP',
                            'speed': 'unknown'}}
                    }
        inst = ceph_summary.CephSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['network'], expected)

    @mock.patch.object(checks, 'CLIHelper')
    def test_get_service_info_unavailable(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.ps.return_value = []
        mock_helper.return_value.dpkg_l.return_value = []
        inst = ceph_summary.CephSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['release'], 'unknown')

    def test_get_package_info(self):
        inst = ceph_summary.CephSummary()
        actual = self.part_output_to_actual(inst.output)
        expected = ['ceph 15.2.14-0ubuntu0.20.04.2',
                    'ceph-base 15.2.14-0ubuntu0.20.04.2',
                    'ceph-common 15.2.14-0ubuntu0.20.04.2',
                    'ceph-mds 15.2.14-0ubuntu0.20.04.2',
                    'ceph-mgr 15.2.14-0ubuntu0.20.04.2',
                    'ceph-mgr-modules-core 15.2.14-0ubuntu0.20.04.2',
                    'ceph-mon 15.2.14-0ubuntu0.20.04.2',
                    'ceph-osd 15.2.14-0ubuntu0.20.04.2',
                    'python3-ceph-argparse 15.2.14-0ubuntu0.20.04.2',
                    'python3-ceph-common 15.2.14-0ubuntu0.20.04.2',
                    'python3-cephfs 15.2.14-0ubuntu0.20.04.2',
                    'python3-rados 15.2.14-0ubuntu0.20.04.2',
                    'python3-rbd 15.2.14-0ubuntu0.20.04.2',
                    'radosgw 15.2.14-0ubuntu0.20.04.2']
        self.assertEquals(actual["dpkg"], expected)

    def test_ceph_base_interfaces(self):
        expected = {'cluster': {'br-ens3': {'addresses': ['10.0.0.128'],
                                            'hwaddr': '22:c2:7b:1c:12:1b',
                                            'state': 'UP',
                                            'speed': 'unknown'}},
                    'public': {'br-ens3': {'addresses': ['10.0.0.128'],
                                           'hwaddr': '22:c2:7b:1c:12:1b',
                                           'state': 'UP',
                                           'speed': 'unknown'}}}
        ports = ceph_core.CephChecksBase().bind_interfaces
        _ports = {}
        for config, port in ports.items():
            _ports.update({config: port.to_dict()})

        self.assertEqual(_ports, expected)


class TestOSDCephEventChecks(StorageCephOSDTestsBase):

    def test_get_ceph_daemon_log_checker(self):
        result = {'osd-reported-failed': {'osd.41': {'2021-02-13': 23},
                                          'osd.85': {'2021-02-13': 4}},
                  'crc-err-bluestore': {'2021-02-12': 5, '2021-02-13': 1},
                  'crc-err-rocksdb': {'2021-02-12': 7},
                  'long-heartbeat-pings': {'2021-02-09': 4},
                  'heartbeat-no-reply': {'2021-02-09': {'osd.0': 1,
                                                        'osd.1': 2}}}
        inst = ceph_event_checks.CephDaemonLogChecks()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual, result)


class TestCephOSDBugChecks(StorageCephOSDTestsBase):

    @mock.patch('core.checks.CLIHelper')
    @mock.patch('core.plugins.storage.ceph.CephDaemonConfigShowAllOSDs')
    @mock.patch('core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('ceph.yaml'))
    def test_bug_check_lp1959649(self, mock_cephdaemon, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.dpkg_l.return_value = \
            ["ii  ceph-osd 15.2.7-0ubuntu0.20.04.2 amd64"]
        mock_cephdaemon.return_value = mock.MagicMock()
        mock_cephdaemon.return_value.bluestore_volume_selection_policy = \
            ['rocksdb_original']
        YBugChecker()()
        expected = {'bugs-detected': [{
                        'desc': (
                            'Vulnerability to a known bug '
                            'https://tracker.ceph.com/issues/38745. RocksDB '
                            'needs more space than the leveled space '
                            'available so it is using storage from the data '
                            'disk. Please set '
                            'bluestore_volume_selection_policy of all OSDs '
                            'to use_some_extra'),
                        'id': 'https://bugs.launchpad.net/bugs/1959649',
                        'origin': 'storage.01part'}]}
        self.assertEqual(known_bugs_utils._get_known_bugs(), expected)

    @mock.patch('core.ycheck.ServiceChecksBase')
    @mock.patch('core.plugins.storage.ceph.CephConfig')
    @mock.patch('core.plugins.storage.bcache.CachesetsConfig')
    @mock.patch('core.plugins.kernel.KernelChecksBase')
    @mock.patch('core.plugins.storage.ceph.CephChecksBase')
    @mock.patch('core.checks.CLIHelper')
    @mock.patch('core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('bcache.yaml'))
    def test_bug_check_lp1936136(self, mocl_cli, mock_cephbase,
                                 mock_kernelbase, mock_cset_config,
                                 mock_ceph_config, mock_svc_check_base):
        mocl_cli.return_value = mock.MagicMock()
        mocl_cli.return_value.dpkg_l.return_value = \
            ["ii  ceph-osd 14.2.22-0ubuntu0.20.04.2 amd64"]

        mock_svc_check_base.return_value = mock.MagicMock()
        mock_svc_check_base.return_value.services = \
            {'ceph-osd': 'enabled'}

        mock_cset_config.return_value = mock.MagicMock()
        mock_cset_config.return_value.get.return_value = 69

        mock_ceph_config.return_value = mock.MagicMock()
        mock_ceph_config.return_value.bluefs_buffered_io.return_value = True

        mock_cephbase.return_value = mock.MagicMock()
        mock_cephbase.return_value.local_osds_use_bcache = True
        mock_kernelbase.return_value = mock.MagicMock()
        mock_kernelbase.return_value.version = '5.3'

        YBugChecker()()
        expected = {'bugs-detected': [{
                        'desc': (
                            'This host has Ceph OSDs using bcache block '
                            'devices and may be vulnerable to bcache bug LP '
                            '1936136. The current workaround is to set '
                            'bluefs_buffered_io is set=False in Ceph or '
                            'upgrade to a kernel >= 5.4.'),
                        'id': 'https://bugs.launchpad.net/bugs/1936136',
                        'origin': 'storage.01part'}]}
        self.assertEqual(known_bugs_utils._get_known_bugs(), expected)


class TestCephConfigChecks(StorageCephOSDTestsBase):

    @mock.patch('core.ycheck.YDefsLoader._is_def', new=utils.is_def_filter(
                    'ssd_osds_no_discard.yaml'))
    @mock.patch('core.issues.issue_utils.add_issue')
    def test_ssd_osds_no_discard(self, mock_add_issue):
        issues = []

        def fake_add_issue(issue):
            issues.append(issue)

        mock_add_issue.side_effect = fake_add_issue
        YConfigChecker()()
        self.assertTrue(mock_add_issue.called)

        msgs = [("This host has osds with device_class 'ssd' but Bluestore "
                 "discard is not enabled. The recommendation is to set 'bdev "
                 "enable discard true'.")]
        self.assertEqual([issue.msg for issue in issues], msgs)

    @mock.patch('core.ycheck.YDefsLoader._is_def', new=utils.is_def_filter(
                    'filestore_to_bluestore_upgrade.yaml'))
    @mock.patch('core.plugins.storage.ceph.CephChecksBase.bluestore_enabled',
                True)
    @mock.patch('core.plugins.storage.ceph.CephConfig')
    @mock.patch('core.issues.issue_utils.add_issue')
    def test_filestore_to_bluestore_upgrade(self, mock_add_issue,
                                            mock_ceph_config):
        issues = []

        def fake_add_issue(issue):
            issues.append(issue)

        mock_ceph_config.return_value = mock.MagicMock()
        mock_ceph_config.return_value.get = lambda args: '/journal/path'
        mock_add_issue.side_effect = fake_add_issue
        YConfigChecker()()
        self.assertTrue(mock_add_issue.called)

        msgs = [("Ceph Bluestore is enabled yet there is a still a journal "
                 "device configured in ceph.conf - please check")]
        self.assertEqual([issue.msg for issue in issues], msgs)
