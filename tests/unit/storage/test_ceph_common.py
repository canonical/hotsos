import os

from hotsos.core.config import HotSOSConfig
from hotsos.core.plugins.storage import ceph

from .. import utils


CEPH_MON_DATA_ROOT = os.path.join(utils.TESTS_DIR,
                                  'fake_data_root/storage/ceph-mon')

SNAP_LIST_MICROCEPH = """
Name       Version                Rev    Tracking       Publisher   Notes
core20     20240111               2182   latest/stable  canonical✓  base
core22     20240111               1122   latest/stable  canonical✓  base
lxd        5.0.3-9a1d904          27428  5.0/stable/…   canonical✓  -
microceph  18.2.0+snap450240f5dd  975    reef/stable    canonical✓  held
snapd      2.61.2                 21184  latest/stable  canonical✓  snapd
"""


class CephCommonTestsBase(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        HotSOSConfig.data_root = CEPH_MON_DATA_ROOT
        HotSOSConfig.plugin_name = 'storage'


class TestCephPluginDeps(CephCommonTestsBase):

    def test_ceph_dep_dpkg(self):
        self.assertTrue(ceph.CephChecksBase().plugin_runnable)

    @utils.create_data_root({'sos_commands/snap/snap_list_--all':
                             SNAP_LIST_MICROCEPH})
    def test_ceph_dep_snap(self):
        self.assertTrue(ceph.CephChecksBase().plugin_runnable)
        self.assertEqual(ceph.CephChecksBase().release_name, 'reef')


@utils.load_templated_tests('scenarios/storage/ceph/common')
class TestCephCommonScenarios(CephCommonTestsBase):
    """
    Scenario tests can be written using YAML templates that are auto-loaded
    into this test runner. This is the recommended way to write tests for
    scenarios. It is however still possible to write the tests in Python if
    required. See defs/tests/README.md for more info.
    """
