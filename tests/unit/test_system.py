import mock

import utils

utils.add_sys_plugin_path("system")
from plugins.system import (  # noqa E402
    _01system,
)


class TestSystemPlugin01system(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(_01system, "SYSTEM_INFO", {})
    def test_get_service_info(self):
        pass
