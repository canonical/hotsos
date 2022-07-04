import os
import tempfile

from unittest import mock

from . import utils

from hotsos.core import issues
from hotsos.core.issues.utils import IssuesStore
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

DPIF_LOST_PACKETS_LOGS = """
2022-03-25T01:55:12.913Z|10324|dpif_netlink(handler10)|WARN|system@ovs-system: lost packet on port channel 0 of handler 0
2022-03-25T01:55:12.924Z|05761|dpif_netlink(handler11)|WARN|system@ovs-system: lost packet on port channel 0 of handler 2
2022-03-25T01:55:12.972Z|06053|dpif_netlink(handler12)|WARN|system@ovs-system: lost packet on port channel 0 of handler 3
2022-03-25T01:55:13.567Z|06054|dpif_netlink(handler12)|WARN|system@ovs-system: lost packet on port channel 0 of handler 3
2022-03-25T01:55:13.571Z|06069|dpif_netlink(handler13)|WARN|system@ovs-system: lost packet on port channel 0 of handler 4
2022-03-25T01:58:42.750Z|05763|dpif_netlink(handler11)|WARN|system@ovs-system: lost packet on port channel 0 of handler 2
"""  # noqa

BFD_STATE_CHANGES = """
2022-04-21T21:00:{secs}.466Z|01221|bfd(monitor130)|INFO|ovn-ps5-ra-f: BFD state change: up->down "Control Detection Time Expired"->"Control Detection Time Expired".
"""  # noqa


CR_LRP_CHANGES = """
2022-04-21T14:03:{secs}.947Z|1044240|binding|INFO|Claiming lport cr-lrp-31f4fa6a-04cf-462f-aab9-b283fcdb7ce4 for this chassis.
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
        with mock.patch.object(openvswitch.host_helpers,
                               'CLIHelper') as mock_cli:
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

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('ovs-vswitchd.yaml'))
    def test_ovs_vswitchd_checks(self):
        expected = {
            'ovs-vswitchd': {
                'unreasonably-long-poll-interval':
                    {'2022-02-10': 3},
                'bridge-no-such-device': {
                    '2022-02-10': {'tap6a0486f9-82': 1}}}}
        inst = event_checks.OVSEventChecks()
        self.assertEqual(self.part_output_to_actual(inst.output), expected)

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('errors-and-warnings.yaml'))
    def test_ovs_common_log_checks(self):
        expected = {
            'errors-and-warnings': {
                'ovs-vswitchd': {
                    'WARN': {
                        '2022-02-04': 56,
                        '2022-02-09': 24,
                        '2022-02-10': 12}},
                'ovsdb-server': {
                    'WARN': {
                        '2022-02-04': 6,
                        '2022-02-09': 2,
                        '2022-02-10': 4}}}}
        inst = event_checks.OVSEventChecks()
        self.assertEqual(self.part_output_to_actual(inst.output), expected)

    @mock.patch('hotsos.core.ycheck.engine.properties.CLIHelper')
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('datapath-checks.yaml'))
    def test_ovs_dp_checks(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.ovs_appctl_dpctl_show.return_value = \
            DPCTL_SHOW
        expected = {'datapath-checks-port-stats': {
                        'qr-aa623763-fd': {
                            'RX': {
                                'dropped': 1394875,
                                'packets': 309
                                }}}}
        inst = event_checks.OVSEventChecks()
        self.assertEqual(self.part_output_to_actual(inst.output), expected)

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('ovn-central.yaml'))
    def test_ovn_central_checks(self):
        expected = {'ovsdb-server-sb': {
                        'inactivity-probe': {
                            '2022-02-16': {'10.130.11.109': 1,
                                           '10.130.11.110': 1},
                            '2022-02-17': {'10.130.11.109': 1,
                                           '10.130.11.110': 1}},
                        'unreasonably-long-poll-interval': {
                            '2022-02-16': 2,
                            '2022-02-17': 3}},
                    'ovsdb-server-nb': {
                        'inactivity-probe': {
                            '2022-02-16': {'10.130.11.109': 1},
                            '2022-02-17': {'10.130.11.115': 1}},
                        'unreasonably-long-poll-interval': {
                            '2022-02-16': 2,
                            '2022-02-17': 1}
                    }}

        inst = event_checks.OVNEventChecks()
        self.assertEqual(self.part_output_to_actual(inst.output), expected)

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('ovn-controller.yaml'))
    def test_ovn_controller_checks(self):
        expected = {'ovn-controller':
                    {'unreasonably-long-poll-interval': {
                        '2022-02-16': 1,
                        '2022-02-17': 1},
                     'bridge-not-found-for-port': {
                        '2022-02-16': 7,
                        '2022-02-17': 16}}}
        inst = event_checks.OVNEventChecks()
        self.assertEqual(self.part_output_to_actual(inst.output), expected)

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('errors-and-warnings.yaml'))
    def test_ovn_common_log_checks(self):
        expected = {'errors-and-warnings': {
                        'ovn-controller': {
                            'ERR': {'2022-02-16': 2},
                            'WARN': {'2022-02-16': 4, '2022-02-17': 5}},
                        'ovn-northd': {
                            'ERR': {'2022-02-16': 1, '2022-02-17': 1},
                            'WARN': {'2022-02-16': 1, '2022-02-17': 1}},
                        'ovsdb-server-nb': {
                            'ERR': {'2022-02-16': 1, '2022-02-17': 1},
                            'WARN': {'2022-02-16': 12, '2022-02-17': 17}},
                        'ovsdb-server-sb': {
                            'ERR': {'2022-02-16': 2, '2022-02-17': 2},
                            'WARN': {'2022-02-16': 23, '2022-02-17': 23}}}}

        inst = event_checks.OVNEventChecks()
        self.assertEqual(self.part_output_to_actual(inst.output), expected)


class TestOpenvswitchScenarioChecks(TestOpenvswitchBase):

    @mock.patch('hotsos.core.host_helpers.packaging.CLIHelper')
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('ovn_bugs.yaml'))
    def test_1865127(self, mock_cli):
        mock_cli.return_value = mock.MagicMock()
        mock_cli.return_value.dpkg_l.return_value = \
            ["ii  ovn-common 20.12.0 amd64"]
        YScenarioChecker()()
        self.assertEqual(issues.IssuesManager().load_bugs(), {})

        mock_cli.return_value.dpkg_l.return_value = \
            ["ii  ovn-common 20.03.2-0ubuntu0.20.04.3 amd64"]
        # we already have this bug in our logs so no need to mock it
        YScenarioChecker()()
        msg = ('The version of ovn on this node is affected by a known bug '
               'where the ovn-controller logs are being spammed with error '
               'messages containing "No bridge for localnet port ..." when '
               'that is in fact not an error. Upgrading to a version >= '
               '20.12.0 will fix the issue.')
        expected = {'bugs-detected':
                    [{'id': 'https://bugs.launchpad.net/bugs/1865127',
                      'desc': msg,
                      'origin': 'openvswitch.01part'}]}
        self.assertEqual(issues.IssuesManager().load_bugs(),
                         expected)

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
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

    @mock.patch('hotsos.core.host_helpers.packaging.CLIHelper')
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
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

    @mock.patch('hotsos.core.plugins.openvswitch.host_helpers.CLIHelper')
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('flow_lookup_checks.yaml'))
    def test_flow_lookup_checks_p1(self, mock_cli):
        mock_cli.return_value = mock.MagicMock()
        mock_cli.return_value.ovs_appctl_dpctl_show.return_value = \
            ['lookups: hit:39017272903 missed:137481120 lost:54691089']

        YScenarioChecker()()
        msg = ('OVS datapath is reporting a non-zero amount of "lost" packets '
               '(total=54691089) which implies that packets destined for '
               'userspace (e.g. vm tap) are being dropped. Please check '
               'ovs-appctl dpctl/show to see if the number of lost packets is '
               'still increasing.')
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.plugins.openvswitch.host_helpers.CLIHelper')
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('flow_lookup_checks.yaml'))
    def test_flow_lookup_checks_p2(self, mock_cli):
        mock_cli.return_value = mock.MagicMock()
        mock_cli.return_value.ovs_appctl_dpctl_show.return_value = \
            ['lookups: hit:39017272903 missed:137481120 lost:54691089']

        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(DATA_ROOT=dtmp)
            logfile = os.path.join(dtmp,
                                   'var/log/openvswitch/ovs-vswitchd.log')
            os.makedirs(os.path.dirname(logfile))
            with open(logfile, 'w') as fd:
                fd.write(DPIF_LOST_PACKETS_LOGS)

            YScenarioChecker()()
            msg = ('OVS datapath is reporting a non-zero amount of "lost" '
                   'packets (total=54691089) which implies that packets '
                   'destined for userspace (e.g. vm tap) are being dropped. '
                   'ovs-vswitchd is also reporting large numbers of dropped '
                   'packets within a 24h period (look for '
                   '"system@ovs-system: lost packet on port channel"). '
                   'This could be caused by '
                   'overloaded system cores blocking ovs threads from '
                   'delivering packets in time. Please check ovs-appctl '
                   'dpctl/show to see if the number of lost packets is still '
                   'increasing.')
            issues = list(IssuesStore().load().values())[0]
            self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.ycheck.engine.properties.CLIHelper')
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('bfd_flapping.yaml'))
    def test_bfd_flapping_vswitchd_only(self, mock_cli):
        mock_cli.return_value = mock.MagicMock()
        mock_cli.return_value.date.return_value = '2022-04-21 20:44:21'
        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(DATA_ROOT=dtmp)
            logfile = os.path.join(dtmp,
                                   'var/log/openvswitch/ovs-vswitchd.log')
            os.makedirs(os.path.dirname(logfile))
            with open(logfile, 'w') as fd:
                for i in range(0, 10):
                    fd.write(BFD_STATE_CHANGES.format(secs='0{}'.format(i)))

            YScenarioChecker()()
            msg = ('The ovn-controller on this host has experienced 10 BFD '
                   'state changes within an hour (and within the last 24 '
                   'hours). This is unusual and could be an indication that '
                   'something is wrong with the network between this node and '
                   'one or more peer chassis nodes.')
            issues = list(IssuesStore().load().values())[0]
            self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.ycheck.engine.properties.CLIHelper')
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('bfd_flapping.yaml'))
    def test_bfd_flapping_cr_lrp_changes(self, mock_cli):
        mock_cli.return_value = mock.MagicMock()
        mock_cli.return_value.date.return_value = '2022-04-21 20:44:21'
        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(DATA_ROOT=dtmp)
            logfile = os.path.join(dtmp, 'var/log/ovn/ovn-controller.log')
            os.makedirs(os.path.dirname(logfile))
            with open(logfile, 'w') as fd:
                for i in range(0, 20):
                    fd.write(CR_LRP_CHANGES.format(secs='0{}'.format(i)))

            YScenarioChecker()()

            msg = ('The ovn-controller on this host is showing 20 logical '
                   'router port (lrp) chassis re-assignments within the last '
                   '24 hours that do not appear to have resulted from BFD '
                   'state changes. This could indicate that some operator '
                   'activity is causing significant load in ovn which may or '
                   'may not be expected.')
            issues = list(IssuesStore().load().values())[0]
            self.assertEqual([issue['desc'] for issue in issues], [msg])
