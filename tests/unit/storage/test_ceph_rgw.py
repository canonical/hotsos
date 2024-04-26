
from hotsos.core.config import HotSOSConfig

from .. import utils


class StorageCephRGWTestsBase(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        HotSOSConfig.plugin_name = 'storage'


@utils.load_templated_tests('scenarios/storage/ceph/ceph-rgw')
class TestCephRGWScenarios(StorageCephRGWTestsBase):
    """
    Scenario tests can be written using YAML templates that are auto-loaded
    into this test runner. This is the recommended way to write tests for
    scenarios. It is however still possible to write the tests in Python if
    required. See https://hotsos.readthedocs.io/en/latest/contrib/testing.html
    for more information.
    """
