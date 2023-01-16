from unittest import mock

from . import utils

from hotsos.core.config import HotSOSConfig
from hotsos.plugin_extensions.juju import summary


class JujuTestsBase(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        HotSOSConfig.plugin_name = 'juju'


class TestJujuSummary(JujuTestsBase):

    def test_summary_keys(self):
        inst = summary.JujuSummary()
        self.assertEqual(list(inst.output.keys()),
                         ['machine',
                          'services',
                          'units',
                          'version'])

    def test_service_info(self):
        expected = {'ps': ['jujud (1)'],
                    'systemd': {
                        'enabled': ['jujud-machine-1']}
                    }
        inst = summary.JujuSummary()
        self.assertEqual(self.part_output_to_actual(inst.output)['services'],
                         expected)

    def test_machine_info(self):
        inst = summary.JujuSummary()
        self.assertTrue(inst.plugin_runnable)
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['version'], '2.9.22')
        self.assertEqual(actual['machine'], '1')

    @mock.patch('hotsos.core.plugins.juju.resources.JujuMachine')
    def test_get_lxd_machine_info(self, mock_machine):
        mock_machine.return_value = mock.MagicMock()
        mock_machine.return_value.id = '0-lxd-11'
        mock_machine.return_value.version = '2.9.9'
        inst = summary.JujuSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['version'], '2.9.9')
        self.assertEqual(actual['machine'], '0-lxd-11')

    def test_get_unit_info(self):
        expected = {'ceph-osd/0': {
                        'charm': {
                            'name': 'ceph-osd',
                            'repo-info': 'a5e0c6e',
                            'version': 508},
                        'logs': {
                            'warning': {
                                'config-changed': {
                                    'logger.go': {'2022-02-04': 3}},
                                'juju-log': {'server.go': {
                                    '2022-02-04': 14,
                                    '2022-02-09': 19,
                                    '2022-02-10': 197}},
                                'operation': {
                                    'leader.go': {
                                        '2022-02-09': 1}},
                                'secrets-storage-relation-changed': {
                                    'logger.go': {
                                        '2022-02-04': 51}}}}},
                    'neutron-openvswitch/1': {
                        'charm': {
                            'name': 'neutron-openvswitch',
                            'repo-info': '9951bee',
                            'version': 457},
                        'logs': {
                            'warning': {
                                'config-changed': {
                                    'logger.go': {'2022-02-04': 2}},
                                'install': {
                                    'logger.go': {'2022-02-04': 1}},
                                'juju-log': {'server.go':
                                             {'2022-02-04': 346,
                                              '2022-02-09': 160,
                                              '2022-02-10': 1950}},
                                'neutron-plugin-api-relation-changed': {
                                    'logger.go': {'2022-02-04': 7}},
                                'neutron-plugin-relation-changed': {
                                    'logger.go': {'2022-02-04': 4}},
                                'neutron-plugin-relation-joined': {
                                    'logger.go': {'2022-02-04': 1}},
                                'operation': {
                                    'leader.go': {'2022-02-09': 1}}}}},
                    'nova-compute/0': {
                        'charm': {
                            'name': 'nova-compute',
                            'repo-info': 'fcddc4a', 'version': 589},
                        'logs': {
                            'error': {
                                'operation': {
                                    'runhook.go': {'2022-02-04': 12,
                                                   '2022-02-09': 6}}},
                            'warning': {
                                'ceph-relation-changed': {
                                    'logger.go': {'2022-02-04': 1}},
                                'cloud-compute-relation-changed': {
                                    'logger.go': {'2022-02-04': 28}},
                                'config-changed': {
                                    'logger.go': {'2022-02-04': 5}},
                                'install': {'logger.go': {'2022-02-04': 1}},
                                'juju-log': {'server.go': {
                                    '2022-02-04': 115,
                                    '2022-02-09': 50,
                                    '2022-02-10': 392}},
                                'secrets-storage-relation-changed': {
                                    'logger.go': {'2022-02-04': 10}},
                                'start': {'logger.go': {
                                    '2022-02-04': 1, '2022-02-09': 1}},
                                'update-status': {'logger.go': {
                                    '2022-02-04': 1013,
                                    '2022-02-09': 519,
                                    '2022-02-10': 195}}}}}}

        inst = summary.JujuSummary()
        self.assertEqual(self.part_output_to_actual(inst.output)['units'],
                         expected)


@utils.load_templated_tests('scenarios/juju')
class TestJujuScenarios(JujuTestsBase):
    """
    Scenario tests can be written using YAML templates that are auto-loaded
    into this test runner. This is the recommended way to write tests for
    scenarios. It is however still possible to write the tests in Python if
    required. See defs/tests/README.md for more info.
    """
