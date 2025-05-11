from unittest import mock

from hotsos.core.config import HotSOSConfig
from hotsos.core import host_helpers
from hotsos.core.host_helpers.cli.common import CmdOutput
from hotsos.core.plugins.storage import ceph
from hotsos.core.ycheck.common import GlobalSearcher
from hotsos.plugin_extensions.storage import (
    ceph_summary,
    ceph_event_checks,
)

from .. import utils

# pylint: disable=duplicate-code


CEPH_CONF_NO_BLUESTORE = """
[global]
[osd]
osd objectstore = filestore
osd journal size = 1024
filestore xattr use omap = true
"""


class StorageCephOSDTestsBase(utils.BaseTestCase):
    """ Custom test case that sets the storage plugin context. """
    def setUp(self):
        super().setUp()
        HotSOSConfig.plugin_name = 'storage'


class TestCephOSDChecks(StorageCephOSDTestsBase):
    """ Unit tests for Ceph osd checks. """
    @mock.patch.object(ceph.daemon, 'CLIHelper')
    def test_get_date_secs(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.date.return_value = "1234\n"
        self.assertEqual(ceph.daemon.CephDaemonBase.get_date_secs(), 1234)

    def test_get_date_secs_from_timestamp(self):
        date_string = "Thu Mar 25 10:55:05 MDT 2021"
        self.assertEqual(ceph.daemon.CephDaemonBase.get_date_secs(date_string),
                         1616691305)

    def test_get_date_secs_from_timestamp_w_tz(self):
        date_string = "Thu Mar 25 10:55:05 UTC 2021"
        self.assertEqual(ceph.daemon.CephDaemonBase.get_date_secs(date_string),
                         1616669705)

    def test_release_name(self):
        release_name = ceph.common.CephChecks().release_name
        self.assertEqual(release_name, 'octopus')

    @mock.patch('hotsos.core.host_helpers.cli.catalog.DateFileCmd.format_date')
    def test_release_eol(self, mock_date):
        # 2030-04-30
        mock_date.return_value = CmdOutput('1903748400')

        base = ceph.common.CephChecks()

        self.assertEqual(base.release_name, 'octopus')
        self.assertLessEqual(base.days_to_eol, 0)

    @mock.patch('hotsos.core.host_helpers.cli.catalog.DateFileCmd.format_date')
    def test_release_not_eol(self, mock_date):
        # 2030-01-01
        mock_date.return_value = CmdOutput('1893466800')

        base = ceph.common.CephChecks()

        self.assertEqual(base.release_name, 'octopus')
        self.assertGreater(base.days_to_eol, 0)

    def test_bluestore_enabled(self):
        enabled = ceph.common.CephChecks().bluestore_enabled
        self.assertTrue(enabled)

    @utils.create_data_root({'etc/ceph/ceph.conf': CEPH_CONF_NO_BLUESTORE})
    def test_bluestore_not_enabled(self):
        enabled = ceph.common.CephChecks().bluestore_enabled
        self.assertFalse(enabled)

    def test_daemon_osd_config(self):
        config = ceph.common.CephDaemonConfigShow(osd_id=0)
        with self.assertRaises(AttributeError):
            _ = config.foo

        self.assertEqual(config.bluefs_buffered_io, 'true')

    def test_daemon_osd_config_no_exist(self):
        config = ceph.common.CephDaemonConfigShow(osd_id=100)
        with self.assertRaises(AttributeError):
            _ = config.bluefs_buffered_io

    def test_daemon_osd_all_config(self):
        config = ceph.common.CephDaemonAllOSDsCommand('CephDaemonConfigShow')
        self.assertEqual(config.foo, [])
        self.assertEqual(config.bluefs_buffered_io, ['true'])


class TestCephOSDSummary(StorageCephOSDTestsBase):
    """ Unit tests for Ceph osd summary. """
    def test_local_osd_ids(self):
        inst = ceph_summary.CephSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(list(actual['local-osds'].keys()), [0])

    def test_local_osd_info(self):
        fsid = "48858aa1-71a3-4f0e-95f3-a07d1d9a6749"
        expected = {0: {
                    'dev': f'/dev/mapper/crypt-{fsid}',
                    'fsid': fsid,
                    'rss': '317M'}}
        inst = ceph_summary.CephSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual["local-osds"], expected)

    def test_service_info(self):
        svc_info = {'systemd': {'enabled': [
                                    'ceph-crash',
                                    'ceph-osd'],
                                'disabled': [
                                    'ceph-mds',
                                    'ceph-mgr',
                                    'ceph-mon',
                                    'ceph-radosgw'],
                                'generated': ['radosgw']},
                    'ps': ['ceph-crash (1)', 'ceph-osd (1)']}
        release_info = {'name': 'octopus', 'days-to-eol': 3000}
        inst = ceph_summary.CephSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['services'], svc_info)
        self.assertEqual(actual['release'], release_info)

    def test_network_info(self):
        expected = {'cluster': {
                        'br-ens3': {
                            'addresses': ['10.0.0.128'],
                            'hwaddr': '22:c2:7b:1c:12:1b',
                            'mtu': 1500,
                            'state': 'UP',
                            'speed': 'unknown'}},
                    'public': {
                        'br-ens3': {
                            'addresses': ['10.0.0.128'],
                            'hwaddr': '22:c2:7b:1c:12:1b',
                            'mtu': 1500,
                            'state': 'UP',
                            'speed': 'unknown'}}
                    }
        inst = ceph_summary.CephSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['network'], expected)

    @mock.patch.object(host_helpers.packaging, 'CLIHelper')
    def test_service_info_unavailable(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.ps.return_value = []
        mock_helper.return_value.dpkg_l.return_value = []
        inst = ceph_summary.CephSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertFalse('release' in actual)

    def test_package_info(self):
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

    def test_ceph_daemon_interfaces(self):
        expected = {'cluster': {'br-ens3': {'addresses': ['10.0.0.128'],
                                            'hwaddr': '22:c2:7b:1c:12:1b',
                                            'mtu': 1500,
                                            'state': 'UP',
                                            'speed': 'unknown'}},
                    'public': {'br-ens3': {'addresses': ['10.0.0.128'],
                                           'hwaddr': '22:c2:7b:1c:12:1b',
                                           'mtu': 1500,
                                           'state': 'UP',
                                           'speed': 'unknown'}}}
        ports = ceph.common.CephChecks().bind_interfaces
        _ports = {}
        for config, port in ports.items():
            _ports.update({config: port.to_dict()})

        self.assertEqual(_ports, expected)


class TestCephOSDEvents(StorageCephOSDTestsBase):
    """ Unit tests for Ceph osd event checks. """
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('osd/osdlogs.yaml',
                                        'events/storage/ceph'))
    @mock.patch('hotsos.core.search.CLIHelper')
    def test_ceph_daemon_log_checker(self, mock_cli):
        mock_cli.return_value = mock.MagicMock()
        # ensure log file contents are within allowed timeframe ("since")
        mock_cli.return_value.date.return_value = "2021-01-01 00:00:00"
        result = {'crc-err-bluestore': {'2021-02-12': 5, '2021-02-13': 1},
                  'crc-err-rocksdb': {'2021-02-12': 7}}

        with GlobalSearcher() as global_searcher:
            inst = ceph_event_checks.CephEventHandler(global_searcher)
            actual = self.part_output_to_actual(inst.output)
            for key, value in result.items():
                self.assertEqual(actual[key], value)


@utils.load_templated_tests('scenarios/storage/ceph/ceph-osd')
class TestCephOSDScenarios(StorageCephOSDTestsBase):
    """
    Scenario tests can be written using YAML templates that are auto-loaded
    into this test runner. This is the recommended way to write tests for
    scenarios. It is however still possible to write the tests in Python if
    required. See https://hotsos.readthedocs.io/en/latest/contrib/testing.html
    for more information.
    """
