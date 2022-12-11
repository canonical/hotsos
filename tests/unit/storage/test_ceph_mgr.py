import os
from .. import utils

from hotsos.core.config import setup_config

CEPH_MGR_DATA_ROOT = os.path.join(utils.TESTS_DIR,
                                  'fake_data_root/storage/ceph-mon')


class CephMgrTestsBase(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        setup_config(DATA_ROOT=CEPH_MGR_DATA_ROOT, PLUGIN_NAME='storage')


@utils.load_templated_tests('scenarios/storage/ceph/ceph-mgr')
class TestCephMgrScenarios(CephMgrTestsBase):
    """
    Scenario tests can be written using YAML templates that are auto-loaded
    into this test runner. This is the recommended way to write tests for
    scenarios. It is however still possible to write the tests in Python if
    required. See defs/tests/README.md for more info.
    """
