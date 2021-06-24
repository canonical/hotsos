import utils

utils.add_sys_plugin_path("system")
from plugins.system.parts.pyparts import (  # noqa E402
    system,
)


class TestSystemPluginPartSystem(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    def test_get_service_info(self):
        expected = {'hostname': 'hothost',
                    'num-cpus': 72,
                    'os': 'ubuntu bionic',
                    'unattended-upgrades': 'ENABLED'}
        inst = system.SystemChecks()
        inst()
        self.assertEqual(inst.output, expected)
