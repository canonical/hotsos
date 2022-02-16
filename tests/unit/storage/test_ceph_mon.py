import os
import shutil
import tempfile

import mock
import json

from tests.unit import utils

from core import constants
from core.ycheck.scenarios import YScenarioChecker
from core.issues import issue_types
from core.plugins.storage import (
    ceph as ceph_core,
)
from plugins.storage.pyparts import (
    ceph_cluster_checks,
    ceph_service_info,
)

MON_ELECTION_LOGS = """
2022-02-02 06:25:23.876485 mon.test mon.1 10.230.16.55:6789/0 16486802 : cluster [INF] mon.test calling monitor election
2022-02-02 06:26:23.876485 mon.test mon.1 10.230.16.55:6789/0 16486802 : cluster [INF] mon.test calling monitor election
2022-02-02 06:27:23.876485 mon.test mon.1 10.230.16.55:6789/0 16486802 : cluster [INF] mon.test calling monitor election
2022-02-02 06:28:23.876485 mon.test mon.1 10.230.16.55:6789/0 16486802 : cluster [INF] mon.test calling monitor election
2022-02-02 06:29:23.876485 mon.test mon.1 10.230.16.55:6789/0 16486802 : cluster [INF] mon.test calling monitor election
"""  # noqa

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

PG_DUMP_JSON_DECODED = {'pg_map': {
                          'pg_stats': [
                            {'stat_sum': {'num_large_omap_objects': 1},
                             'last_scrub_stamp': '2021-09-16T21:26:00.00',
                             'last_deep_scrub_stamp': '2021-09-16T21:26:00.00',
                             'pgid': '2.f',
                             'state': 'active+clean+laggy'}]}}


class StorageCephMonTestsBase(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        os.environ['PLUGIN_NAME'] = 'storage'
        os.environ["DATA_ROOT"] = \
            os.path.join(utils.TESTS_DIR, 'fake_data_root/storage/ceph-mon')


class TestMonCephServiceInfo(StorageCephMonTestsBase):

    def test_get_service_info(self):
        svc_info = {'systemd': {'enabled': [
                                    'ceph-crash',
                                    'ceph-mgr',
                                    'ceph-mon',
                                    ],
                                'disabled': [
                                    'ceph-mds',
                                    'ceph-osd',
                                    'ceph-radosgw',
                                    'ceph-volume'
                                    ],
                                'generated': ['radosgw'],
                                'masked': ['ceph-create-keys']},
                    'ps': ['ceph-crash (1)', 'ceph-mgr (1)', 'ceph-mon (1)']}
        expected = {'ceph': {
                        'services': svc_info,
                        'release': 'octopus',
                        'status': 'HEALTH_WARN',
                    }}
        inst = ceph_service_info.CephServiceChecks()
        inst()
        self.assertEqual(inst.output, expected)


class TestCephMonNetworkInfo(StorageCephMonTestsBase):

    def test_get_network_info(self):
        expected = {'ceph': {
                        'network': {
                            'cluster': {
                                'eth0@if17': {
                                    'addresses': ['10.0.0.123'],
                                    'hwaddr': '00:16:3e:ae:9e:44',
                                    'state': 'UP',
                                    'speed': '10000Mb/s'}},
                            'public': {
                                'eth0@if17': {
                                    'addresses': ['10.0.0.123'],
                                    'hwaddr': '00:16:3e:ae:9e:44',
                                    'state': 'UP',
                                    'speed': '10000Mb/s'}}
                            }
                    }}
        inst = ceph_service_info.CephNetworkInfo()
        inst()
        self.assertEqual(inst.output, expected)


class TestStorageCephChecksBaseCephMon(StorageCephMonTestsBase):

    def test_health_status(self):
        health = ceph_core.CephChecksBase().health_status
        self.assertEqual(health, 'HEALTH_WARN')

    @mock.patch('core.plugins.storage.ceph.CLIHelper')
    def test_check_osdmaps_size(self, mock_helper):
        pinned = {'osdmap_manifest': {'pinned_maps': range(5496)}}
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.ceph_report_json_decoded.return_value = pinned
        self.assertEqual(ceph_core.CephMon().osdmaps_count, 5496)


class TestStorageCephDaemons(StorageCephMonTestsBase):

    def test_osd_versions(self):
        versions = ceph_core.CephOSD(1, 1234, '/dev/foo').versions
        self.assertEqual(versions, {'15.2.14': 3})

    def test_mon_versions(self):
        versions = ceph_core.CephMon().versions
        self.assertEqual(versions, {'15.2.14': 3})

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
        self.assertEqual(release_names, {'octopus': 3})


class TestStorageCephClusterChecksCephMon(StorageCephMonTestsBase):

    @mock.patch.object(ceph_cluster_checks.issue_utils, 'add_issue')
    def test_check_large_omap_objects_no_issue(self, mock_add_issue):
        inst = ceph_cluster_checks.CephClusterChecks()
        inst.check_large_omap_objects()
        self.assertFalse(mock_add_issue.called)

    @mock.patch('core.plugins.storage.ceph.CLIHelper')
    @mock.patch.object(ceph_cluster_checks.issue_utils, 'add_issue')
    def test_check_large_omap_objects_w_issue(self, mock_add_issue, mock_cli):
        mock_cli.return_value = mock.MagicMock()
        mock_cli.return_value.ceph_pg_dump_json_decoded.return_value = \
            PG_DUMP_JSON_DECODED
        inst = ceph_cluster_checks.CephClusterChecks()
        inst.check_large_omap_objects()
        self.assertTrue(mock_add_issue.called)

    @mock.patch('plugins.storage.pyparts.ceph_cluster_checks.'
                'OSD_META_LIMIT_KB', 1024)
    @mock.patch.object(ceph_cluster_checks, 'issue_utils')
    def test_check_ceph_bluefs_size(self, mock_issue_utils):
        inst = ceph_cluster_checks.CephClusterChecks()
        inst.check_ceph_bluefs_size()
        self.assertTrue(mock_issue_utils.add_issue.called)

    def test_get_crush_rules(self):
        inst = ceph_cluster_checks.CephClusterChecks()
        inst()
        expected = {'replicated_rule': {'id': 0, 'type': 'replicated',
                    'pools': ['device_health_metrics (1)', 'glance (2)',
                              'cinder-ceph (3)', 'nova (4)']}}
        self.assertEqual(inst.crush_rules, expected)

    @mock.patch.object(ceph_cluster_checks, 'issue_utils')
    def test_check_osd_v2(self, mock_issue_utils):
        with tempfile.TemporaryDirectory() as dtmp:
            src = os.path.join(constants.DATA_ROOT,
                               ('sos_commands/ceph_mon/json_output/'
                                'ceph_osd_dump_--format_json-pretty.'
                                'v1_only_osds'))
            dst = os.path.join(dtmp, 'sos_commands/ceph_mon/json_output/'
                               'ceph_osd_dump_--format_json-pretty')
            os.makedirs(os.path.dirname(dst))
            shutil.copy(src, dst)
            os.environ['DATA_ROOT'] = dtmp
            inst = ceph_cluster_checks.CephClusterChecks()
            inst.check_osd_msgr_protocol_versions()
            self.assertTrue(mock_issue_utils.add_issue.called)

    @mock.patch.object(ceph_core, 'CLIHelper')
    @mock.patch.object(ceph_cluster_checks.issue_utils, "add_issue")
    def test_get_ceph_pg_imbalance(self, mock_add_issue, mock_helper):

        mock_helper.return_value = mock.MagicMock()
        out = {'nodes': [{'id': 0, 'pgs': 295, 'name': "osd.0"},
                         {'id': 1, 'pgs': 501, 'name': "osd.1"},
                         {'id': 2, 'pgs': 200, 'name': "osd.2"}]}
        mock_helper.return_value.ceph_osd_df_tree_json_decoded.return_value = \
            out

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
        inst = ceph_cluster_checks.CephClusterChecks()
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

    @mock.patch.object(ceph_core, 'CLIHelper')
    def test_get_ceph_pg_imbalance_unavailable(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.ceph_osd_df_tree.return_value = []
        inst = ceph_cluster_checks.CephClusterChecks()
        inst.get_ceph_pg_imbalance()
        self.assertEqual(inst.output, None)

    @mock.patch.object(ceph_cluster_checks, 'issue_utils')
    def test_check_crushmap_non_equal_buckets(self, mock_issue_utils):
        """
        Verifies that the check_crushmap_equal_buckets() function
        correctly raises an issue against a known bad CRUSH map.
        """
        test_data_path = ('sos_commands/ceph_mon/json_output/'
                          'ceph_osd_crush_dump_--format_'
                          'json-pretty.unbalanced')
        osd_crush_dump_path = os.path.join(os.environ["DATA_ROOT"],
                                           test_data_path)
        osd_crush_dump = json.load(open(osd_crush_dump_path))
        with mock.patch.object(ceph_core, 'CLIHelper') as mock_helper:
            mock_helper.return_value = mock.MagicMock()
            mock_helper.return_value.ceph_osd_crush_dump_json_decoded.\
                return_value = osd_crush_dump
            inst = ceph_cluster_checks.CephClusterChecks()
            inst.check_crushmap_equal_buckets()
            self.assertTrue(mock_issue_utils.add_issue.called)

    @mock.patch.object(ceph_cluster_checks, 'issue_utils')
    def test_check_crushmap_equal_buckets(self, mock_issue_utils):
        inst = ceph_cluster_checks.CephClusterChecks()
        inst.check_crushmap_equal_buckets()
        self.assertFalse(mock_issue_utils.add_issue.called)

    @mock.patch.object(ceph_cluster_checks, 'issue_utils')
    def test_get_crushmap_mixed_buckets(self, mock_issue_utils):
        '''
        Verifies that the check_crushmap_equal_buckets() function
        correctly does not raise an issue against a known good CRUSH map.
        '''
        with mock.patch.object(ceph_core, 'CLIHelper') as mock_helper:
            mock_helper.return_value = mock.MagicMock()
            mock_helper.return_value.ceph_osd_crush_dump_json_decoded.\
                return_value = json.loads(CEPH_OSD_CRUSH_DUMP)
            inst = ceph_cluster_checks.CephClusterChecks()
            inst.get_crushmap_mixed_buckets()
            self.assertTrue(mock_issue_utils.add_issue.called)

    @mock.patch.object(ceph_cluster_checks, 'issue_utils')
    def test_get_crushmap_no_mixed_buckets(self, mock_issue_utils):
        inst = ceph_cluster_checks.CephClusterChecks()
        inst.get_crushmap_mixed_buckets()
        self.assertFalse(mock_issue_utils.add_issue.called)

    def test_get_ceph_versions_mismatch_pass(self):
        result = {'mgr': ['15.2.14'],
                  'mon': ['15.2.14'],
                  'osd': ['15.2.14']}
        inst = ceph_cluster_checks.CephClusterChecks()
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
            inst = ceph_cluster_checks.CephClusterChecks()
            inst.get_ceph_versions_mismatch()
            self.assertEqual(inst.output["ceph"]["versions"], result)

    @mock.patch.object(ceph_cluster_checks.issue_utils, "add_issue")
    def test_get_ceph_mon_lower_version(self, mock_add_issue):
        issues = []

        def fake_add_issue(issue):
            issues.append(issue)

        mock_add_issue.side_effect = fake_add_issue
        with mock.patch.object(ceph_core, 'CLIHelper') as mock_helper:
            mock_helper.return_value = mock.MagicMock()
            mock_helper.return_value.ceph_versions.return_value = \
                CEPH_VERSIONS_MISMATCHED_MINOR.split('\n')
            inst = ceph_cluster_checks.CephClusterChecks()
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
        inst = ceph_cluster_checks.CephClusterChecks()
        inst.get_ceph_versions_mismatch()
        self.assertIsNone(inst.output)

    def test_get_cluster_osd_ids(self):
        inst = ceph_cluster_checks.CephClusterChecks()
        inst()
        self.assertEqual([osd.id for osd in inst.cluster_osds], [0, 1, 2])


class TestStorageScenarioChecksCephMon(StorageCephMonTestsBase):

    @mock.patch('core.issues.issue_utils.add_issue')
    def test_scenarios_none(self, mock_add_issue):
        with tempfile.TemporaryDirectory() as dtmp:
            os.environ['DATA_ROOT'] = dtmp
            YScenarioChecker()()
            self.assertFalse(mock_add_issue.called)

    @mock.patch('core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('mon_elections_flapping.yaml'))
    @mock.patch('core.plugins.storage.ceph.CephChecksBase')
    @mock.patch('core.issues.issue_utils.add_issue')
    def test_scenario_mon_reelections(self, mock_add_issue, mock_cephbase):
        issues = []

        def fake_add_issue(issue):
            issues.append(issue)

        mock_add_issue.side_effect = fake_add_issue
        mock_cephbase.return_value = mock.MagicMock()
        mock_cephbase.return_value.plugin_runnable = True
        mock_cephbase.return_value.has_interface_errors = True
        mock_cephbase.return_value.bind_interface_names = 'ethX'

        with tempfile.TemporaryDirectory() as dtmp:
            path = os.path.join(dtmp, 'var/log/ceph')
            os.makedirs(path)
            with open(os.path.join(path, 'ceph.log'), 'w') as fd:
                fd.write(MON_ELECTION_LOGS)

            os.environ['DATA_ROOT'] = dtmp
            YScenarioChecker()()

        self.assertTrue(mock_add_issue.called)
        msg = ("Ceph monitor is experiencing repeated re-elections. The "
               "network interface(s) (ethX) used by the ceph-mon are "
               "showing errors - please investigate.")
        self.assertEqual([issue.msg for issue in issues], [msg])

    @mock.patch('core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('bluefs_spillover.yaml'))
    @mock.patch('core.ycheck.CLIHelper')
    @mock.patch('core.plugins.storage.ceph.CephChecksBase')
    @mock.patch('core.issues.issue_utils.add_issue')
    def test_scenario_bluefs_spillover(self, mock_add_issue, mock_cephbase,
                                       mock_helper):
        issues = []

        def fake_add_issue(issue):
            issues.append(issue)

        mock_add_issue.side_effect = fake_add_issue
        mock_cephbase.return_value = mock.MagicMock()
        mock_cephbase.return_value.plugin_runnable = True
        mock_cephbase.return_value.health_status = 'HEALTH_WARN'
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.ceph_health_detail_json_decoded.return_value \
            = " experiencing BlueFS spillover"

        YScenarioChecker()()
        self.assertTrue(mock_add_issue.called)
        msg = ('Known ceph bug https://tracker.ceph.com/issues/38745 '
               'detected. RocksDB needs more space than the leveled '
               'space available. See '
               'www.mail-archive.com/ceph-users@ceph.io/msg05782.html')
        self.assertEqual([issue.msg for issue in issues], [msg])

    @mock.patch('core.plugins.storage.ceph.CLIHelper')
    @mock.patch('core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter(
                    'osd_maps_backlog_too_large.yaml'))
    @mock.patch('core.plugins.storage.ceph.CephChecksBase')
    @mock.patch('core.issues.issue_utils.add_issue')
    def test_scenario_osd_maps_backlog_too_large(self, mock_add_issue,
                                                 mock_cephbase, mock_helper):
        issues = []

        def fake_add_issue(issue):
            issues.append(issue)

        pinned = {'osdmap_manifest': {'pinned_maps': range(5496)}}
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.ceph_report_json_decoded.return_value = pinned
        mock_add_issue.side_effect = fake_add_issue
        mock_cephbase.return_value = mock.MagicMock()
        mock_cephbase.return_value.plugin_runnable = True

        YScenarioChecker()()
        self.assertTrue(mock_add_issue.called)
        msg = ("Found 5496 pinned osdmaps. This can affect mon's performance "
               "and also indicate bugs such as "
               "https://tracker.ceph.com/issues/44184 and "
               "https://tracker.ceph.com/issues/47290.")
        self.assertEqual([issue.msg for issue in issues], [msg])

    @mock.patch('core.plugins.storage.ceph.CephCluster.require_osd_release',
                'octopus')
    @mock.patch('core.plugins.storage.ceph.CLIHelper')
    @mock.patch('core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('required_osd_release_mismatch.yaml'))
    @mock.patch('core.issues.issue_utils.add_issue')
    def test_required_osd_release(self, mock_add_issue, mock_helper):
        issues = []

        def fake_add_issue(issue):
            issues.append(issue)

        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.ceph_versions.return_value = \
            CEPH_VERSIONS_MISMATCHED_MAJOR.split('\n')
        mock_add_issue.side_effect = fake_add_issue

        YScenarioChecker()()
        self.assertTrue(mock_add_issue.called)
        msg = ('require_osd_release is octopus but not all OSDs are on that '
               'version - please check.')
        self.assertEqual([issue.msg for issue in issues], [msg])

    @mock.patch('core.plugins.storage.ceph.CephCluster.require_osd_release',
                'octopus')
    @mock.patch('core.plugins.storage.ceph.CLIHelper')
    @mock.patch('core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('laggy_pgs.yaml'))
    @mock.patch('core.issues.issue_utils.add_issue')
    def test_laggy_pgs(self, mock_add_issue, mock_helper):
        issues = []

        def fake_add_issue(issue):
            issues.append(issue)

        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.ceph_pg_dump_json_decoded.return_value = \
            PG_DUMP_JSON_DECODED
        mock_add_issue.side_effect = fake_add_issue

        YScenarioChecker()()
        self.assertTrue(mock_add_issue.called)
        msg = ('Ceph cluster is reporting 1 laggy/wait PGs. This suggests a '
               'potential network or storage issue - please check.')
        self.assertEqual([issue.msg for issue in issues], [msg])

    @mock.patch('core.ycheck.ServiceChecksBase.services',
                {'ceph-mon': 'enabled'})
    @mock.patch('core.plugins.storage.ceph.CephChecksBase.health_status',
                'HEALTH_WARN')
    @mock.patch('core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('ceph_cluster_health.yaml'))
    @mock.patch('core.issues.issue_utils.add_issue')
    def test_ceph_cluster_health(self, mock_add_issue):
        issues = []

        def fake_add_issue(issue):
            issues.append(issue)

        mock_add_issue.side_effect = fake_add_issue

        YScenarioChecker()()
        self.assertTrue(mock_add_issue.called)
        msg = ("Ceph cluster is in 'HEALTH_WARN' state. Please check "
               "'ceph status' for details.")
        self.assertEqual([issue.msg for issue in issues], [msg])

    @mock.patch('core.ycheck.ServiceChecksBase.services',
                {'ceph-mon': 'enabled'})
    @mock.patch('core.plugins.storage.ceph.CephChecksBase.health_status',
                'HEALTH_OK')
    @mock.patch('core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('ceph_cluster_health.yaml'))
    @mock.patch('core.issues.issue_utils.add_issue')
    def test_ceph_cluster_health_ok(self, mock_add_issue):
        YScenarioChecker()()
        self.assertFalse(mock_add_issue.called)

    @mock.patch('core.ycheck.ServiceChecksBase.services',
                {'ceph-osd': 'enabled'})
    @mock.patch('core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('ceph_cluster_health.yaml'))
    @mock.patch('core.issues.issue_utils.add_issue')
    def test_ceph_cluster_health_not_ceph_mon(self, mock_add_issue):
        YScenarioChecker()()
        self.assertFalse(mock_add_issue.called)
