import os

from unittest import mock
import json

from .. import utils

from hotsos.core.config import HotSOSConfig
from hotsos.core.plugins.storage import (
    ceph as ceph_core,
)
from hotsos.plugin_extensions.storage import ceph_summary, ceph_event_checks

CEPH_VERSIONS_MISMATCHED_MINOR_MONS_UNALIGNED = """
{
    "mon": {
        "ceph version 15.2.11 (e3523634d9c2227df9af89a4eac33d16738c49cb) octopus (stable)": 3
        "ceph version 15.2.10 (1d69545544ae30333407eefa48e-b696b18994bf) octopus (stable)": 3
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


CEPH_MON_DATA_ROOT = os.path.join(utils.TESTS_DIR,
                                  'fake_data_root/storage/ceph-mon')


class CephMonTestsBase(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        HotSOSConfig.data_root = CEPH_MON_DATA_ROOT
        HotSOSConfig.plugin_name = 'storage'

    def setup_fake_cli_osds_imbalanced_pgs(self, mock_cli_helper):
        """
        Mocks ceph osd df tree so that it contains OSDs with imbalanced PGs.

        Returns a dictionary used to match the output of the storage.ceph
        plugin i.e. the summary output.
        """
        inst = mock.MagicMock()
        mock_cli_helper.return_value = inst
        out = {'nodes': [{'id': 0, 'pgs': 295, 'name': "osd.0"},
                         {'id': 1, 'pgs': 501, 'name': "osd.1"},
                         {'id': 2, 'pgs': 200, 'name': "osd.2"}]}
        inst.ceph_osd_df_tree_json_decoded.return_value = out

        return {'osd-pgs-suboptimal': {
                    'osd.0': 295,
                    'osd.1': 501},
                'osd-pgs-near-limit': {
                     'osd.1': 501}}


class TestCoreCephCluster(CephMonTestsBase):

    def test_cluster_mons(self):
        cluster_mons = ceph_core.CephCluster().mons
        self.assertEqual([ceph_core.CephMon],
                         list(set([type(obj) for obj in cluster_mons])))

    def test_cluster_osds(self):
        cluster_osds = ceph_core.CephCluster().osds
        self.assertEqual([ceph_core.CephOSD],
                         list(set([type(obj) for obj in cluster_osds])))

    def test_health_status(self):
        health = ceph_core.CephCluster().health_status
        self.assertEqual(health, 'HEALTH_WARN')

    def test_osd_versions(self):
        versions = ceph_core.CephCluster().daemon_versions('osd')
        self.assertEqual(versions, {'15.2.14': 3})

    def test_mon_versions(self):
        versions = ceph_core.CephCluster().daemon_versions('mon')
        self.assertEqual(versions, {'15.2.14': 3})

    def test_mds_versions(self):
        versions = ceph_core.CephCluster().daemon_versions('mds')
        self.assertEqual(versions, {})

    def test_rgw_versions(self):
        versions = ceph_core.CephCluster().daemon_versions('rgw')
        self.assertEqual(versions, {})

    def test_osd_release_name(self):
        release_names = ceph_core.CephCluster().daemon_release_names('osd')
        self.assertEqual(release_names, {'octopus': 3})

    def test_mon_release_name(self):
        release_names = ceph_core.CephCluster().daemon_release_names('mon')
        self.assertEqual(release_names, {'octopus': 3})

    def test_cluster_osd_ids(self):
        cluster = ceph_core.CephCluster()
        self.assertEqual([osd.id for osd in cluster.osds], [0, 1, 2])

    def test_crush_rules(self):
        cluster = ceph_core.CephCluster()
        expected = {'replicated_rule': {'id': 0, 'type': 'replicated',
                    'pools': ['device_health_metrics (1)', 'glance (2)',
                              'cinder-ceph (3)', 'nova (4)']}}
        self.assertEqual(cluster.crush_map.rules, expected)

    def test_ceph_daemon_versions_unique(self):
        result = {'mgr': ['15.2.14'],
                  'mon': ['15.2.14'],
                  'osd': ['15.2.14']}
        cluster = ceph_core.CephCluster()
        self.assertEqual(cluster.ceph_daemon_versions_unique(), result)
        self.assertTrue(cluster.ceph_versions_aligned)
        self.assertTrue(cluster.mon_versions_aligned_with_cluster)

    @utils.create_data_root({'sos_commands/ceph_mon/ceph_versions':
                             CEPH_VERSIONS_MISMATCHED_MINOR_MONS_UNALIGNED})
    def test_ceph_daemon_versions_unique_not(self):
        result = {'mgr': ['15.2.11'],
                  'mon': ['15.2.11',
                          '15.2.10'],
                  'osd': ['15.2.11',
                          '15.2.13']}
        cluster = ceph_core.CephCluster()
        self.assertEqual(cluster.ceph_daemon_versions_unique(), result)
        self.assertFalse(cluster.ceph_versions_aligned)
        self.assertFalse(cluster.mon_versions_aligned_with_cluster)

    def test_crushmap_equal_buckets(self):
        cluster = ceph_core.CephCluster()
        buckets = cluster.crush_map.crushmap_equal_buckets
        self.assertEqual(buckets, [])

    @utils.create_data_root({'sos_commands/ceph_mon/ceph_osd_crush_dump':
                             CEPH_OSD_CRUSH_DUMP})
    def test_crushmap_mixed_buckets(self):
        cluster = ceph_core.CephCluster()
        buckets = cluster.crush_map.crushmap_mixed_buckets
        self.assertEqual(buckets, ['default'])

    def test_crushmap_no_mixed_buckets(self):
        cluster = ceph_core.CephCluster()
        buckets = cluster.crush_map.crushmap_mixed_buckets
        self.assertEqual(buckets, [])

    def test_mgr_modules(self):
        cluster = ceph_core.CephCluster()
        expected = ['balancer',
                    'crash',
                    'devicehealth',
                    'orchestrator',
                    'pg_autoscaler',
                    'progress',
                    'rbd_support',
                    'status',
                    'telemetry',
                    'volumes',
                    'iostat',
                    'restful']
        self.assertEqual(cluster.mgr_modules, expected)


class TestCephMonSummary(CephMonTestsBase):

    def test_services(self):
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
        release_info = {'name': 'octopus', 'days-to-eol': 3000}
        inst = ceph_summary.CephSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['services'], svc_info)
        self.assertEqual(actual['release'], release_info)
        self.assertEqual(actual['status'], 'HEALTH_WARN')

    def test_network_info(self):
        expected = {'cluster': {
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
        inst = ceph_summary.CephSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['network'], expected)

    def test_cluster_info(self):
        expected = {'crush-rules': {
                        'replicated_rule': {
                            'id': 0,
                            'pools': [
                                'device_health_metrics (1)',
                                'glance (2)',
                                'cinder-ceph (3)',
                                'nova (4)'],
                            'type': 'replicated'}},
                    'versions': {'mgr': ['15.2.14'],
                                 'mon': ['15.2.14'],
                                 'osd': ['15.2.14']}}
        inst = ceph_summary.CephSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['crush-rules'], expected['crush-rules'])
        self.assertEqual(actual['versions'], expected['versions'])

    @mock.patch('hotsos.core.plugins.storage.ceph.CephCluster.pool_id_to_name',
                lambda *args: 'foo')
    @utils.create_data_root({'sos_commands/ceph_mon/json_output/'
                             'ceph_pg_dump_--format_json-pretty':
                             json.dumps(PG_DUMP_JSON_DECODED)})
    def test_cluster_info_large_omap_pgs(self):
        expected = {'2.f': {
                        'pool': 'foo',
                        'last_scrub_stamp': '2021-09-16T21:26:00.00',
                        'last_deep_scrub_stamp': '2021-09-16T21:26:00.00'}}
        inst = ceph_summary.CephSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['large-omap-pgs'], expected)

    @mock.patch.object(ceph_core, 'CLIHelper')
    def test_ceph_pg_imbalance(self, mock_helper):
        result = self.setup_fake_cli_osds_imbalanced_pgs(mock_helper)
        inst = ceph_summary.CephSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['osd-pgs-suboptimal'],
                         result['osd-pgs-suboptimal'])
        self.assertEqual(actual['osd-pgs-near-limit'],
                         result['osd-pgs-near-limit'])

    @utils.create_data_root({'sos_commands/ceph_mon/json_output/'
                             'ceph_osd_df_tree_--format_json-pretty':
                             json.dumps([])})
    def test_ceph_pg_imbalance_unavailable(self):
        inst = ceph_summary.CephSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertFalse('osd-pgs-suboptimal' in actual)
        self.assertFalse('osd-pgs-near-limit' in actual)

    def test_ceph_versions(self):
        result = {'mgr': ['15.2.14'],
                  'mon': ['15.2.14'],
                  'osd': ['15.2.14']}
        inst = ceph_summary.CephSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['versions'], result)

    @utils.create_data_root({'sos_commands/ceph_mon/ceph_versions':
                             json.dumps([])})
    def test_ceph_versions_unavailable(self):
        inst = ceph_summary.CephSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertIsNone(actual.get('versions'))


class TestCephMonEvents(CephMonTestsBase):

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('mon/monlogs.yaml'))
    @mock.patch('hotsos.core.search.constraints.CLIHelper')
    def test_ceph_daemon_log_checker(self, mock_cli):
        mock_cli.return_value = mock.MagicMock()
        # ensure log file contents are within allowed timeframe ("since")
        mock_cli.return_value.date.return_value = "2022-02-10 00:00:00"
        result = {'osd-reported-failed': {'osd.41': {'2022-02-08': 23},
                                          'osd.85': {'2022-02-08': 4}},
                  'long-heartbeat-pings': {'2022-02-09': 4},
                  'heartbeat-no-reply': {'2022-02-09': {'osd.0': 1,
                                                        'osd.1': 2}}}
        inst = ceph_event_checks.CephDaemonLogChecks()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual, result)


@utils.load_templated_tests('scenarios/storage/ceph/ceph-mon')
class TestCephMonScenarios(CephMonTestsBase):
    """
    Scenario tests can be written using YAML templates that are auto-loaded
    into this test runner. This is the recommended way to write tests for
    scenarios. It is however still possible to write the tests in Python if
    required. See defs/tests/README.md for more info.
    """
