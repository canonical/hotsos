import os
import tempfile

import mock

from . import utils

from hotsos.core.config import setup_config
from hotsos.core.ycheck.scenarios import YScenarioChecker
from hotsos.core import issues
from hotsos.plugin_extensions.juju import summary

JOURNALCTL_CAPPEDPOSITIONLOST = """
Dec 21 14:07:53 juju-1 mongod.37017[17873]: [replication-18] CollectionCloner ns:juju.txns.log finished cloning with status: QueryPlanKilled: PlanExecutor killed: CappedPositionLost: CollectionScan died due to position in capped collection being deleted. Last seen record id: RecordId(204021366)
Dec 21 14:07:53 juju-1 mongod.37017[17873]: [replication-18] collection clone for 'juju.txns.log' failed due to QueryPlanKilled: While cloning collection 'juju.txns.log' there was an error 'PlanExecutor killed: CappedPositionLost: CollectionScan died due to position in capped collection being deleted. Last seen record id: RecordId(204021366)'
"""  # noqa

RABBITMQ_CHARM_LOGS = """
2021-02-17 08:18:44 ERROR juju.worker.dependency engine.go:671 "uniter" manifold worker returned unexpected error: failed to initialize uniter for "unit-rabbitmq-server-0": cannot create relation state tracker: cannot remove persisted state, relation 236 has members
2021-02-17 08:20:34 ERROR juju.worker.dependency engine.go:671 "uniter" manifold worker returned unexpected error: failed to initialize uniter for "unit-rabbitmq-server-0": cannot create relation state tracker: cannot remove persisted state, relation 236 has members
"""  # noqa


UNIT_LEADERSHIP_ERROR = """
2021-09-16 10:28:25 WARNING leader-elected ERROR cannot write leadership settings: cannot write settings: failed to merge leadership settings: application "keystone": prerequisites failed: "keystone/2" is not leader of "keystone"
2021-09-16 10:28:47 WARNING leader-elected ERROR cannot write leadership settings: cannot write settings: failed to merge leadership settings: application "keystone": prerequisites failed: "keystone/2" is not leader of "keystone"
2021-09-16 10:29:06 WARNING leader-elected ERROR cannot write leadership settings: cannot write settings: failed to merge leadership settings: application "keystone": prerequisites failed: "keystone/2" is not leader of "keystone"
2021-09-16 10:29:53 WARNING leader-elected ERROR cannot write leadership settings: cannot write settings: failed to merge leadership settings: application "keystone": prerequisites failed: "keystone/2" is not leader of "keystone"
2021-09-16 10:30:41 WARNING leader-elected ERROR cannot write leadership settings: cannot write settings: failed to merge leadership settings: application "keystone": prerequisites failed: "keystone/2" is not leader of "keystone"
"""  # noqa


class JujuTestsBase(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        setup_config(PLUGIN_NAME='juju')


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

    @mock.patch('hotsos.core.plugins.juju.JujuMachine')
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


class TestJujuScenarios(JujuTestsBase):

    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('juju_core_bugs.yaml'))
    @mock.patch('hotsos.core.ycheck.CLIHelper')
    def test_1852502(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.journalctl.return_value = \
            JOURNALCTL_CAPPEDPOSITIONLOST.splitlines(keepends=True)

        YScenarioChecker()()
        mock_helper.return_value.journalctl.assert_called_with(
                                                            unit='juju-db')
        msg_1852502 = ('known mongodb bug identified - '
                       'https://jira.mongodb.org/browse/TOOLS-1636 '
                       'Workaround is to pass --no-logs to juju '
                       'create-backup. This is an issue only with Mongo '
                       '3. Mongo 4 does not have this issue. Upstream is '
                       'working on migrating to Mongo 4 in the Juju 3.0 '
                       'release.')
        expected = {'bugs-detected':
                    [{'id': 'https://bugs.launchpad.net/bugs/1852502',
                      'desc': msg_1852502,
                      'origin': 'juju.01part'}]}
        self.assertEqual(issues.IssuesManager().load_bugs(), expected)

    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('juju_core_bugs.yaml'))
    def test_1910958(self):
        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(DATA_ROOT=dtmp)
            logfile = os.path.join(dtmp,
                                   'var/log/juju/unit-rabbitmq-server-0.log')
            os.makedirs(os.path.dirname(logfile))
            with open(logfile, 'w') as fd:
                fd.write(RABBITMQ_CHARM_LOGS)

            YScenarioChecker()()
            expected = {'bugs-detected':
                        [{'id': 'https://bugs.launchpad.net/bugs/1910958',
                          'desc':
                          ('Unit unit-rabbitmq-server-0 failed to start due '
                           'to members in relation 236 that cannot be '
                           'removed.'),
                          'origin': 'juju.01part'}]}
            self.assertEqual(issues.IssuesManager().load_bugs(),
                             expected)

    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('jujud_checks.yaml'))
    @mock.patch('hotsos.core.ycheck.ServiceChecksBase.processes', {})
    @mock.patch('hotsos.core.issues.IssuesManager.add')
    def test_jujud_checks(self, mock_add_issue):
        raised_issues = {}

        def fake_add_issue(issue, **_kwargs):
            if type(issue) in raised_issues:
                raised_issues[type(issue)].append(issue.msg)
            else:
                raised_issues[type(issue)] = [issue.msg]

        mock_add_issue.side_effect = fake_add_issue

        YScenarioChecker()()
        self.assertEqual(len(raised_issues), 1)
        msg = ('No jujud processes found running on this host but it seems '
               'there should be since Juju is installed.')
        self.assertEqual(list(raised_issues.values())[0], [msg])

    @mock.patch('hotsos.core.ycheck.CLIHelper')
    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('juju_unit_checks.yaml'))
    @mock.patch('hotsos.core.issues.IssuesManager.add')
    def test_unit_checks(self, mock_add_issue, mock_cli):
        raised_issues = {}

        def fake_add_issue(issue, **_kwargs):
            if type(issue) in raised_issues:
                raised_issues[type(issue)].append(issue.msg)
            else:
                raised_issues[type(issue)] = [issue.msg]

        mock_add_issue.side_effect = fake_add_issue

        mock_cli.return_value = mock.MagicMock()

        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(DATA_ROOT=dtmp)
            logfile = os.path.join(dtmp,
                                   'var/log/juju/unit-keystone-2.log')
            os.makedirs(os.path.dirname(logfile))
            with open(logfile, 'w') as fd:
                fd.write(UNIT_LEADERSHIP_ERROR)

            # first try outside age limit
            mock_cli.return_value.date.return_value = "2021-09-25 00:00:00"
            YScenarioChecker()()
            self.assertEqual(len(raised_issues), 0)

            # then within
            mock_cli.return_value.date.return_value = "2021-09-17 00:00:00"
            YScenarioChecker()()
            self.assertEqual(len(raised_issues), 1)
            msg = ("Juju unit(s) 'keystone' are showing leadership errors in "
                   "their logs from the last 7 days. Please investigate.")
            self.assertEqual(list(raised_issues.values())[0], [msg])
