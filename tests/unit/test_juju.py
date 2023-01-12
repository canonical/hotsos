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
                        'logs': {'warning': {
                                    'server.go': {'2022-02-04': 14,
                                                  '2022-02-09': 19,
                                                  '2022-02-10': 197}}}},
                    'neutron-openvswitch/1': {
                        'charm': {'name': 'neutron-openvswitch',
                                  'repo-info': '9951bee',
                                  'version': 457},
                        'logs': {'warning': {
                                    'server.go': {
                                        '2022-02-04': 346,
                                        '2022-02-09': 160,
                                        '2022-02-10': 1950}}}},
                    'nova-compute/0': {
                        'charm': {
                            'name': 'nova-compute',
                            'repo-info': 'fcddc4a', 'version': 589},
                        'logs': {'warning': {
                                    'server.go': {'2022-02-04': 115,
                                                  '2022-02-09': 50,
                                                  '2022-02-10': 392}}}}}

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
