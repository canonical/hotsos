import os

from tests.unit import utils

from hotsos.core.config import HotSOSConfig
from hotsos.plugin_extensions.pacemaker import summary


class TestPacemakerBase(utils.BaseTestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        HotSOSConfig.plugin_name = 'pacemaker'
        HotSOSConfig.data_root = os.path.join(utils.TESTS_DIR,
                                              'fake_data_root/vault')


class TestPacemakerSummary(TestPacemakerBase):
    def test_dpkg(self):
        expected = ['corosync 3.0.3-2ubuntu2.1',
                    'crmsh 4.2.0-2ubuntu1',
                    'pacemaker 2.0.3-3ubuntu4.3',
                    'pacemaker-cli-utils 2.0.3-3ubuntu4.3',
                    'pacemaker-common 2.0.3-3ubuntu4.3',
                    'pacemaker-resource-agents 2.0.3-3ubuntu4.3']
        inst = summary.PacemakerSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual["dpkg"], expected)

    def test_services(self):
        expected = {'ps': ['corosync (1)', 'pacemakerd (1)'],
                    'systemd': {
            'enabled': [
                'corosync',
                'pacemaker']
        }}
        inst = summary.PacemakerSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual["services"], expected)

    def test_offline_nodes(self):
        expected = ['node1']
        inst = summary.PacemakerSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual["nodes"]["offline"], expected)

    def test_online_nodes(self):
        expected = ['juju-04f1e3-0-lxd-5',
                    'juju-04f1e3-1-lxd-6',
                    'juju-04f1e3-2-lxd-6']
        inst = summary.PacemakerSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual["nodes"]["online"], expected)


@utils.load_templated_tests('scenarios/pacemaker')
class TestPacemakerScenarios(TestPacemakerBase):
    """
    Scenario tests can be written using YAML templates that are auto-loaded
    into this test runner. This is the recommended way to write tests for
    scenarios. It is however still possible to write the tests in Python if
    required. See defs/tests/README.md for more info.
    """
