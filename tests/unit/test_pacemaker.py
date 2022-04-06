import os

import mock

from tests.unit import utils

from hotsos.core.config import setup_config, HotSOSConfig
from hotsos.core.ycheck.scenarios import YScenarioChecker
from hotsos.plugin_extensions.pacemaker import summary


class TestPacemakerBase(utils.BaseTestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        setup_config(PLUGIN_NAME='pacemaker',
                     DATA_ROOT=os.path.join(utils.TESTS_DIR,
                                            'fake_data_root/vault'))


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


class TestPacemakerScenarios(TestPacemakerBase):
    @mock.patch('hotsos.core.plugins.pacemaker.CLIHelper')
    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('pacemaker_node1_found.yaml'))
    @mock.patch('hotsos.core.issues.IssuesManager.add')
    def test_node1_found(self, mock_add_issue, mock_helper):
        raised_issues = []

        def fake_add_issue(issue, **_kwargs):
            raised_issues.append(issue)

        mock_helper.return_value = mock.MagicMock()
        test_data_path = ('sos_commands/pacemaker/crm_status')
        crm_status_path = os.path.join(HotSOSConfig.DATA_ROOT,
                                       test_data_path)
        with open(crm_status_path) as crm_status:
            mock_helper.return_value.pacemaker_crm_status.\
                return_value = crm_status

            mock_add_issue.side_effect = fake_add_issue
            YScenarioChecker()()
            self.assertTrue(mock_add_issue.called)
            msg = (
                'A node with the hostname node1 is currently configured and '
                'enabled on pacemaker. This is caused by a known bug and you '
                'can remove the node by running the following command on the '
                'application-hacluster leader: '
                'juju run-action '
                '<application>-hacluster/leader '
                'delete-node-from-ring node=node1 --wait\n'
                'If the above action is not available in the charm, you can '
                'run the following command: '
                'juju run --application <application>-hacluster -- '
                'sudo crm_node -R node1 --force')
            msgs = [issue.msg for issue in raised_issues]
            self.assertEqual(len(msgs), 1)
            self.assertEqual(msgs, [msg])
