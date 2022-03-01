import os

from tests.unit import utils

from plugins.vault.pyparts import summary


class TestVaultPluginPartGeneral(utils.BaseTestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        os.environ['DATA_ROOT'] = os.path.join(utils.TESTS_DIR,
                                               'fake_data_root/vault')

    def test_install(self):
        inst = summary.VaultSummary()
        self.assertEqual(self.part_output_to_actual(inst.output)['snaps'],
                         ['vault 1.5.9'])

    def test_services(self):
        # TODO: this needs fixing - the pid is not identifiable
        # under the vault.service but instead under a .scope of
        #
        # snap.vault.vault
        expected = {'ps': [],
                    'systemd': {
                        'enabled': [
                            'vault',
                            'vault-mysql-router']
                        }}
        inst = summary.VaultSummary()
        self.assertEqual(self.part_output_to_actual(inst.output)['services'],
                         expected)
