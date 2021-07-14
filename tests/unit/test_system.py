import utils

from plugins.system.pyparts import system


class TestSystemPluginPartSystem(utils.BaseTestCase):

    def test_get_service_info(self):
        expected = {'hostname': 'hothost',
                    'num-cpus': 72,
                    'os': 'ubuntu bionic',
                    'unattended-upgrades': 'ENABLED'}
        inst = system.SystemChecks()
        inst()
        self.assertEqual(inst.output, expected)
