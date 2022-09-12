import os

from unittest import mock

from .. import utils

from hotsos.core.config import setup_config
from hotsos.core.host_helpers.systemd import SystemdService
from hotsos.core.issues import IssuesManager
from hotsos.core.ycheck.scenarios import YScenarioChecker

CEPH_MGR_DATA_ROOT = os.path.join(utils.TESTS_DIR,
                                  'fake_data_root/storage/ceph-mgr')

OVERLAPPING_ROOTS = """
2022-09-02T09:08:00+0100 7f641f7e3700  0 [pg_autoscaler ERROR root] pool 14 has overlapping roots: {-1, -2}
2022-09-02T09:00:00+0100 7f641f7e3700  0 [pg_autoscaler WARNING root] pool 4 contains an overlapping root -1... skipping scaling
"""  # noqa


class StorageCephMgrTestsBase(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        setup_config(DATA_ROOT=CEPH_MGR_DATA_ROOT, PLUGIN_NAME='storage',
                     MACHINE_READABLE=True)


class TestStorageScenarioChecksCephMgr(StorageCephMgrTestsBase):

    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('ceph-mgr/'
                                        'autoscaler_overlap_roots.yaml'))
    @mock.patch('hotsos.core.host_helpers.systemd.SystemdHelper.services',
                {'ceph-mgr': SystemdService('ceph-mgr', 'enabled')})
    @utils.create_test_files({'var/log/ceph/ceph-mgr.log': OVERLAPPING_ROOTS})
    def test_pg_autoscaler_overlapping_roots(self):
        YScenarioChecker()()
        msg = ("PG autoscaler found overlapping roots for pool(s). As a "
               "result, PG autoscaler won't scale those pools. This happens "
               "when a pool uses a crush rule that doesn't distinguish "
               "between OSD device classes. Any pool using that crush rule "
               "would use OSDs from multiple device classes. Identify those "
               "pools (ceph osd crush tree --show-shadow) and change their "
               "crush rule to use only one of the device classes.")
        issues = list(IssuesManager().load_issues().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])
