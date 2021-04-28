import mock

import utils

utils.add_sys_plugin_path("system")
from plugins.system import (  # noqa E402
    system,
)


class TestSystemPlugin01system(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(system, "SYSTEM_INFO", {})
    def test_get_service_info(self):
        expected = {'hostname': 'hothost',
                    'num-cpus': 72,
                    'os': 'ubuntu bionic',
                    'unattended-upgrades': 'ENABLED'}
        system.get_system_checks()()
        self.assertEqual(system.SYSTEM_INFO, expected)
