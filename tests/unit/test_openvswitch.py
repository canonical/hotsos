import os
import tempfile

import mock

from tests.unit import utils

from core import known_bugs_utils
from core.plugins import openvswitch
from core.ycheck.bugs import YBugChecker
from plugins.openvswitch.pyparts import (
    event_checks,
    service_info,
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
        os.environ["PLUGIN_NAME"] = "openvswitch"


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
        expected = {'dpkg':
                    ['libc-bin 2.31-0ubuntu9.2',
                     'openvswitch-switch 2.13.3-0ubuntu0.20.04.2']}

        inst = service_info.OpenvSwitchPackageChecks()
        inst()
        self.assertEqual(inst.output, expected)

    def test_get_resource_checks(self):
        expected = {'services': {
                        'systemd': {
                            'enabled': [
                                'openvswitch-switch'
                                ],
                            'static': [
                                'ovs-vswitchd', 'ovsdb-server'
                                ]
                            },
                        'ps': [
                            'ovs-vswitchd (1)', 'ovsdb-client (1)',
                            'ovsdb-server (1)']}}
        inst = service_info.OpenvSwitchServiceChecks()
        inst()
        self.assertEqual(inst.output, expected)

    def test_bridge_checks(self):
        expected = {'bridges': {'br-data': [
                                    {'ens7': {
                                        'addresses': [],
                                        'hwaddr': '52:54:00:78:19:c3',
                                        'state': 'UP',
                                        'speed': 'Unknown!'}}],
                                'br-ex': [],
                                'br-int': ['(6 ports)'],
                                'br-tun': ['vxlan-0a000072',
                                           'vxlan-0a000085']}}

        inst = service_info.OpenvSwitchBridgeChecks()
        inst()
        self.assertEqual(inst.output, expected)


class TestOpenvswitchBugChecks(TestOpenvswitchBase):

    @mock.patch('core.plugins.openvswitch.OpenvSwitchChecksBase.'
                'plugin_runnable', True)
    @mock.patch('core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('ovn.yaml'))
    def test_1917475(self):
        with tempfile.TemporaryDirectory() as dtmp:
            os.environ['DATA_ROOT'] = dtmp
            logfile = os.path.join(dtmp, 'var/log/ovn/ovn-controller.log')
            os.makedirs(os.path.dirname(logfile))
            with open(logfile, 'w') as fd:
                fd.write(LP1917475_LOG)

            YBugChecker()()
            expected = {'bugs-detected':
                        [{'id': 'https://bugs.launchpad.net/bugs/1917475',
                          'desc': "known ovn bug identified - db rbac errors",
                          'origin': 'openvswitch.01part'}]}
            self.assertEqual(known_bugs_utils._get_known_bugs(), expected)

    @mock.patch('core.checks.CLIHelper')
    @mock.patch('core.plugins.openvswitch.OpenvSwitchChecksBase.'
                'plugin_runnable', True)
    @mock.patch('core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('libc-bin.yaml'))
    def test_1839592(self, mock_cli):
        mock_cli.return_value = mock.MagicMock()
        mock_cli.return_value.dpkg_l.return_value = \
            ["ii  libc-bin 2.26-3ubuntu1.3 amd64"]

        YBugChecker()()
        expected = {'bugs-detected':
                    [{'id': 'https://bugs.launchpad.net/bugs/1839592',
                      'desc': "installed package 'libc-bin' with version "
                              "2.26-3ubuntu1.3 has a known critical bug which "
                              "causes ovs deadlocks. If this environment is "
                              "using OVS it should be upgraded asap.",
                      'origin': 'openvswitch.01part'}]}
        self.assertEqual(known_bugs_utils._get_known_bugs(), expected)


class TestOpenvswitchEventChecks(TestOpenvswitchBase):

    def test_common_checks(self):
        expected = {'daemon-checks': {
                        'ovs-vswitchd': {
                            'bridge-no-such-device': {
                                '2022-02-10': {'tap6a0486f9-82': 1}}},
                        'logs': {
                            'ovs-vswitchd': {
                                'WARN': {
                                    '2022-02-04': 56,
                                    '2022-02-09': 24,
                                    '2022-02-10': 6}},
                            'ovsdb-server': {
                                'WARN': {'2022-02-04': 6,
                                         '2022-02-09': 2,
                                         '2022-02-10': 4}}}}}
        inst = event_checks.OpenvSwitchDaemonEventChecks()
        inst()
        self.assertEqual(inst.output, expected)

    @mock.patch('core.ycheck.CLIHelper')
    def test_dp_checks(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.ovs_appctl_dpctl_show.return_value = \
            DPCTL_SHOW
        expected = {'flow-checks': {
                        'datapath-port-stats': {
                            'qr-aa623763-fd': {
                                'RX': {
                                    'dropped': 1394875,
                                    'packets': 309
                                    }}}}}
        inst = event_checks.OpenvSwitchFlowEventChecks()
        inst()
        self.assertEqual(inst.output, expected)
