import os

import mock

import utils

from core.ycheck.bugs import YBugChecker
from core import known_bugs_utils

from plugins.juju.pyparts import (
    machines,
    charms,
    units,
    service_info,
)

FAKE_PS = """root       615  0.0  0.0  21768   980 ?        Ss   Apr06   0:00 bash /etc/systemd/system/jujud-machine-0-lxd-11-exec-start.sh
root       731  0.0  0.0 2981484 81644 ?       Sl   Apr06  49:01 /var/lib/juju/tools/machine-0-lxd-11/jujud machine --data-dir /var/lib/juju --machine-id 0/lxd/11 --debug"""  # noqa


JOURNALCTL_CAPPEDPOSITIONLOST = """
Dec 21 14:07:53 juju-1 mongod.37017[17873]: [replication-18] CollectionCloner ns:juju.txns.log finished cloning with status: QueryPlanKilled: PlanExecutor killed: CappedPositionLost: CollectionScan died due to position in capped collection being deleted. Last seen record id: RecordId(204021366)
Dec 21 14:07:53 juju-1 mongod.37017[17873]: [replication-18] collection clone for 'juju.txns.log' failed due to QueryPlanKilled: While cloning collection 'juju.txns.log' there was an error 'PlanExecutor killed: CappedPositionLost: CollectionScan died due to position in capped collection being deleted. Last seen record id: RecordId(204021366)'
"""  # noqa


class JujuTestsBase(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        os.environ['PLUGIN_NAME'] = 'juju'


class TestJujuServiceInfo(JujuTestsBase):

    def test_service_info(self):
        expected = {'services': {
                        'ps': ['jujud (6)'],
                        'systemd': {
                            'enabled': ['jujud-machine-1']}
                        }
                    }
        inst = service_info.JujuServiceInfo()
        inst()
        self.assertEquals(inst.output, expected)


class TestJujuMachines(JujuTestsBase):

    def test_get_machine_info(self):
        expected = {'machine': '1',
                    'version': '2.9.8'}
        inst = machines.JujuMachineChecks()
        inst.get_machine_info()
        self.assertTrue(inst.plugin_runnable)
        self.assertEquals(inst.output, expected)

    @mock.patch.object(machines, 'CLIHelper')
    def test_get_lxd_machine_info(self, mock_cli_helper):
        mock_helper = mock.MagicMock()
        mock_cli_helper.return_value = mock_helper
        mock_helper.ps.return_value = FAKE_PS.split('\n')
        expected = {'machine': '0-lxd-11',
                    'version': '2.9.9'}

        with mock.patch('core.plugins.juju.JujuMachine') as m:
            mock_machine = mock.MagicMock()
            m.return_value = mock_machine
            mock_machine.id = '0-lxd-11'
            mock_machine.version = '2.9.9'
            inst = machines.JujuMachineChecks()
            self.assertTrue(inst.plugin_runnable)
            inst.get_machine_info()

        self.assertEquals(inst.output, expected)


class TestJujuCharms(JujuTestsBase):

    def test_get_charm_versions(self):
        expected = {'charms': ['ceph-osd-495', 'neutron-openvswitch-443',
                               'nova-compute-564']}
        inst = charms.JujuCharmChecks()
        inst()
        self.assertTrue(inst.plugin_runnable)
        self.assertEquals(inst.output, expected)


class TestJujuUnits(JujuTestsBase):

    def test_get_unit_info(self):
        expected = {'local': ['ceph-osd-1', 'neutron-openvswitch-1',
                              'nova-compute-0']}
        inst = units.JujuUnitChecks()
        inst()
        self.assertTrue(inst.plugin_runnable)
        self.assertEquals(inst.output, {"units": expected})


class TestJujuKnownBugs(JujuTestsBase):

    @mock.patch('core.ycheck.CLIHelper')
    def test_detect_known_bugs(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.journalctl.return_value = \
            JOURNALCTL_CAPPEDPOSITIONLOST.splitlines(keepends=True)
        YBugChecker()()
        mock_helper.return_value.journalctl.assert_called_with(unit='juju-db')
        msg_1852502 = ('known mongodb bug identified - '
                       'https://jira.mongodb.org/browse/TOOLS-1636 '
                       'Workaround is to pass --no-logs to juju '
                       'create-backup. This is an issue only with Mongo '
                       '3. Mongo 4 does not have this issue. Upstream is '
                       'working on migrating to Mongo 4 in the Juju 3.0 '
                       'release.')
        expected = {'bugs-detected':
                    [{'id': 'https://bugs.launchpad.net/bugs/1910958',
                      'desc':
                      ('Unit unit-rabbitmq-server-2 failed to start due '
                       'to members in relation 236 that cannot be '
                       'removed.'),
                      'origin': 'juju.01part'},
                     {'id': 'https://bugs.launchpad.net/bugs/1852502',
                      'desc': msg_1852502,
                      'origin': 'juju.01part'}]}
        self.assertEqual(known_bugs_utils._get_known_bugs(), expected)
