import os
from unittest import mock

from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import NetworkPort
from hotsos.core.host_helpers.systemd import SystemdService
from hotsos.core.issues.utils import IssuesStore
from hotsos.core.plugins.openvswitch import (
    OpenvSwitchBase,
    OVSDB,
    OVNBase,
    OVSFDBStats,
)
from hotsos.core.ycheck.scenarios import YScenarioChecker
from hotsos.core.ycheck.common import GlobalSearcher
from hotsos.plugin_extensions.openvswitch import (
    event_checks,
    summary,
)

from . import utils

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

VSWITCHD_LOG = """
2023-06-08T07:31:02.643Z|00017|util(pmd-c11/id:3)|EMER|../include/openvswitch/ofpbuf.h:194: assertion offset + size <= b->size failed in ofpbuf_at_assert()
2023-06-08T07:39:03.134Z|00002|util(pmd-c11/id:7)|EMER|../lib/conntrack.c:1095: assertion conn->conn_type == CT_CONN_TYPE_DEFAULT failed in conn_update_state()
"""  # noqa

BFD_STATE_CHANGES = """
2022-07-27T08:49:57.903Z|00007|bfd|INFO|ovn-abc-xa-15: BFD state change: admin_down->down "No Diagnostic"->"No Diagnostic".
2022-07-27T08:49:57.903Z|00007|bfd(handler7)|INFO|ovn-abc-xa-15: BFD state change: down->init "No Diagnostic"->"No Diagnostic".
2022-07-27T08:49:58.323Z|00066|bfd(handler1)|INFO|ovn-abc-xb-0: BFD state change: down->up "No Diagnostic"->"No Diagnostic".
2022-07-27T08:49:58.362Z|00069|bfd(handler1)|INFO|ovn-abc-xa-2: BFD state change: down->up "No Diagnostic"->"No Diagnostic".
2022-07-27T08:49:58.844Z|00018|bfd(handler4)|INFO|ovn-abc-xa-15: BFD state change: init->up "No Diagnostic"->"No Diagnostic".
"""  # noqa

OFPROTO_LIST_TUNNELS = """
port 4: ovn-comput-1 (geneve: ::->10.10.2.33, key=flow, legacy_l2, dp port=4, ttl=64, csum=true)
port 4: ovn-comput-2 (geneve: ::->10.10.2.29, key=flow, legacy_l2, dp port=4, ttl=64, csum=true)
"""  # noqa

OVS_DB_GENEVE_ENCAP = """
Open_vSwitch table
_uuid               : 35eda39e-ada8-4c2f-b6cb-00e28f336182
external_ids        : {hostname=compute-1, ovn-bridge-mappings="physnet1:br-data", ovn-cms-options=enable-chassis-as-gw, ovn-encap-ip="10.3.4.24", ovn-encap-type=geneve, ovn-remote="ssl:10.3.4.99:6642,ssl:10.3.4.125:6642,ssl:10.3.4.140:6642", rundir="/var/run/openvswitch", system-id=compute-1, ovn-match-northd-version="true"}

"""  # noqa

OVNDB_TABLE_CONNECTION = """
_uuid               : 0fb85665-7d1a-4730-acac-4498b6649edb
external_ids        : {}
inactivity_probe    : []
is_connected        : false
max_backoff         : []
other_config        : {}
status              : {}
target              : "pssl:6641:[::]"
"""  # noqa

LEADERSHIP_TRANSFERS = """
2022-07-27T04:55:54.400Z|117956|raft|INFO|Transferring leadership to write a snapshot.
2022-07-27T05:17:45.365Z|118228|raft|INFO|received leadership transfer from fd77 in term 41911
"""  # noqa

NORTHD_LEADER_CHANGE = """
2023-12-13T03:26:27.299Z|16875|ovn_northd|INFO|ovn-northd lock lost. This ovn-northd instance is now on standby.
2023-12-13T04:57:13.234Z|16898|ovn_northd|INFO|ovn-northd lock acquired. This ovn-northd instance is now active.
2023-12-13T04:57:13.235Z|16901|ovn_northd|INFO|ovn-northd lock lost. This ovn-northd instance is now on standby.
2023-12-13T04:58:46.709Z|16908|ovn_northd|INFO|ovn-northd lock acquired. This ovn-northd instance is now active.
2023-12-13T05:52:37.116Z|18133|ovn_northd|INFO|ovn-northd lock lost. This ovn-northd instance is now on standby.
"""  # noqa

NBDB_COMPACTION = """
2022-07-13T23:32:57.624Z|631027|ovsdb|INFO|OVN_Northbound: Database compaction took 2145ms
2022-07-13T23:43:51.864Z|631056|ovsdb|INFO|OVN_Northbound: Database compaction took 2279ms
2022-07-13T23:57:57.528Z|631184|ovsdb|INFO|OVN_Northbound: Database compaction took 2151ms
"""  # noqa

SBDB_COMPACTION = """
2022-07-14T23:32:57.624Z|631027|ovsdb|INFO|OVN_Southbound: Database compaction took 2145ms
2022-07-14T23:43:51.864Z|631056|ovsdb|INFO|OVN_Southbound: Database compaction took 2279ms
2022-07-14T23:57:57.528Z|631184|ovsdb|INFO|OVN_Southbound: Database compaction took 2151ms
"""  # noqa

DA_MSGS = """
Mar  3 22:57:11 compute4 kernel: [1381807.338196] openvswitch: ovs-system: deferred action limit reached, drop recirc action
Mar  3 22:57:11 compute4 kernel: [1381807.714508] openvswitch: ovs-system: deferred action limit reached, drop recirc action
Mar  3 22:57:11 compute4 kernel: [1381807.843795] openvswitch: ovs-system: deferred action limit reached, drop recirc action
Mar  3 22:57:22 compute4 kernel: [1381818.448855] openvswitch: ovs-system: deferred action limit reached, drop recirc action
Mar  3 22:57:23 compute4 kernel: [1381819.715713] openvswitch: ovs-system: deferred action limit reached, drop recirc action
Mar  3 22:57:24 compute4 kernel: [1381820.269384] openvswitch: ovs-system: deferred action limit reached, drop recirc action
Mar  3 22:57:24 compute4 kernel: [1381820.499397] openvswitch: ovs-system: deferred action limit reached, drop recirc action
"""  # noqa

FDB_STATS_BR_EX_FULL = """
Statistics for bridge "br-ex":
  Current/maximum MAC entries in the table: 8192/8192
  Current static MAC entries in the table : 0
"""  # noqa

FDB_STATS_BR_EX_NOT_FULL = """
Statistics for bridge "br-ex":
  Current/maximum MAC entries in the table: 8/8192
  Current static MAC entries in the table : 0
"""  # noqa


class TestOpenvswitchBase(utils.BaseTestCase):
    """ Custom base testcase that sets openvswitch plugin context. """
    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        HotSOSConfig.plugin_name = 'openvswitch'


class TestCoreOpenvSwitch(TestOpenvswitchBase):
    """ Unit tests for core ovs plugin code. """
    def test_base_offload_disabled(self):
        enabled = OpenvSwitchBase().offload_enabled
        self.assertFalse(enabled)

    @utils.create_data_root({('sos_commands/openvswitch/ovs-vsctl_-t_5_get_'
                              'Open_vSwitch_._other_config'):
                             '{hw-offload="true", max-idle="30000"}'})
    def test_base_offload_enabled(self):
        enabled = OpenvSwitchBase().offload_enabled
        self.assertTrue(enabled)


class TestOpenvswitchServiceInfo(TestOpenvswitchBase):
    """ Unit tests for ovs service code. """
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
                            'openvswitch-switch'],
                        'static': [
                            'ovs-vswitchd', 'ovsdb-server']},
                    'ps': [
                        'ovs-vswitchd (1)',
                        'ovsdb-server (1)']}
        inst = summary.OpenvSwitchSummary()
        self.assertEqual(self.part_output_to_actual(inst.output)['services'],
                         expected)

    def test_summary_bridges(self):
        expected = {'br-data': [
                        {'ens7': {
                            'addresses': [],
                            'hwaddr': '52:54:00:78:19:c3',
                            'mtu': 1500,
                            'state': 'UP',
                            'speed': 'Unknown!'}}],
                    'br-ex': [],
                    'br-int': ['(6 ports)'],
                    'br-tun': ['vxlan-0a000072',
                               'vxlan-0a000085']}

        inst = summary.OpenvSwitchSummary()
        self.assertEqual(self.part_output_to_actual(inst.output)['bridges'],
                         expected)

    def test_summary_tunnels(self):
        expected = {'vxlan': {
                        'iface': {
                            'br-ens3': {
                                'addresses': ['10.0.0.128'],
                                'hwaddr': '22:c2:7b:1c:12:1b',
                                'mtu': 1500,
                                'speed': 'unknown',
                                'state': 'UP'}},
                        'remotes': 2}}

        inst = summary.OpenvSwitchSummary()
        self.assertEqual(self.part_output_to_actual(inst.output)['tunnels'],
                         expected)

    @utils.create_data_root({'sos_commands/openvswitch/ovs-appctl_ofproto.'
                             'list-tunnels': ''},
                            copy_from_original=[
                                'sos_commands/openvswitch/ovs-vsctl_-t_5_list_'
                                'Open_vSwitch',
                                'sos_commands/networking'])
    def test_summary_ovs_tunnels_no_remotes(self):
        inst = summary.OpenvSwitchSummary()
        self.assertFalse('tunnels' in self.part_output_to_actual(inst.output))

    @utils.create_data_root({'sos_commands/openvswitch/ovs-appctl_ofproto.'
                             'list-tunnels': '',
                             'sos_commands/openvswitch/ovs-vsctl_-t_5_list_'
                             'Open_vSwitch': OVS_DB_GENEVE_ENCAP})
    def test_summary_ovn_tunnels_no_remotes(self):
        with mock.patch(
            "hotsos.core.host_helpers.HostNetworkingHelper."
            "host_interfaces_all",
            [
                NetworkPort(
                    name="bondX",
                    addresses=["10.3.4.24"],
                    hwaddr=None,
                    state=None,
                    encap_info=None,
                    mtu=None,
                )
            ],
        ):
            expected = {'geneve': {
                            'iface': {
                                'bondX': {'addresses': ['10.3.4.24'],
                                          'hwaddr': None,
                                          'mtu': None,
                                          'speed': 'unknown',
                                          'state': None}},
                            'remotes': 0}}
            inst = summary.OpenvSwitchSummary()
            actual = self.part_output_to_actual(inst.output)['tunnels']
            self.assertEqual(actual, expected)

    @utils.create_data_root({'sos_commands/ovn_central/microovn.ovn-nbctl_'
                             '--no-leader-only_list_Connection':
                             OVNDB_TABLE_CONNECTION,
                             'sos_commands/ovn_central/microovn.ovn-sbctl_'
                             '--no-leader-only_list_Connection':
                             OVNDB_TABLE_CONNECTION})
    @mock.patch.object(OVNBase, 'is_ovn_central', True)
    def test_summary_ovn_central_db(self):
        expected = {'config': {
                        'nbdb': {'inactivity_probe': '[]',
                                 'max_backoff': '[]'},
                        'sbdb': {'inactivity_probe': '[]',
                                 'max_backoff': '[]'}},
                    'ovn': {
                        'nbdb': {'routers': 0, 'switches': 0},
                        'sbdb': {'chassis': 0, 'ports': 0,
                                 'router-gateways': 0}}}
        inst = summary.OpenvSwitchSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertDictEqual(actual, expected)

    @utils.create_data_root({'sos_commands/openvswitch/ovs-appctl_ofproto.'
                             'list-tunnels':
                             OFPROTO_LIST_TUNNELS,
                             'sos_commands/openvswitch/ovs-vsctl_-t_5_list_'
                             'Open_vSwitch': OVS_DB_GENEVE_ENCAP})
    def test_summary_tunnels_ovn(self):
        with mock.patch(
            "hotsos.core.host_helpers.HostNetworkingHelper."
            "host_interfaces_all",
            [
                NetworkPort(
                    name="bondX",
                    addresses=["10.3.4.24"],
                    hwaddr=None,
                    state=None,
                    encap_info=None,
                    mtu=None,
                )
            ],
        ):
            expected = {'geneve': {
                            'iface': {
                                'bondX': {'addresses': ['10.3.4.24'],
                                          'hwaddr': None,
                                          'mtu': None,
                                          'speed': 'unknown',
                                          'state': None}},
                            'remotes': 2}}
            inst = summary.OpenvSwitchSummary()
            actual = self.part_output_to_actual(inst.output)['tunnels']
            self.assertEqual(actual, expected)


class TestOVSFDBStats(TestOpenvswitchBase):
    """ Unit tests for ovs fdb statistics code. """
    @utils.create_data_root({('sos_commands/openvswitch/'
                              'ovs-appctl_fdb.stats-show_br-ex'):
                             FDB_STATS_BR_EX_FULL,
                             ('sos_commands/openvswitch/'
                              'ovs-vsctl_-t_5_list-br'): 'br-ex'})
    def test_ovs_fdb_full(self):
        fdbstats = OVSFDBStats()
        self.assertEqual(fdbstats.bridges_with_fdb_overflow, ['br-ex'])

    @utils.create_data_root({('sos_commands/openvswitch/'
                              'ovs-appctl_fdb.stats-show_br-ex'):
                             FDB_STATS_BR_EX_NOT_FULL,
                             ('sos_commands/openvswitch/'
                              'ovs-vsctl_-t_5_list-br'): 'br-ex'})
    def test_ovs_fdb_not_full(self):
        fdbstats = OVSFDBStats()
        self.assertEqual(fdbstats.bridges_with_fdb_overflow, [])


class TestOpenvswitchDB(TestOpenvswitchBase):
    """ Unit tests for ovsdb code. """
    def test_ovsdb_other_config(self):
        expected = {}
        self.assertEqual(OVSDB().Open_vSwitch.other_config, expected)

    @utils.create_data_root({('sos_commands/openvswitch/ovs-vsctl_-t_5_get_'
                              'Open_vSwitch_._other_config'):
                             ('{dpdk-extra="-a 0000:56:00.0 -a 0000:58:00.1 '
                              '-a 0000:56:00.1 -a 0000:58:00.0", '
                              'dpdk-init="true", '
                              'dpdk-lcore-mask="0x200002", '
                              'dpdk-socket-mem="8192,8192", '
                              'vlan-limit="0"}')})
    def test_ovsdb_other_config_loaded(self):
        expected = {'dpdk-extra':
                    ('-a 0000:56:00.0 -a 0000:58:00.1 '
                     '-a 0000:56:00.1 -a 0000:58:00.0'),
                    'dpdk-init': "true",
                    'dpdk-lcore-mask': "0x200002",
                    'dpdk-socket-mem': "8192,8192",
                    'vlan-limit': '0'}
        self.assertEqual(OVSDB().Open_vSwitch.other_config, expected)

    def test_ovsdb_external_ids(self):
        expected = {'hostname': 'compute4.mylab.home',
                    'rundir': '/var/run/openvswitch',
                    'system-id': '3c98ecc6-adbc-4647-853b-d4c2b38e49ac'}
        self.assertEqual(OVSDB().Open_vSwitch.external_ids, expected)


class TestOpenvswitchEvents(TestOpenvswitchBase):
    """ Unit tests for ovs events. """
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('ovs-vswitchd.yaml',
                                        'events/openvswitch'))
    def test_ovs_vswitchd_checks(self):
        expected = {
            'ovs-vswitchd': {
                'unreasonably-long-poll-interval':
                    {'2022-02-10': 3},
                'bridge-no-such-device': {
                    '2022-02-10': {'tap6a0486f9-82': 1}}}}
        with GlobalSearcher() as searcher:
            inst = event_checks.OVSEventChecks(searcher)
            actual = self.part_output_to_actual(inst.output)
            for key, value in expected.items():
                self.assertEqual(actual[key], value)

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('ovs-vswitchd.yaml',
                                        'events/openvswitch'))
    @utils.create_data_root({('var/log/openvswitch/'
                              'ovs-vswitchd.log'):
                             VSWITCHD_LOG})
    def test_ovs_vswitchd_assertion_failures(self):
        # TODO(haleyb): combine with above code to have all checks in one place
        expected = {
            'ovs-vswitchd': {
                'assertion-failures':
                    {'2023-06-08': 2}}}
        with GlobalSearcher() as searcher:
            inst = event_checks.OVSEventChecks(searcher)
            self.assertEqual(self.part_output_to_actual(inst.output), expected)

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('errors-and-warnings.yaml',
                                        'events/openvswitch'))
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
        with GlobalSearcher() as searcher:
            inst = event_checks.OVSEventChecks(searcher)
            actual = self.part_output_to_actual(inst.output)
            for key, value in expected.items():
                self.assertEqual(actual[key], value)

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('errors-and-warnings.yaml',
                                        'events/openvswitch'))
    @utils.create_data_root({('var/log/openvswitch/'
                              'ovs-vswitchd.log'):
                             VSWITCHD_LOG})
    def test_ovs_emer_log_checks(self):
        # TODO(haleyb): combine with above code to have all checks in one place
        expected = {
            'errors-and-warnings': {
                'ovs-vswitchd': {
                    'EMER': {
                        '2023-06-08': 2}}}}
        with GlobalSearcher() as searcher:
            inst = event_checks.OVSEventChecks(searcher)
            self.assertEqual(self.part_output_to_actual(inst.output), expected)

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('datapath-checks.yaml',
                                        'events/openvswitch'))
    @utils.create_data_root({('sos_commands/openvswitch/'
                              'ovs-appctl_dpctl.show_-s_system_ovs-system'):
                             DPCTL_SHOW,
                             ('sos_commands/openvswitch/'
                              'ovs-vsctl_-t_5_list-br'): 'br-int'})
    def test_ovs_dp_checks(self):
        expected = {'datapath-checks-port-stats': {
                        'qr-aa623763-fd': {
                            'RX': {
                                'dropped': 1394875,
                                'packets': 309}}}}
        with GlobalSearcher() as searcher:
            inst = event_checks.OVSEventChecks(searcher)
            self.assertEqual(self.part_output_to_actual(inst.output), expected)

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('ovn-central.yaml',
                                        'events/openvswitch'))
    def test_ovn_central_checks(self):
        expected = {'ovn-northd': {
                        'leadership-acquired': {
                            '2022-02-16': 1, '2022-02-17': 2}},
                    'ovsdb-server-sb': {
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
        with GlobalSearcher() as searcher:
            inst = event_checks.OVNEventChecks(searcher)
            actual = self.part_output_to_actual(inst.output)
            for key, value in expected.items():
                self.assertEqual(actual[key], value)

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('ovn-controller.yaml',
                                        'events/openvswitch'))
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
        with GlobalSearcher() as searcher:
            inst = event_checks.OVNEventChecks(searcher)
            actual = self.part_output_to_actual(inst.output)
            for key, value in expected.items():
                self.assertEqual(actual[key], value)

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('errors-and-warnings.yaml',
                                        'events/openvswitch'))
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
        with GlobalSearcher() as searcher:
            inst = event_checks.OVNEventChecks(searcher)
            actual = self.part_output_to_actual(inst.output)
            for key, value in expected.items():
                self.assertEqual(actual[key], value)

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('bfd.yaml',
                                        'events/openvswitch'))
    @utils.create_data_root({'var/log/openvswitch/ovs-vswitchd.log':
                             BFD_STATE_CHANGES},
                            copy_from_original=['sos_commands/date/date'])
    def test_ovs_bfd_state_changes(self):
        expected = {'ovs-vswitchd': {
                    'bfd': {
                        'state-change-stats': {
                            'all-ports-day-avg': {
                                '2022-07-27': 1},
                            'per-port-day-total': {
                                '2022-07-27': {'ovn-abc-xb-0': 1,
                                               'ovn-abc-xa-2': 1,
                                               'ovn-abc-xa-15': 3}}}}}}
        with GlobalSearcher() as searcher:
            inst = event_checks.OVSEventChecks(searcher)
            self.assertEqual(self.part_output_to_actual(inst.output), expected)

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('ovn/ovn-central.yaml',
                                        'events/openvswitch'))
    @utils.create_data_root({'var/log/ovn/ovsdb-server-nb.log':
                             LEADERSHIP_TRANSFERS,
                             'var/log/ovn/ovsdb-server-sb.log':
                             LEADERSHIP_TRANSFERS},
                            copy_from_original=['sos_commands/date/date'])
    def test_ovn_ovsdb_leadership_changes(self):
        expected = {'ovsdb-server-nb': {'leadership-transfers': {
                                            '2022-07-27': 2}},
                    'ovsdb-server-sb': {'leadership-transfers': {
                                            '2022-07-27': 2}}}
        with GlobalSearcher() as searcher:
            inst = event_checks.OVNEventChecks(searcher)
            self.assertEqual(self.part_output_to_actual(inst.output), expected)

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('ovn/ovn-central.yaml',
                                        'events/openvswitch'))
    @utils.create_data_root({'var/log/ovn/ovn-northd.log':
                             NORTHD_LEADER_CHANGE},
                            copy_from_original=['sos_commands/date/date'])
    def test_ovn_northd_leadership_changes(self):
        expected = {'ovn-northd': {'leadership-acquired': {
                                            '2023-12-13': 2}}}
        with GlobalSearcher() as searcher:
            inst = event_checks.OVNEventChecks(searcher)
            self.assertEqual(self.part_output_to_actual(inst.output), expected)

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('ovn/ovn-central.yaml',
                                        'events/openvswitch'))
    @utils.create_data_root({'var/log/ovn/ovsdb-server-nb.log':
                             NBDB_COMPACTION,
                             'var/log/ovn/ovsdb-server-sb.log':
                             SBDB_COMPACTION},
                            copy_from_original=['sos_commands/date/date'])
    def test_ovn_ovsdb_compactions(self):
        expected = {'ovsdb-server-nb': {'compactions': {
                                            '2022-07-13': 3}},
                    'ovsdb-server-sb': {'compactions': {
                                            '2022-07-14': 3}}}
        with GlobalSearcher() as searcher:
            inst = event_checks.OVNEventChecks(searcher)
            self.assertEqual(self.part_output_to_actual(inst.output), expected)

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('ovs/datapath-checks.yaml',
                                        'events/openvswitch'))
    @utils.create_data_root({'var/log/kern.log': DA_MSGS})
    def test_ovs_defferred_action_limit_reached(self):
        expected = {
            'datapath-checks': {
                'deferred-action-limit-reached': {
                    'ovs-system':
                        {'Mar 3': 7}}}}
        with GlobalSearcher() as searcher:
            inst = event_checks.OVSEventChecks(searcher)
            self.assertEqual(self.part_output_to_actual(inst.output), expected)


@utils.load_templated_tests('scenarios/openvswitch')
class TestOpenvswitchScenarios(TestOpenvswitchBase):
    """
    Scenario tests can be written using YAML templates that are auto-loaded
    into this test runner. This is the recommended way to write tests for
    scenarios. It is however still possible to write the tests in Python if
    required. See https://hotsos.readthedocs.io/en/latest/contrib/testing.html
    for more information.
    """

    @mock.patch('hotsos.core.ycheck.engine.properties.requires.types.systemd.'
                'SystemdHelper')
    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('ovn_central_services.yaml',
                                        'scenarios/openvswitch'))
    def test_ovn_northd_running(self, mock_systemd):
        # pylint: disable-next=too-few-public-methods
        class FakeSystemdHelper():
            """ fake systemd helper """
            def __init__(self, svcs):
                self.processes = {}
                self.services = {}
                for svc in svcs:
                    self.services[svc] = SystemdService(svc, 'enabled')
                    if svc != 'ovn-northd':
                        self.processes[svc] = 1

        mock_systemd.side_effect = FakeSystemdHelper
        with GlobalSearcher() as searcher:
            YScenarioChecker(searcher).run()

        msg = ('The ovn-northd service on this ovn-central host is not '
               'active/running which means that changes made to the '
               'northbound database are not being ported to the southbound '
               'database.')
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual([issue['message'] for issue in issues], [msg])

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('ovn/ovn_central_certs_logs.yaml',
                                        'scenarios/openvswitch'))
    @utils.create_data_root({'etc/ovn/cert_host': '',
                             'etc/ovn/ovn-central.crt': ''},
                            copy_from_original=['sos_commands/date/date',
                                                'uptime'])
    def test_ovn_ssl_certs_svcs_no_error(self):
        mtime = os.path.getmtime(os.path.join(HotSOSConfig.data_root,
                                              'etc/ovn/cert_host'))

        class FakeSystemdService(SystemdService):
            """ fake systemd service """
            @property
            def start_time_secs(self):  # pylint: disable=W0236
                return mtime + 10

        services = {'ovn-northd':
                    FakeSystemdService('ovn-northd', 'enabled'),
                    'ovn-ovsdb-server-sb':
                    FakeSystemdService('ovn-ovsdb-server-sb', 'enabled'),
                    'ovn-ovsdb-server-nb':
                    FakeSystemdService('ovn-ovsdb-server-nb', 'enabled')}

        with mock.patch(('hotsos.core.host_helpers.systemd.SystemdHelper.'
                         'services'), services):
            with GlobalSearcher() as searcher:
                YScenarioChecker(searcher).run()

            issues = list(IssuesStore().load().values())
            self.assertEqual(len(issues), 0)

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('ovn/ovn_central_certs_logs.yaml',
                                        'scenarios/openvswitch'))
    @utils.create_data_root({'etc/ovn/cert_host': '',
                             'etc/ovn/ovn-central.crt': ''},
                            copy_from_original=['sos_commands/date/date',
                                                'uptime'])
    def test_ovn_ssl_certs_svcs_w_error(self):
        mtime = os.path.getmtime(os.path.join(HotSOSConfig.data_root,
                                              'etc/ovn/cert_host'))

        class FakeSystemdService(SystemdService):
            """ fake systemd service """
            @property
            def start_time_secs(self):  # pylint: disable=W0236
                return mtime - 10

        services = {'ovn-northd':
                    FakeSystemdService('ovn-northd', 'enabled'),
                    'ovn-ovsdb-server-sb':
                    FakeSystemdService('ovn-ovsdb-server-sb', 'enabled'),
                    'ovn-ovsdb-server-nb':
                    FakeSystemdService('ovn-ovsdb-server-nb', 'enabled')}

        with mock.patch(('hotsos.core.host_helpers.systemd.SystemdHelper.'
                         'services'), services):
            with GlobalSearcher() as searcher:
                YScenarioChecker(searcher).run()

            msg = ("One or more of services ovn-northd, ovn-ovsdb-server-nb "
                   "and ovn-ovsdb-server-sb has not been restarted since ssl "
                   "certs were updated and this may breaking their ability to "
                   "connect to other services.")
            issues = list(IssuesStore().load().values())[0]
            self.assertEqual([issue['message'] for issue in issues], [msg])

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('ovn/ovn_chassis_certs_logs.yaml',
                                        'scenarios/openvswitch'))
    @utils.create_data_root({'etc/ovn/cert_host': '',
                             'etc/ovn/ovn-chassis.crt': ''},
                            copy_from_original=['sos_commands/date/date',
                                                'uptime'])
    def test_ovn_chassis_ssl_certs_svcs_no_error(self):
        mtime = os.path.getmtime(os.path.join(HotSOSConfig.data_root,
                                              'etc/ovn/cert_host'))

        class FakeSystemdService(SystemdService):
            """ fake systemd service """
            @property
            def start_time_secs(self):  # pylint: disable=W0236
                return mtime + 10

        services = {'ovn-controller':
                    FakeSystemdService('ovn-controller', 'enabled')}
        with mock.patch(('hotsos.core.host_helpers.systemd.SystemdHelper.'
                         'services'), services):
            with GlobalSearcher() as searcher:
                YScenarioChecker(searcher).run()

            issues = list(IssuesStore().load().values())
            self.assertEqual(len(issues), 0)

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('ovn/ovn_chassis_certs_logs.yaml',
                                        'scenarios/openvswitch'))
    @utils.create_data_root({'etc/ovn/cert_host': '',
                             'etc/ovn/ovn-chassis.crt': ''},
                            copy_from_original=['sos_commands/date/date',
                                                'uptime'])
    def test_ovn_chassis_ssl_certs_svcs_w_error(self):
        mtime = os.path.getmtime(os.path.join(HotSOSConfig.data_root,
                                              'etc/ovn/cert_host'))

        class FakeSystemdService(SystemdService):
            """ fake systemd service """
            @property
            def start_time_secs(self):  # pylint: disable=W0236
                return mtime - 10

        services = {'ovn-controller':
                    FakeSystemdService('ovn-controller', 'enabled')}
        with mock.patch(('hotsos.core.host_helpers.systemd.SystemdHelper.'
                         'services'), services):
            with GlobalSearcher() as searcher:
                YScenarioChecker(searcher).run()

            msg = ("ovn-controller has not been restarted since ssl certs "
                   "were updated so may be using old certs. Please check.")
            issues = list(IssuesStore().load().values())[0]
            self.assertEqual([issue['message'] for issue in issues], [msg])
