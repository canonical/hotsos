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
                         ['charm-repo-info',
                          'charms',
                          'machine',
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

    def test_charm_versions(self):
        expected = ['ceph-osd-508', 'neutron-openvswitch-457',
                    'nova-compute-589']
        inst = summary.JujuSummary()
        self.assertEqual(self.part_output_to_actual(inst.output)['charms'],
                         expected)

    def test_get_unit_info(self):
        expected = {'local': ['ceph-osd-0', 'neutron-openvswitch-1',
                              'nova-compute-0']}
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
