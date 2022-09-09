from unittest import mock

from . import utils

from hotsos.core import issues
from hotsos.core.issues.utils import IssuesStore, KnownBugsStore
from hotsos.core.config import setup_config
from hotsos.core.plugins.openvswitch import OpenvSwitchBase
from hotsos.core.ycheck.scenarios import YScenarioChecker
from hotsos.plugin_extensions.openvswitch import (
    event_checks,
    summary,
)

LP1917475_LOG = r"""
2021-09-22T01:13:33.307Z|00266|ovsdb_idl|WARN|transaction error: {"details":"RBAC rules for client \"compute5\" role \"ovn-controller\" prohibit row insertion into table \"IGMP_Group\".","error":"permission error"}
"""  # noqa

DPIF_LOST_PACKETS_TMPLT = """
2022-03-25T{hour}:{min}:12.913Z|10324|dpif_netlink(handler10)|WARN|system@ovs-system: lost packet on port channel 0 of handler 0
"""  # noqa, pylint: disable=C0301

DPIF_RESUBMIT_LIMIT_TMPLT = """
2022-02-20T{hour}:{min}:22.449Z|14339034|ofproto_dpif_xlate|WARN|over 4096 resubmit actions on bridge br-int while processing arp,in_port=CONTROLLER,vlan_tci=0x0000,dl_src=fa:16:3e:2e:f1:45,dl_dst=ff:ff:ff:ff:ff:ff,arp_spa=10.200.86.60,arp_tpa=10.200.86.130,arp_op=1,arp_sha=fa:16:3e:2e:f1:45,arp_tha=00:00:00:00:00:00
"""  # noqa, pylint: disable=C0301

BFD_STATE_CHANGES_TMPLT = """
2022-04-21T21:00:{sec}.466Z|01221|bfd(monitor130)|INFO|ovn-abc-ra-f: BFD state change: up->down "Control Detection Time Expired"->"Control Detection Time Expired".
"""  # noqa, pylint: disable=C0301

CR_LRP_CHANGES_TMPLT = """
2022-04-21T14:03:{sec}.947Z|1044240|binding|INFO|Claiming lport cr-lrp-31f4fa6a-04cf-462f-aab9-b283fcdb7ce4 for this chassis.
2022-04-21T15:03:{sec}.213Z|1044241|binding|INFO|Claiming lport bac8173d-ee39-4139-b699-754a3d17d771 for this chassis.
"""  # noqa, pylint: disable=C0301

DPCTL_SHOW = r"""  port 6: br-int (internal)
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

OVS_DB_RECONNECT_ERROR = """
2022-07-04 20:03:32.405 2050177 ERROR ovsdbapp.backend.ovs_idl.connection ValueError: non-zero flags not allowed in calls to send() on <class 'eventlet.green.ssl.GreenSSLSocket'>
"""  # noqa

BFD_STATE_CHANGES = """
2022-07-27T08:49:57.903Z|00007|bfd|INFO|ovn-abc-xa-15: BFD state change: admin_down->down "No Diagnostic"->"No Diagnostic".
2022-07-27T08:49:57.903Z|00007|bfd(handler7)|INFO|ovn-abc-xa-15: BFD state change: down->init "No Diagnostic"->"No Diagnostic".
2022-07-27T08:49:58.323Z|00066|bfd(handler1)|INFO|ovn-abc-xb-0: BFD state change: down->up "No Diagnostic"->"No Diagnostic".
2022-07-27T08:49:58.362Z|00069|bfd(handler1)|INFO|ovn-abc-xa-2: BFD state change: down->up "No Diagnostic"->"No Diagnostic".
2022-07-27T08:49:58.844Z|00018|bfd(handler4)|INFO|ovn-abc-xa-15: BFD state change: init->up "No Diagnostic"->"No Diagnostic".
"""  # noqa


class TestOpenvswitchBase(utils.BaseTestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        setup_config(PLUGIN_NAME='openvswitch')


class TestCoreOpenvSwitch(TestOpenvswitchBase):

    def testBase_offload_disabled(self):
        enabled = OpenvSwitchBase().offload_enabled
        self.assertFalse(enabled)

    @utils.create_test_files({('sos_commands/openvswitch/ovs-vsctl_-t_5_get_'
                               'Open_vSwitch_._other_config'):
                              '{hw-offload="true", max-idle="30000"}'})
    def testBase_offload_enabled(self):
        enabled = OpenvSwitchBase().offload_enabled
        self.assertTrue(enabled)


class TestOpenvswitchServiceInfo(TestOpenvswitchBase):

    def test_get_package_checks(self):
        expected = ['libc-bin 2.31-0ubuntu9.2',
                    'openssl 1.1.1f-1ubuntu2.10',
                    'openvswitch-common 2.13.3-0ubuntu0.20.04.2',
                    'openvswitch-switch 2.13.3-0ubuntu0.20.04.2',
                    'python3-openssl 19.0.0-1build1',
                    'python3-openvswitch 2.13.3-0ubuntu0.20.04.2',
                    'python3-ovsdbapp 1.1.0-0ubuntu2']
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

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('datapath-checks.yaml'))
    @utils.create_test_files({('sos_commands/openvswitch/'
                               'ovs-appctl_dpctl.show_-s_system_ovs-system'):
                              DPCTL_SHOW,
                              ('sos_commands/openvswitch/'
                               'ovs-vsctl_-t_5_list-br'): 'br-int'})
    def test_ovs_dp_checks(self):
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
                     'involuntary-context-switches': {
                         '2022-02-16': {'09': 634},
                         '2022-02-17': {'04': 136}},
                     'bridge-not-found-for-port': {
                        '2022-02-16':
                            {'provnet-aa3a4fec-a788-42e6-a773-bf3a0cdb52c2':
                             1}}}}
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

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('bfd.yaml'))
    @utils.create_test_files({'var/log/openvswitch/ovs-vswitchd.log':
                              BFD_STATE_CHANGES})
    def test_ovs_bfd_state_changes(self):
        expected = {'ovs-vswitchd': {
                    'bfd-state-changes': {
                        '2022-07-27': {
                            'ovn-abc-xa-15': [
                                    'admin_down->down',
                                    'down->init',
                                    'init->up'],
                            'ovn-abc-xa-2': [
                                'down->up'],
                            'ovn-abc-xb-0': [
                                'down->up']}}}}
        inst = event_checks.OVSEventChecks()
        self.assertEqual(self.part_output_to_actual(inst.output), expected)


class TestOpenvswitchScenarioChecks(TestOpenvswitchBase):

    @mock.patch('hotsos.core.host_helpers.packaging.CLIHelper')
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('ovn_bugs.yaml'))
    def test_1865127(self, mock_cli):
        """
        NOTE: we don't use utils.create_test_files here because we want to use
        the logs in current DATA_ROOT.
        """
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
    @utils.create_test_files({'var/log/ovn/ovn-controller.log': LP1917475_LOG})
    def test_1917475(self):
        YScenarioChecker()()
        expected = {'bugs-detected':
                    [{'id': 'https://bugs.launchpad.net/bugs/1917475',
                      'desc': "known ovn bug identified - db rbac errors",
                      'origin': 'openvswitch.01part'}]}
        self.assertEqual(issues.IssuesManager().load_bugs(),
                         expected)

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('ovs_bugs.yaml'))
    @utils.create_test_files({'sos_commands/dpkg/dpkg_-l':
                              'ii  libc-bin 2.26-3ubuntu1.3 amd64'})
    def test_1839592(self):
        YScenarioChecker()()
        expected = {'bugs-detected':
                    [{'id': 'https://bugs.launchpad.net/bugs/1839592',
                      'desc': "Installed package 'libc-bin' with version "
                              "2.26-3ubuntu1.3 has a known critical bug which "
                              "causes ovs deadlocks. If this environment is "
                              "using OVS it should be upgraded asap.",
                      'origin': 'openvswitch.01part'}]}
        self.assertEqual(issues.IssuesManager().load_bugs(), expected)

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('dpif_lost_packets.yaml'))
    @utils.create_test_files({('sos_commands/openvswitch/'
                               'ovs-appctl_dpctl.show_-s_system_ovs-system'):
                              ('lookups: hit:39017272903 missed:137481120 '
                               'lost:54691089')})
    def test_dpif_lost_packets_no_vswitchd(self):
        YScenarioChecker()()
        msg = ('This host is running Openvswitch and its datapath is '
               'reporting a non-zero amount (54691089) of "lost" packets '
               'which implies that packets are being dropped by the '
               'kernel before they reach userspace (e.g. vm tap). '
               'Causes for this can include high system load, tc rules in '
               'the datapath etc. Suggested actions are (a) check ovs-appctl '
               'dpctl/show to see if the number of lost packets is increasing '
               'and (b) check the ovs-vswitchd logs for more context and '
               'check the path between nic and ovs.')
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('dpif_lost_packets.yaml'))
    @utils.create_test_files({'var/log/openvswitch/ovs-vswitchd.log':
                              utils.expand_log_template(
                                                       DPIF_LOST_PACKETS_TMPLT,
                                                       hours=10, lstrip=True),
                              ('sos_commands/openvswitch/'
                               'ovs-appctl_dpctl.show_-s_system_ovs-system'):
                              ('lookups: hit:39017272903 missed:137481120 '
                               'lost:54691089')})
    def test_dpif_lost_packets_w_vswitchd(self):
        YScenarioChecker()()
        msg = ('This host is running Openvswitch and its datapath is '
               'reporting a non-zero amount (54691089) of "lost" packets '
               'which implies that packets are being dropped by the '
               'kernel before they reach userspace (e.g. vm tap). '
               'Causes for this can include high system load, tc rules in '
               'the datapath etc. Suggested actions are (a) check ovs-appctl '
               'dpctl/show to see if the number of lost packets is increasing '
               'and (b) check the ovs-vswitchd logs for more context and '
               'check the path between nic and ovs. vswitchd has also '
               'recently reported large numbers of dropped packets within a '
               '24h period - logs like "system@ovs-system: lost packet on '
               'port channel".')
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('dpif_resubmit_actions.yaml'))
    @utils.create_test_files({'var/log/openvswitch/ovs-vswitchd.log':
                              utils.expand_log_template(
                                                     DPIF_RESUBMIT_LIMIT_TMPLT,
                                                     hours=5, lstrip=True),
                              'sos_commands/date/date':
                              'Thu Feb 10 16:19:17 UTC 2022'})
    def test_dpif_resubmit_limit_reached(self):
        YScenarioChecker()()
        msg = ('OpenvSwitch (vswitchd) is reporting flows hitting action '
               'resubmit limit (4096) which suggests that packets are being '
               'silently dropped. One cause of this is when you have too many '
               'flows and an example is when you have an excess of ovn '
               'logical flows. Look for "resubmit actions on bridge" in '
               '/var/log/ovs-vswitchd.log for more info and see what type of '
               'flow is resulting in this limit being hit.')
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('bfd_flapping.yaml'))
    @utils.create_test_files({'var/log/openvswitch/ovs-vswitchd.log':
                              utils.expand_log_template(
                                                       BFD_STATE_CHANGES_TMPLT,
                                                       secs=10, lstrip=True),
                              'sos_commands/date/date':
                              'Thu Feb 10 16:19:17 UTC 2022'})
    def test_bfd_flapping_vswitchd_only(self):
        YScenarioChecker()()
        msg = ('The ovn-controller on this host has experienced 10 BFD '
               'state changes within an hour (and within the last 24 '
               'hours). This is unusual and could be an indication that '
               'something is wrong with the network between this node and '
               'one or more peer chassis nodes.')
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('bfd_flapping.yaml'))
    @utils.create_test_files({'var/log/ovn/ovn-controller.log':
                              utils.expand_log_template(CR_LRP_CHANGES_TMPLT,
                                                        secs=20, lstrip=True),
                              'sos_commands/date/date':
                              'Thu Feb 10 16:19:17 UTC 2022'})
    def test_bfd_flapping_cr_lrp_changes(self):
        YScenarioChecker()()
        msg = ('The ovn-controller on this host is showing 20 logical '
               'router port (lrp) chassis re-assignments within the last '
               '24 hours that do not appear to have resulted from BFD '
               'state changes. This could indicate that some operator '
               'activity is causing significant load in ovn which may or '
               'may not be expected.')
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('ovsdb_reconnect_errors.yaml'))
    @utils.create_test_files({'var/log/neutron/neutron-server.log':
                              OVS_DB_RECONNECT_ERROR,
                              'sos_commands/dpkg/dpkg_-l':
                              'ii  python3-openvswitch 2.17.0 amd64'})
    def test_ovsdb_reconnect_error(self):
        YScenarioChecker()()
        msg = ("Installed package 'python3-openvswitch' with version "
               "2.17.0 has a known bug whereby if connections to the ovn "
               "southbound db are closed, the client fails to reconnect. "
               "This is usually resolved with a service restart and a "
               "fix is available as of openvswitch version 2.17.2.")
        issues = list(KnownBugsStore().load().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])
