import os

from tests.unit import utils

from plugins.vault.pyparts import general


class TestVaultPluginPartGeneral(utils.BaseTestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        os.environ['DATA_ROOT'] = os.path.join(utils.TESTS_DIR,
                                               'fake_data_root/vault')

    def test_install(self):
        inst = general.VaultInstallChecks()
        inst()
        self.assertEqual(inst.output, {'snaps': ['vault 1.5.9']})

    def test_services(self):
        expected = {'services': {
                        'ps': ['vault (1)'],
                        'systemd': {'enabled': ['vault',
                                                'vault-mysql-router']}}
                    }
        inst = general.VaultServiceChecks()
        inst()
        self.assertEqual(inst.output, expected)
