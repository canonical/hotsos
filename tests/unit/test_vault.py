import utils

from plugins.vault.pyparts import (
    general,
)


class TestSystemPluginPartGeneral(utils.BaseTestCase):

    def test_install(self):
        inst = general.VaultInstallChecks()
        inst()
        self.assertEqual(inst.output, {'snaps': ['vault 1.5.4']})

    def test_services(self):
        expected = {'services': {
                        'ps': ['vault (1)'],
                        'systemd': {'indirect': ['vaultlocker-decrypt']}}
                    }
        inst = general.VaultServiceChecks()
        inst()
        self.assertEqual(inst.output, expected)
