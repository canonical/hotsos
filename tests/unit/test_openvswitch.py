import os
import tempfile

import mock

from . import utils

from hotsos.core import issues
from hotsos.core.config import setup_config
from hotsos.core.plugins import openvswitch
from hotsos.core.ycheck.scenarios import YScenarioChecker
from hotsos.plugin_extensions.openvswitch import (
    event_checks,
    summary,
)

LP1917475_LOG = r"""
2021-09-22T01:13:33.307Z|00266|ovsdb_idl|WARN|transaction error: {"details":"RBAC rules for client \"compute5\" role \"ovn-controller\" prohibit row insertion into table \"IGMP_Group\".","error":"permission error"}
"""  # noqa

DPCTL_SHOW = r"""
  port 6: br-int (internal)
    RX packets:0 errors:0 dropped:1887 overruns:0 frame:0
    TX packets:0 errors:0 dropped:0 aborted:0 carrier:0
    collisions:0
    RX bytes:0  TX bytes:0
  port 7: qr-aa623763-fd (internal)
    RX packets:309 errors:0 dropped:1394875 overruns:0 frame:0
    TX packets:66312 errors:0 dropped:0 aborted:0 carrier:0
    collisions:0
    RX bytes:529676 (517.3 KiB)  TX bytes:114369124 (109.1 MiB)
  port 8: sg-6df85cb0-c0 (internal)
    RX packets:78 errors:0 dropped:0 overruns:0 frame:0
    TX packets:51 errors:0 dropped:0 aborted:0 carrier:0
    collisions:0
    RX bytes:7878 (7.7 KiB)  TX bytes:5026 (4.9 KiB)
"""  # noqa


class TestOpenvswitchBase(utils.BaseTestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        setup_config(PLUGIN_NAME='openvswitch')


class TestCoreOpenvSwitch(TestOpenvswitchBase):

    def testBase_offload_disabled(self):
        enabled = openvswitch.OpenvSwitchBase().offload_enabled
        self.assertFalse(enabled)

    def testBase_offload_enabled(self):
        with mock.patch.object(openvswitch, 'CLIHelper') as mock_cli:
            mock_cli.return_value = mock.MagicMock()
            f = mock_cli.return_value.ovs_vsctl_get_Open_vSwitch
            f.return_value = '{hw-offload="true", max-idle="30000"}'
            enabled = openvswitch.OpenvSwitchBase().offload_enabled
            self.assertTrue(enabled)


class TestOpenvswitchServiceInfo(TestOpenvswitchBase):

    def test_get_package_checks(self):
        expected = ['libc-bin 2.31-0ubuntu9.2',
                    'openvswitch-switch 2.13.3-0ubuntu0.20.04.2']
        inst = summary.OpenvSwitchSummary()
        self.assertEqual(self.part_output_to_actual(inst.output)['dpkg'],
                         expected)

    def test_get_resource_checks(self):
        expected = {'systemd': {
                        'enabled': [
                            'openvswitch-switch'
                            ],
                        'static': [
                            'ovs-vswitchd', 'ovsdb-server'
                            ]
                        },
                    'ps': [
                        'ovs-vswitchd (1)',
                        'ovsdb-server (1)']}
        inst = summary.OpenvSwitchSummary()
        self.assertEqual(self.part_output_to_actual(inst.output)['services'],
                         expected)

    def test_bridge_checks(self):
        expected = {'br-data': [
                        {'ens7': {
                            'addresses': [],
                            'hwaddr': '52:54:00:78:19:c3',
                            'state': 'UP',
                            'speed': 'Unknown!'}}],
                    'br-ex': [],
                    'br-int': ['(6 ports)'],
                    'br-tun': ['vxlan-0a000072',
                               'vxlan-0a000085']}

        inst = summary.OpenvSwitchSummary()
        self.assertEqual(self.part_output_to_actual(inst.output)['bridges'],
                         expected)


class TestOpenvswitchEventChecks(TestOpenvswitchBase):

    def test_common_checks(self):
        expected = {
            'ovs-vswitchd': {
               'bridge-no-such-device': {
                    '2022-02-10': {'tap6a0486f9-82': 1}}},
            'logs': {
                'ovn-controller-unreasonably-long-poll-interval': {
                    '2022-02-16': 1,
                    '2022-02-17': 1},
                'ovsdb-server-nb-inactivity-probe': {
                    '2022-02-16': {
                        '10.130.11.109': 1},
                    '2022-02-17': {
                        '10.130.11.115': 1}},
                'ovsdb-server-nb-unreasonably-long-poll-interval': {
                    '2022-02-16': 2,
                    '2022-02-17': 1},
                'ovsdb-server-sb-inactivity-probe': {
                    '2022-02-16': {
                        '10.130.11.109': 1,
                        '10.130.11.110': 1},
                    '2022-02-17': {
                        '10.130.11.109': 1,
                        '10.130.11.110': 1}},
                'ovsdb-server-sb-unreasonably-long-poll-interval': {
                    '2022-02-16': 2,
                    '2022-02-17': 3},
                'ovs-thread-unreasonably-long-poll-interval': {
                    '2022-02-10': 3},
                'ovs-vswitchd': {
                    'WARN': {
                        '2022-02-04': 56,
                        '2022-02-09': 24,
                        '2022-02-10': 12}},
                'ovsdb-server': {
                    'WARN': {
                        '2022-02-04': 6,
                        '2022-02-09': 2,
                        '2022-02-10': 4}},
                'ovn-controller': {
                    'ERR': {'2022-02-16': 2},
                    'WARN': {
                        '2022-02-16': 4,
                        '2022-02-17': 5}},
                'ovn-northd': {
                    'ERR': {
                        '2022-02-16': 1,
                        '2022-02-17': 1},
                    'WARN': {
                        '2022-02-16': 1,
                        '2022-02-17': 1}},
                'ovsdb-server-nb': {
                    'ERR': {
                        '2022-02-16': 1,
                        '2022-02-17': 1},
                    'WARN': {
                        '2022-02-16': 12,
                        '2022-02-17': 17}},
                'ovsdb-server-sb': {
                    'ERR': {
                        '2022-02-16': 2,
                        '2022-02-17': 2},
                    'WARN': {
                        '2022-02-16': 23,
                        '2022-02-17': 23}}}}
        inst = event_checks.OpenvSwitchDaemonEventChecks()
        self.assertEqual(self.part_output_to_actual(inst.output), expected)

    @mock.patch('hotsos.core.ycheck.CLIHelper')
    def test_dp_checks(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.ovs_appctl_dpctl_show.return_value = \
            DPCTL_SHOW
        expected = {'datapath-port-stats': {
                        'qr-aa623763-fd': {
                            'RX': {
                                'dropped': 1394875,
                                'packets': 309
                                }}}}
        inst = event_checks.OpenvSwitchFlowEventChecks()
        self.assertEqual(self.part_output_to_actual(inst.output), expected)


class TestOpenvswitchScenarioChecks(TestOpenvswitchBase):

    @mock.patch('hotsos.core.plugins.openvswitch.OpenvSwitchChecksBase.'
                'plugin_runnable', True)
    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('ovn_bugs.yaml'))
    def test_1917475(self):
        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(DATA_ROOT=dtmp)
            logfile = os.path.join(dtmp, 'var/log/ovn/ovn-controller.log')
            os.makedirs(os.path.dirname(logfile))
            with open(logfile, 'w') as fd:
                fd.write(LP1917475_LOG)

            YScenarioChecker()()
            expected = {'bugs-detected':
                        [{'id': 'https://bugs.launchpad.net/bugs/1917475',
                          'desc': "known ovn bug identified - db rbac errors",
                          'origin': 'openvswitch.01part'}]}
            self.assertEqual(issues.IssuesManager().load_bugs(),
                             expected)

    @mock.patch('hotsos.core.checks.CLIHelper')
    @mock.patch('hotsos.core.plugins.openvswitch.OpenvSwitchChecksBase.'
                'plugin_runnable', True)
    @mock.patch('hotsos.core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('ovs_bugs.yaml'))
    def test_1839592(self, mock_cli):
        mock_cli.return_value = mock.MagicMock()
        mock_cli.return_value.dpkg_l.return_value = \
            ["ii  libc-bin 2.26-3ubuntu1.3 amd64"]

        YScenarioChecker()()
        expected = {'bugs-detected':
                    [{'id': 'https://bugs.launchpad.net/bugs/1839592',
                      'desc': "Installed package 'libc-bin' with version "
                              "2.26-3ubuntu1.3 has a known critical bug which "
                              "causes ovs deadlocks. If this environment is "
                              "using OVS it should be upgraded asap.",
                      'origin': 'openvswitch.01part'}]}
        self.assertEqual(issues.IssuesManager().load_bugs(), expected)
