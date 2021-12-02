import os

import mock

import utils

from core.plugins import openvswitch
from core.ycheck.bugs import YBugChecker
from core.ycheck.packages import YPackageChecker
from plugins.openvswitch.pyparts import (
    event_checks,
    service_info,
)


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
                     'openvswitch-switch 2.13.3-0ubuntu0.20.04.1']}

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
                                        'state': 'UP'}}],
                                'br-ex': [],
                                'br-int': ['(7 ports)'],
                                'br-tun': ['vxlan-0a000032',
                                           'vxlan-0a000030']}}

        inst = service_info.OpenvSwitchBridgeChecks()
        inst()
        self.assertEqual(inst.output, expected)


class TestOpenvswitchBugChecks(TestOpenvswitchBase):

    @mock.patch('core.ycheck.bugs.add_known_bug')
    def test_bug_checks(self, mock_add_known_bug):
        bugs = []

        def fake_add_bug(*args, **kwargs):
            bugs.append((args, kwargs))

        mock_add_known_bug.side_effect = fake_add_bug
        YBugChecker()()
        calls = [mock.call('1917475',
                           'known ovn bug identified - db rbac errors')]
        mock_add_known_bug.assert_has_calls(calls, any_order=True)
        self.assertEqual(len(bugs), 1)


class TestOpenvswitchEventChecks(TestOpenvswitchBase):

    def test_common_checks(self):

        expected = {'daemon-checks': {
                        'ovs-vswitchd': {
                            'netdev-linux-no-such-device': {
                                '2021-07-19': {'tap4b02cb1d-8b': 1}},
                            'bridge-no-such-device': {'2021-06-29':
                                                      {'tapd4b5494a-b1': 1}}},
                        'logs': {
                            'ovs-thread-unreasonably-long-poll-interval': {
                                '2021-08-19': 2},
                            'ovs-vswitchd': {
                                'WARN': {'2021-06-29': 1,
                                         '2021-07-19': 1,
                                         '2021-08-19': 2}},
                            'ovsdb-server': {'ERR': {'2021-07-16': 1},
                                             'WARN': {'2021-07-28': 1}}}}}
        inst = event_checks.OpenvSwitchDaemonEventChecks()
        inst()
        self.assertEqual(inst.output, expected)

    def test_dp_checks(self):
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


class TestOpenstackPackageChecks(TestOpenvswitchBase):

    @mock.patch('core.ycheck.packages.add_known_bug')
    def test_pkgbugchecks_no_issue(self, mock_add_known_bug):
        YPackageChecker()()
        self.assertFalse(mock_add_known_bug.called)

    @mock.patch('core.checks.CLIHelper')
    @mock.patch('core.ycheck.packages.add_known_bug')
    @mock.patch('core.plugins.openstack.OpenstackBase.release_name', 'queens')
    def test_pkgbugchecks_w_issue(self, mock_add_known_bug, mock_cli):
        mock_cli.return_value = mock.MagicMock()
        mock_cli.return_value.dpkg_l.return_value = \
            ["ii  libc-bin 2.26-3ubuntu1.3 amd64"]
        YPackageChecker()()
        self.assertTrue(mock_add_known_bug.called)

    @mock.patch('core.cli_helpers.CLIHelper')
    @mock.patch('core.ycheck.packages.add_known_bug')
    def test_pkgbugchecks_no_packages(self, mock_add_known_bug, mock_cli):
        mock_cli.return_value = mock.MagicMock()
        mock_cli.return_value.dpkg_l.return_value = []
        YPackageChecker()()
        self.assertFalse(mock_add_known_bug.called)
