from unittest import mock

from .. import utils

from hotsos.core.config import setup_config
from hotsos.core import host_helpers
from hotsos.core.issues import IssuesManager
from hotsos.core.ycheck.scenarios import YScenarioChecker
from hotsos.core.host_helpers.systemd import SystemdService
from hotsos.core.plugins.storage import (
    ceph as ceph_core,
)
from hotsos.plugin_extensions.storage import (
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
        setup_config(PLUGIN_NAME='storage', MACHINE_READABLE=True)


class TestOSDCephChecksBase(StorageCephOSDTestsBase):

    @mock.patch.object(ceph_core, 'CLIHelper')
    def test_get_date_secs(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.date.return_value = "1234\n"
        self.assertEqual(ceph_core.CephDaemonBase.get_date_secs(), 1234)

    def test_get_date_secs_from_timestamp(self):
        date_string = "Thu Mar 25 10:55:05 MDT 2021"
        self.assertEqual(ceph_core.CephDaemonBase.get_date_secs(date_string),
                         1616691305)

    def test_get_date_secs_from_timestamp_w_tz(self):
        date_string = "Thu Mar 25 10:55:05 UTC 2021"
        self.assertEqual(ceph_core.CephDaemonBase.get_date_secs(date_string),
                         1616669705)

    def test_release_name(self):
        release_name = ceph_core.CephChecksBase().release_name
        self.assertEqual(release_name, 'octopus')

    @mock.patch('hotsos.core.host_helpers.cli.DateFileCmd.format_date')
    def test_release_eol(self, mock_date):
        # 2030-04-30
        mock_date.return_value = '1903748400'

        base = ceph_core.CephChecksBase()

        self.assertEqual(base.release_name, 'octopus')
        self.assertLessEqual(base.days_to_eol, 0)

    @mock.patch('hotsos.core.host_helpers.cli.DateFileCmd.format_date')
    def test_release_not_eol(self, mock_date):
        # 2030-01-01
        mock_date.return_value = '1893466800'

        base = ceph_core.CephChecksBase()

        self.assertEqual(base.release_name, 'octopus')
        self.assertGreater(base.days_to_eol, 0)

    def test_bluestore_enabled(self):
        enabled = ceph_core.CephChecksBase().bluestore_enabled
        self.assertTrue(enabled)

    @utils.create_test_files({'etc/ceph/ceph.conf': CEPH_CONF_NO_BLUESTORE})
    def test_bluestore_not_enabled(self):
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
        release_info = {'name': 'octopus', 'days-to-eol': 3000}
        inst = ceph_summary.CephSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['services'], svc_info)
        self.assertEqual(actual['release'], release_info)

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

    @mock.patch.object(host_helpers.packaging, 'CLIHelper')
    def test_get_service_info_unavailable(self, mock_helper):
        release_info = {'name': 'unknown', 'days-to-eol': None}

        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.ps.return_value = []
        mock_helper.return_value.dpkg_l.return_value = []
        inst = ceph_summary.CephSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['release'], release_info)

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
        self.assertEqual(actual["dpkg"], expected)

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

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('osd/osdlogs.yaml'))
    def test_get_ceph_daemon_log_checker(self):
        result = {'crc-err-bluestore': {'2021-02-12': 5, '2021-02-13': 1},
                  'crc-err-rocksdb': {'2021-02-12': 7}}
        inst = ceph_event_checks.CephDaemonLogChecks()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual, result)


class TestCephScenarioChecks(StorageCephOSDTestsBase):

    @mock.patch('hotsos.core.plugins.storage.ceph.CephChecksBase.'
                'local_osds_use_bcache', True)
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter(
                                   'ceph-osd/juju_ceph_no_bcache_tuning.yaml'))
    def test_juju_ceph_no_bcache_tuning(self):
        YScenarioChecker()()
        msg = ("This host is running Juju-managed Ceph OSDs that are "
               "using bcache devices yet the bcache-tuning charm was "
               "not detected. It is recommended to use the "
               "bcache-tuning charm to ensure optimal bcache "
               "configuration.")
        issues = list(IssuesManager().load_issues().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.host_helpers.packaging.CLIHelper')
    @mock.patch('hotsos.core.plugins.storage.ceph.CephDaemonConfigShowAllOSDs')
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('ceph-osd/bugs.yaml'))
    @mock.patch('hotsos.core.host_helpers.systemd.SystemdHelper.services',
                {'ceph-osd': SystemdService('ceph-osd', 'enabled')})
    def test_bug_check_lp1959649(self, mock_cephdaemon, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.dpkg_l.return_value = \
            ["ii  ceph-osd 15.2.7-0ubuntu0.20.04.2 amd64"]
        mock_cephdaemon.return_value = mock.MagicMock()
        mock_cephdaemon.return_value.bluestore_volume_selection_policy = \
            ['rocksdb_original']
        YScenarioChecker()()
        msg = ('This host is vulnerable to known bug '
               'https://tracker.ceph.com/issues/38745. RocksDB needs more '
               'space than the leveled space available so it is using storage '
               'from the data disk. Please set '
               'bluestore_volume_selection_policy of all OSDs to '
               'use_some_extra')
        context = {'package': 'ceph-osd', 'version': '15.2.7-0ubuntu0.20.04.2',
                   'property': ('hotsos.core.plugins.storage.ceph.'
                                'CephDaemonConfigShowAllOSDs.'
                                'bluestore_volume_selection_policy'),
                   'ops': 'ne []', 'value_actual': ['rocksdb_original'],
                   'passes': True}
        expected = {'bugs-detected': [{
                        'context': context,
                        'desc': msg,
                        'id': 'https://bugs.launchpad.net/bugs/1959649',
                        'origin': 'storage.01part'}]}
        self.assertEqual(IssuesManager().load_bugs(), expected)

    @mock.patch('hotsos.core.plugins.kernel.sysfs.CPU.'
                'cpufreq_scaling_governor_all', 'powersave')
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('ceph-osd/system_cpufreq_mode.yaml'))
    def test_scenarios_cpufreq(self):
        YScenarioChecker()()
        msg = ('This node has Ceph OSDs running on it but is not using '
               'cpufreq scaling_governor in "performance" mode '
               '(actual=powersave). This is not recommended and can result '
               'in performance degradation. To fix this you can install '
               'cpufrequtils, set "GOVERNOR=performance" in '
               '/etc/default/cpufrequtils and run systemctl restart '
               'cpufrequtils. You will also need to stop and disable the '
               'ondemand systemd service in order for changes to persist.')
        issues = list(IssuesManager().load_issues().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('ceph-osd/ssd_osds_no_discard.yaml'))
    def test_ssd_osds_no_discard(self):
        self.skipTest("scenario currently disabled until fixed")

        YScenarioChecker()()
        msgs = [("This host has osds with device_class 'ssd' but Bluestore "
                 "discard is not enabled. The recommendation is to set 'bdev "
                 "enable discard true'.")]
        issues = list(IssuesManager().load_issues().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], msgs)

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter(
                               'ceph-osd/filestore_to_bluestore_upgrade.yaml'))
    @mock.patch('hotsos.core.plugins.storage.ceph.CephChecksBase.'
                'bluestore_enabled', True)
    @mock.patch('hotsos.core.plugins.storage.ceph.CephConfig')
    def test_filestore_to_bluestore_upgrade(self, mock_ceph_config):
        mock_ceph_config.return_value = mock.MagicMock()
        mock_ceph_config.return_value.get = lambda args: '/journal/path'
        YScenarioChecker()()
        msg = ("Ceph Bluestore is enabled yet there is a still a journal "
               "device configured in ceph.conf - please check")
        issues = list(IssuesManager().load_issues().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.plugins.storage.ceph.CephConfig')
    @mock.patch('hotsos.core.plugins.storage.bcache.CachesetsConfig')
    @mock.patch('hotsos.core.plugins.kernel.KernelBase')
    @mock.patch('hotsos.core.plugins.storage.ceph.CephChecksBase')
    @mock.patch('hotsos.core.host_helpers.packaging.CLIHelper')
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('ceph-osd/bcache_lp1936136.yaml'))
    @mock.patch('hotsos.core.host_helpers.systemd.SystemdHelper.services',
                {'ceph-osd': SystemdService('ceph-osd', 'enabled')})
    def test_lp1936136(self, mocl_cli, mock_cephbase, mock_kernelbase,
                       mock_cset_config, mock_ceph_config):
        def fake_ceph_config(key):
            if key == 'bluefs_buffered_io':
                return 'true'

        mocl_cli.return_value = mock.MagicMock()
        mocl_cli.return_value.dpkg_l.return_value = \
            ["ii  ceph-osd 14.2.22-0ubuntu0.20.04.2 amd64"]

        mock_cset_config.return_value = mock.MagicMock()
        mock_cset_config.return_value.get.return_value = 69

        mock_ceph_config.return_value = mock.MagicMock()
        mock_ceph_config.return_value.get.side_effect = fake_ceph_config

        mock_cephbase.return_value = mock.MagicMock()
        mock_cephbase.return_value.local_osds_use_bcache = True
        mock_kernelbase.return_value = mock.MagicMock()
        mock_kernelbase.return_value.version = '5.3'

        YScenarioChecker()()

        msg = ('This host has Ceph OSDs using bcache block devices and may be '
               'vulnerable to bcache bug LP 1936136 since '
               'bcache cache_available_percent is lt 70 (actual=69). The '
               'current workaround is to set bluefs_buffered_io=false in Ceph '
               'or upgrade to a kernel >= 5.4.')

        issues = list(IssuesManager().load_bugs().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('ceph-osd/eol.yaml'))
    @mock.patch('hotsos.core.host_helpers.cli.DateFileCmd.format_date')
    def test_ceph_osd_eol(self, mock_date):
        # 2030-04-30
        mock_date.return_value = '1903748400'

        YScenarioChecker()()
        issues = list(IssuesManager().load_issues().values())[0]

        expected = ('This node is running a version of Ceph that is '
                    'End of Life (release=octopus) which means it '
                    'has limited support and is likely not receiving '
                    'updates anymore. Please consider upgrading to a '
                    'newer release.')

        self.assertEqual(issues[0]['desc'], expected)
