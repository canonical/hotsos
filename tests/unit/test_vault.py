import os

from . import utils

from hotsos.core.config import HotSOSConfig
from hotsos.plugin_extensions.vault import summary


class VaultTestsBase(utils.BaseTestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        HotSOSConfig.plugin_name = 'vault'
        HotSOSConfig.data_root = os.path.join(utils.TESTS_DIR,
                                              'fake_data_root/vault')


class TestVaultSummary(VaultTestsBase):

    def test_snaps(self):
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


@utils.load_templated_tests('scenarios/vault')
class TestVaultScenarios(VaultTestsBase):
    """
    Scenario tests can be written using YAML templates that are auto-loaded
    into this test runner. This is the recommended way to write tests for
    scenarios. It is however still possible to write the tests in Python if
    required. See defs/tests/README.md for more info.
    """
