import os

import mock

import utils

from core import checks
from core import known_bugs_utils

from plugins.juju.pyparts import (
    machines,
    charms,
    units,
)

FAKE_PS = """root       615  0.0  0.0  21768   980 ?        Ss   Apr06   0:00 bash /etc/systemd/system/jujud-machine-0-lxd-11-exec-start.sh
root       731  0.0  0.0 2981484 81644 ?       Sl   Apr06  49:01 /var/lib/juju/tools/machine-0-lxd-11/jujud machine --data-dir /var/lib/juju --machine-id 0/lxd/11 --debug"""  # noqa


class TestJujuPluginPartServices(utils.BaseTestCase):

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


class TestJujuPluginPartCharms(utils.BaseTestCase):

    def test_get_charm_versions(self):
        expected = {'charms': ['ceph-osd-495', 'neutron-openvswitch-443',
                               'nova-compute-564']}
        inst = charms.JujuCharmChecks()
        inst()
        self.assertTrue(inst.plugin_runnable)
        self.assertEquals(inst.output, expected)


class TestJujuPluginPartUnits(utils.BaseTestCase):

    def test_get_unit_info(self):
        expected = {'local': ['ceph-osd-1', 'neutron-openvswitch-1',
                              'nova-compute-0']}
        inst = units.JujuUnitChecks()
        inst()
        self.assertTrue(inst.plugin_runnable)
        self.assertEquals(inst.output, {"units": expected})


class TestJujuPluginPartKnown_bugs(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        os.environ["PLUGIN_NAME"] = "juju"

    def test_detect_known_bugs(self):
        checks.BugChecksBase()()
        expected = {'bugs-detected':
                    [{'id': 'https://bugs.launchpad.net/bugs/1910958',
                      'desc':
                      ('Unit unit-rabbitmq-server-2 failed to start due '
                       'to members in relation 236 that cannot be '
                       'removed.'),
                      'origin': 'juju.01part'}]}
        self.assertEqual(known_bugs_utils._get_known_bugs(), expected)
