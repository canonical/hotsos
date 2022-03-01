import os
import tempfile

import mock

from tests.unit import utils

from core.ycheck.bugs import YBugChecker
from core import known_bugs_utils
from plugins.juju.pyparts import summary

FAKE_PS = """root       615  0.0  0.0  21768   980 ?        Ss   Apr06   0:00 bash /etc/systemd/system/jujud-machine-0-lxd-11-exec-start.sh
root       731  0.0  0.0 2981484 81644 ?       Sl   Apr06  49:01 /var/lib/juju/tools/machine-0-lxd-11/jujud machine --data-dir /var/lib/juju --machine-id 0/lxd/11 --debug"""  # noqa


JOURNALCTL_CAPPEDPOSITIONLOST = """
Dec 21 14:07:53 juju-1 mongod.37017[17873]: [replication-18] CollectionCloner ns:juju.txns.log finished cloning with status: QueryPlanKilled: PlanExecutor killed: CappedPositionLost: CollectionScan died due to position in capped collection being deleted. Last seen record id: RecordId(204021366)
Dec 21 14:07:53 juju-1 mongod.37017[17873]: [replication-18] collection clone for 'juju.txns.log' failed due to QueryPlanKilled: While cloning collection 'juju.txns.log' there was an error 'PlanExecutor killed: CappedPositionLost: CollectionScan died due to position in capped collection being deleted. Last seen record id: RecordId(204021366)'
"""  # noqa

RABBITMQ_CHARM_LOGS = """
2021-02-17 08:18:44 ERROR juju.worker.dependency engine.go:671 "uniter" manifold worker returned unexpected error: failed to initialize uniter for "unit-rabbitmq-server-0": cannot create relation state tracker: cannot remove persisted state, relation 236 has members
2021-02-17 08:20:34 ERROR juju.worker.dependency engine.go:671 "uniter" manifold worker returned unexpected error: failed to initialize uniter for "unit-rabbitmq-server-0": cannot create relation state tracker: cannot remove persisted state, relation 236 has members
"""  # noqa


class JujuTestsBase(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        os.environ['PLUGIN_NAME'] = 'juju'


class TestJujuSummary(JujuTestsBase):

    def test_summary_keys(self):
        inst = summary.JujuSummary()
        self.assertEquals(list(inst.output.keys()),
                          ['charms',
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
        self.assertEquals(self.part_output_to_actual(inst.output)['services'],
                          expected)

    def test_machine_info(self):
        inst = summary.JujuSummary()
        self.assertTrue(inst.plugin_runnable)
        actual = self.part_output_to_actual(inst.output)
        self.assertEquals(actual['version'], '2.9.22')
        self.assertEquals(actual['machine'], '1')

    @mock.patch.object(summary, 'CLIHelper')
    def test_get_lxd_machine_info(self, mock_cli_helper):
        mock_helper = mock.MagicMock()
        mock_cli_helper.return_value = mock_helper
        mock_helper.ps.return_value = FAKE_PS.split('\n')
        with mock.patch('core.plugins.juju.JujuMachine') as m:
            mock_machine = mock.MagicMock()
            m.return_value = mock_machine
            mock_machine.id = '0-lxd-11'
            mock_machine.version = '2.9.9'
            inst = summary.JujuSummary()
            actual = self.part_output_to_actual(inst.output)
            self.assertEquals(actual['version'], '2.9.9')
            self.assertEquals(actual['machine'], '0-lxd-11')

    def test_charm_versions(self):
        expected = ['ceph-osd-508', 'neutron-openvswitch-457',
                    'nova-compute-589']
        inst = summary.JujuSummary()
        self.assertEquals(self.part_output_to_actual(inst.output)['charms'],
                          expected)

    def test_get_unit_info(self):
        expected = {'local': ['ceph-osd-0', 'neutron-openvswitch-1',
                              'nova-compute-0']}
        inst = summary.JujuSummary()
        self.assertEquals(self.part_output_to_actual(inst.output)['units'],
                          expected)


class TestJujuKnownBugs(JujuTestsBase):

    @mock.patch('core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('juju_core.yaml'))
    @mock.patch('core.ycheck.CLIHelper')
    def test_1852502(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.journalctl.return_value = \
            JOURNALCTL_CAPPEDPOSITIONLOST.splitlines(keepends=True)

        YBugChecker()()
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
        self.assertEqual(known_bugs_utils._get_known_bugs(), expected)

    @mock.patch('core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('juju_core.yaml'))
    def test_1910958(self):
        with tempfile.TemporaryDirectory() as dtmp:
            os.environ['DATA_ROOT'] = dtmp
            logfile = os.path.join(dtmp,
                                   'var/log/juju/unit-rabbitmq-server-0.log')
            os.makedirs(os.path.dirname(logfile))
            with open(logfile, 'w') as fd:
                fd.write(RABBITMQ_CHARM_LOGS)

            YBugChecker()()
            expected = {'bugs-detected':
                        [{'id': 'https://bugs.launchpad.net/bugs/1910958',
                          'desc':
                          ('Unit unit-rabbitmq-server-0 failed to start due '
                           'to members in relation 236 that cannot be '
                           'removed.'),
                          'origin': 'juju.01part'}]}
            self.assertEqual(known_bugs_utils._get_known_bugs(), expected)
