import os
import pathlib
import shutil
import subprocess
from unittest import mock

from hotsos.core.config import HotSOSConfig
from hotsos.core.plugins.juju.resources import JujuBase
from hotsos.plugin_extensions.juju import summary

from . import utils


class JujuTestsBase(utils.BaseTestCase):
    """ Custom base testcase that sets juju plugin context. """
    def setUp(self):
        super().setUp()
        HotSOSConfig.plugin_name = 'juju'


class TestJujuResources(JujuTestsBase):
    """ Unit tests for Juju resources. """
    def test_charm(self):
        charms = JujuBase().charms
        self.assertEqual(sorted(list(charms.keys())),
                         sorted(['nova-compute', 'neutron-openvswitch',
                                 'ceph-osd']))
        versions = [c.version for c in charms.values()]
        self.assertEqual(sorted(versions), [457, 508, 589])

    @utils.create_data_root({},
                            copy_from_original=[
                                    'var/lib/juju/agents/unit-nova-compute-0'])
    def test_charm_w_version_history(self):
        path = os.path.join(HotSOSConfig.data_root,
                            ('var/lib/juju/agents/unit-nova-compute-0/state/'
                             'deployer/manifests'))
        shutil.rmtree(path)
        os.makedirs(path)
        pathlib.Path(os.path.join(path, 'cs_3a_nova-compute-3')).touch()
        pathlib.Path(os.path.join(path, 'cs_3a_nova-compute-4')).touch()
        pathlib.Path(os.path.join(path, 'cs_3a_nova-compute-100')).touch()
        pathlib.Path(os.path.join(path, 'cs_3a_nova-compute-2')).touch()
        charms = JujuBase().charms
        self.assertEqual(list(charms.keys()), ['nova-compute'])
        versions = [c.version for c in charms.values()]
        self.assertEqual(sorted(versions), [100])

    @utils.create_data_root({'var/lib/juju/agents/machine-0/agent.conf':
                             'upgradedToVersion: 2.9.49'})
    def test_machine_version_bin_noexist(self):
        self.assertEqual(JujuBase().machine.version, '2.9.49')

    @mock.patch('hotsos.core.plugins.juju.resources.subprocess.check_output')
    @utils.create_data_root({'var/lib/juju/agents/machine-0/agent.conf':
                             'upgradedToVersion: xxx',
                             'var/lib/juju/tools/machine-0/jujud': ''})
    def test_machine_version_bin_exists(self, mock_check_output):
        mock_check_output.return_value = b'2.9.49\n'
        self.assertEqual(JujuBase().machine.version, '2.9.49')

    @mock.patch('hotsos.core.plugins.juju.resources.subprocess.check_output')
    @utils.create_data_root({'var/lib/juju/agents/machine-0/agent.conf':
                             'upgradedToVersion: xxx',
                             'var/lib/juju/tools/machine-0/jujud': ''})
    def test_machine_version_bin_error(self, mock_check_output):

        def fake_check_output(*args):
            raise subprocess.CalledProcessError(1, '')

        mock_check_output.side_effect = fake_check_output
        self.assertEqual(JujuBase().machine.version, 'xxx')


class TestJujuSummary(JujuTestsBase):
    """ Unit tests for Juju summary. """
    def test_summary_keys(self):
        inst = summary.JujuSummary()
        self.assertEqual(list(inst.output.keys()),
                         ['version',
                          'services',
                          'machine',
                          'units'])

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
        self.assertTrue(inst.is_runnable())
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
    required. See https://hotsos.readthedocs.io/en/latest/contrib/testing.html
    for more information.
    """
