import os

import datetime
import mock
import tempfile

import utils

from common import searchtools

# Need this for plugin imports
utils.add_sys_plugin_path("openstack")
from plugins.openstack.parts import (  # noqa E402
    openstack_services,
    vm_info,
    nova_external_events,
    package_info,
    network,
    service_features,
    cpu_pinning_check,
    neutron_agent_checks,
    agent_exceptions,
    neutron_l3ha,
    service_checks,
    octavia_agent_checks,
)


APT_UCA = """
# Ubuntu Cloud Archive
deb http://ubuntu-cloud.archive.canonical.com/ubuntu bionic-updates/{} main
"""

SVC_CONF = """
debug = True
"""

JOURNALCTL_OVS_CLEANUP_GOOD = """
-- Logs begin at Thu 2021-04-29 17:44:42 BST, end at Thu 2021-05-06 09:05:01 BST. --
Apr 29 17:52:37 juju-9c28ce-ubuntu-11 systemd[1]: Starting OpenStack Neutron OVS cleanup...
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 sudo[15179]:  neutron : TTY=unknown ; PWD=/var/lib/neutron ; USER=root ; COMMAND=/usr/bin/neutron-rootwrap /etc/neutron/r
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 sudo[15179]: pam_unix(sudo:session): session opened for user root by (uid=0)
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 ovs-vsctl[15183]: ovs|00001|vsctl|INFO|Called as /usr/bin/ovs-vsctl --timeout=5 --id=@manager -- create Manager "target=\
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 sudo[15179]: pam_unix(sudo:session): session closed for user root
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 systemd[1]: Started OpenStack Neutron OVS cleanup.
May 03 06:17:29 juju-9c28ce-ubuntu-11 systemd[1]: Stopped OpenStack Neutron OVS cleanup.
-- Reboot --
May 04 11:05:56 juju-9c28ce-ubuntu-11 systemd[1]: Starting OpenStack Neutron OVS cleanup...
May 04 11:06:20 juju-9c28ce-ubuntu-11 systemd[1]: Started OpenStack Neutron OVS cleanup.
"""  # noqa

JOURNALCTL_OVS_CLEANUP_BAD = """
-- Logs begin at Thu 2021-04-29 17:44:42 BST, end at Thu 2021-05-06 09:05:01 BST. --
Apr 29 17:52:37 juju-9c28ce-ubuntu-11 systemd[1]: Starting OpenStack Neutron OVS cleanup...
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 sudo[15179]:  neutron : TTY=unknown ; PWD=/var/lib/neutron ; USER=root ; COMMAND=/usr/bin/neutron-rootwrap /etc/neutron/r
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 sudo[15179]: pam_unix(sudo:session): session opened for user root by (uid=0)
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 ovs-vsctl[15183]: ovs|00001|vsctl|INFO|Called as /usr/bin/ovs-vsctl --timeout=5 --id=@manager -- create Manager "target=\
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 sudo[15179]: pam_unix(sudo:session): session closed for user root
Apr 29 17:52:39 juju-9c28ce-ubuntu-11 systemd[1]: Started OpenStack Neutron OVS cleanup.
May 03 06:17:29 juju-9c28ce-ubuntu-11 systemd[1]: Stopped OpenStack Neutron OVS cleanup.
May 04 10:05:56 juju-9c28ce-ubuntu-11 systemd[1]: Starting OpenStack Neutron OVS cleanup...
May 04 10:06:20 juju-9c28ce-ubuntu-11 systemd[1]: Started OpenStack Neutron OVS cleanup.
-- Reboot --
May 04 11:05:56 juju-9c28ce-ubuntu-11 systemd[1]: Starting OpenStack Neutron OVS cleanup...
May 04 11:06:20 juju-9c28ce-ubuntu-11 systemd[1]: Started OpenStack Neutron OVS cleanup.
"""  # noqa


with open(os.path.join(os.environ['DATA_ROOT'],
                       "sos_commands/networking/ip_-s_-d_link")) as fd:
    IP_LINK_SHOW = fd.readlines()


def fake_ip_link_show_w_errors_drops():
    lines = ''.join(IP_LINK_SHOW).format(10000000, 100000000)
    return [line + '\n' for line in lines.split('\n')]


def fake_ip_link_show_no_errors_drops():
    lines = ''.join(IP_LINK_SHOW).format(0, 0)
    return [line + '\n' for line in lines.split('\n')]


class TestOpenstackPluginPartOpenstackServices(utils.BaseTestCase):

    @mock.patch.object(openstack_services, "OPENSTACK_INFO", {})
    def test_get_service_info(self):
        expected = ['beam.smp (1)',
                    'haproxy (1)',
                    'keepalived (2)',
                    'neutron-keepalived-state-change (2)',
                    'neutron-ovn-metadata-agent (3)',
                    'nova-api-metadata (5)',
                    'nova-compute (1)',
                    'qemu-system-x86_64 (1)']
        openstack_services.get_openstack_service_checker()()
        self.assertEqual(openstack_services.OPENSTACK_INFO["services"],
                         expected)

    @mock.patch.object(openstack_services, "OPENSTACK_INFO", {})
    def test_get_release_info(self):
        with tempfile.TemporaryDirectory() as dtmp:
            for rel in ["stein", "ussuri", "train"]:
                with open(os.path.join(dtmp,
                                       "cloud-archive-{}.list".format(rel)),
                          'w') as fd:
                    fd.write(APT_UCA.format(rel))

            with mock.patch.object(openstack_services, "APT_SOURCE_PATH",
                                   dtmp):
                openstack_services.get_openstack_service_checker()()
                self.assertEqual(openstack_services.OPENSTACK_INFO["release"],
                                 "ussuri")

    @mock.patch.object(openstack_services, "OPENSTACK_INFO", {})
    def test_get_debug_log_info(self):
        expected = {'neutron': True, 'nova': True}
        with tempfile.TemporaryDirectory() as dtmp:
            for svc in ["nova", "neutron"]:
                conf_path = "etc/{svc}/{svc}.conf".format(svc=svc)
                os.makedirs(os.path.dirname(os.path.join(dtmp, conf_path)))
                with open(os.path.join(dtmp, conf_path), 'w') as fd:
                    fd.write(SVC_CONF)

            with mock.patch.object(openstack_services.constants,
                                   "DATA_ROOT", dtmp):
                openstack_services.get_openstack_service_checker()()
                result = openstack_services.OPENSTACK_INFO[
                                                       'debug-logging-enabled']
                self.assertEqual(result, expected)


class TestOpenstackPluginPartVm_info(utils.BaseTestCase):

    @mock.patch.object(vm_info, "VM_INFO", {})
    def test_get_vm_checks(self):
        vm_info.get_vm_checks()()
        self.assertEquals(vm_info.VM_INFO["instances"],
                          ["09461f0b-297b-4ef5-9053-dd369c86b96b"])


class TestOpenstackPluginPartNova_external_events(utils.BaseTestCase):

    @mock.patch.object(nova_external_events, "EXT_EVENT_INFO", {})
    def test_get_events(self):
        data_root = nova_external_events.constants.DATA_ROOT
        data_source = os.path.join(data_root, "var/log/nova")
        nova_external_events.get_events("network-vif-plugged", data_source)
        events = {'network-vif-plugged':
                  {"succeeded":
                   [{"instance": 'd2666e01-73c8-4a97-9c22-0c175659e6db',
                     "port": "f6f5e6c5-2fdd-4719-9489-ca385d7fa7a7"},
                    {"instance": 'd2666e01-73c8-4a97-9c22-0c175659e6db',
                     "port": "1824336a-4bc3-46bb-9c08-bc86b1d24226"}],
                   "failed": [
                       {"instance": '5b367a10-9e6a-4eb9-9c7d-891dab7e87fa',
                        "port": "9a3673bf-58ac-423a-869a-6c4ae801b57b"}]}}
        self.assertEquals(nova_external_events.EXT_EVENT_INFO, events)


class TestOpenstackPluginPartPackage_info(utils.BaseTestCase):

    @mock.patch.object(package_info, 'OST_PKG_INFO', {})
    def test_get_pkg_info(self):
        expected = [
            'ceilometer-agent-compute 1:10.0.1-0ubuntu0.18.04.2~cloud0',
            'ceilometer-common 1:10.0.1-0ubuntu0.18.04.2~cloud0',
            'conntrack 1:1.4.3-3',
            'dnsmasq-base 2.79-1~cloud0',
            'dnsmasq-utils 2.79-1~cloud0',
            'haproxy 1.6.3-1ubuntu0.3',
            'keepalived 1:1.3.9-1ubuntu0.18.04.2~cloud1',
            'libvirt-daemon 4.0.0-1ubuntu8.15~cloud0',
            'libvirt-daemon-driver-storage-rbd 4.0.0-1ubuntu8.15~cloud0',
            'libvirt-daemon-system 4.0.0-1ubuntu8.15~cloud0',
            'mysql-common 5.7.33-0ubuntu0.16.04.1',
            'neutron-common 2:12.1.0-0ubuntu1~cloud0',
            'neutron-dhcp-agent 2:12.1.0-0ubuntu1~cloud0',
            'neutron-l3-agent 2:12.1.0-0ubuntu1~cloud0',
            'neutron-metadata-agent 2:12.1.0-0ubuntu1~cloud0',
            'neutron-openvswitch-agent 2:12.1.0-0ubuntu1~cloud0',
            'nova-api-metadata 2:17.0.12-0ubuntu1~cloud0',
            'nova-common 2:17.0.12-0ubuntu1~cloud0',
            'nova-compute 2:17.0.12-0ubuntu1~cloud0',
            'nova-compute-kvm 2:17.0.12-0ubuntu1~cloud0',
            'nova-compute-libvirt 2:17.0.12-0ubuntu1~cloud0',
            'octavia-api 6.1.0-0ubuntu1~cloud0',
            'octavia-common 6.1.0-0ubuntu1~cloud0',
            'octavia-health-manager 6.1.0-0ubuntu1~cloud0',
            'octavia-housekeeping 6.1.0-0ubuntu1~cloud0',
            'octavia-worker 6.1.0-0ubuntu1~cloud0',
            'python-barbicanclient 4.6.0-0ubuntu1~cloud0',
            'python-ceilometer 1:10.0.1-0ubuntu0.18.04.2~cloud0',
            'python-ceilometerclient 2.9.0-0ubuntu1~cloud0',
            'python-cinderclient 1:3.5.0-0ubuntu1~cloud0',
            'python-designateclient 2.9.0-0ubuntu1~cloud0',
            'python-glanceclient 1:2.9.1-0ubuntu1~cloud0',
            'python-keystone 2:13.0.2-0ubuntu3~cloud0',
            'python-keystoneauth1 3.4.0-0ubuntu1~cloud0',
            'python-keystoneclient 1:3.15.0-0ubuntu1~cloud0',
            'python-keystonemiddleware 4.21.0-0ubuntu1~cloud0',
            'python-neutron 2:12.1.0-0ubuntu1~cloud0',
            'python-neutron-fwaas 1:12.0.1-0ubuntu1~cloud0',
            'python-neutron-lib 1.13.0-0ubuntu1~cloud0',
            'python-neutronclient 1:6.7.0-0ubuntu1~cloud0',
            'python-nova 2:17.0.12-0ubuntu1~cloud0',
            'python-novaclient 2:9.1.1-0ubuntu1~cloud0',
            'python-oslo.cache 1.28.0-0ubuntu1~cloud0',
            'python-oslo.concurrency 3.25.0-0ubuntu1~cloud0',
            'python-oslo.config 1:5.2.0-0ubuntu1~cloud0',
            'python-oslo.context 1:2.20.0-0ubuntu1~cloud0',
            'python-oslo.db 4.33.0-0ubuntu1~cloud0',
            'python-oslo.i18n 3.19.0-0ubuntu1~cloud0',
            'python-oslo.log 3.36.0-0ubuntu1~cloud0',
            'python-oslo.messaging 5.35.0-0ubuntu1~cloud0',
            'python-oslo.middleware 3.34.0-0ubuntu1~cloud0',
            'python-oslo.policy 1.33.1-0ubuntu2~cloud0',
            'python-oslo.privsep 1.27.0-0ubuntu3~cloud0',
            'python-oslo.reports 1.26.0-0ubuntu1~cloud0',
            'python-oslo.rootwrap 5.13.0-0ubuntu1~cloud0',
            'python-oslo.serialization 2.24.0-0ubuntu2~cloud0',
            'python-oslo.service 1.29.0-0ubuntu1~cloud0',
            'python-oslo.utils 3.35.0-0ubuntu1~cloud0',
            'python-oslo.versionedobjects 1.31.2-0ubuntu3~cloud0',
            'python-swiftclient 1:3.5.0-0ubuntu1~cloud0',
            'python3-octavia 6.1.0-0ubuntu1~cloud0',
            'python3-octavia-lib 2.0.0-0ubuntu1~cloud0',
            'qemu-kvm 1:2.11+dfsg-1ubuntu7.23~cloud0']
        package_info.get_checks()()
        self.assertEquals(package_info.OST_PKG_INFO['dpkg'], expected)


class TestOpenstackPluginPartNetwork(utils.BaseTestCase):

    @mock.patch.object(network.cli_helpers, 'get_ip_link_show',
                       fake_ip_link_show_w_errors_drops)
    def test_get_port_stat_by_name(self):
        c = network.OpenstackNetworkChecks()
        stats = c._get_port_stats(name="bond1")
        self.assertEqual(stats, {'dropped': '100000000 (8%)'})

    @mock.patch.object(network.cli_helpers, 'get_ip_link_show',
                       fake_ip_link_show_no_errors_drops)
    def test_get_port_stat_by_name_no_problems(self):
        c = network.OpenstackNetworkChecks()
        stats = c._get_port_stats(name="bond1")
        self.assertEqual(stats, {})

    @mock.patch.object(network.cli_helpers, 'get_ip_link_show',
                       fake_ip_link_show_w_errors_drops)
    def test_get_port_stat_by_mac(self):
        c = network.OpenstackNetworkChecks()
        stats = c._get_port_stats(mac="ac:1f:6b:9e:d8:44")
        self.assertEqual(stats, {'errors': '10000000 (5%)'})

    def test_find_interface_name_by_ip_address(self):
        addr = "10.10.101.33"
        c = network.OpenstackNetworkChecks()
        name = c._find_interface_name_by_ip_address(addr)
        self.assertEqual(name, "br-bond1")

    @mock.patch.object(network, "NETWORK_INFO", {})
    def test_get_ns_info(self):
        ns_info = {'namespaces': {'qdhcp': 35, 'qrouter': 35, 'fip': 1}}
        c = network.OpenstackNetworkChecks()
        c.get_ns_info()
        self.assertEqual(ns_info, network.NETWORK_INFO)

    @mock.patch.object(network.cli_helpers, "get_ip_netns", lambda: [])
    def test_get_ns_info_none(self):
        c = network.OpenstackNetworkChecks()
        ns_info = c.get_ns_info()
        self.assertEqual(ns_info, None)

    @mock.patch.object(network, "NETWORK_INFO", {})
    def test_get_network_checker(self):
        expected = {'config':
                    {'neutron':
                     {'local_ip': '10.10.102.53 (bond1.4003@bond1)'}},
                    'namespaces':
                    {'fip': 1, 'qdhcp': 35, 'qrouter': 35},
                    'port-health':
                    {'phy-ports':
                     {'bond1.4003@bond1': {
                      'dropped': '131579034 (15%)'}}}}
        network.get_network_checker()()
        self.assertEqual(network.NETWORK_INFO, expected)


class TestOpenstackPluginPartService_features(utils.BaseTestCase):

    @mock.patch.object(service_features, "SERVICE_FEATURES", {})
    def test_get_service_features(self):
        service_features.get_service_features()
        expected = {'neutron': {'neutron': {'availability_zone': 'AZ1'}}}
        self.assertEqual(service_features.SERVICE_FEATURES, expected)


class TestOpenstackPluginPartCpu_pinning_check(utils.BaseTestCase):

    def test_cores_to_list(self):
        ret = cpu_pinning_check.cores_to_list("0-4,8,9,28-32")
        self.assertEqual(ret, [0, 1, 2, 3, 4, 8, 9, 28, 29, 30, 31, 32])


class TestOpenstackPluginPartAgent_checks(utils.BaseTestCase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # These are static but that should be fine since they would be in a
        # real scenario.
        neutron_agent_checks.checks.os.environ["PLUGIN_NAME"] = "openstack"
        neutron_agent_checks.checks.constants.PLUGIN_YAML_DEFS = \
            os.path.join(utils.TESTS_DIR, "plugins/openstack/defs")

    def test_process_rpc_loop_results(self):
        end = datetime.datetime(2021, 3, 2, 14, 26, 55, 682000)
        start = datetime.datetime(2021, 3, 2, 14, 26, 29, 780000)
        expected = {'rpc-loop': {"top": {"1438": {'duration': 25.9,
                                                  'end': end,
                                                  'start': start}},
                                 "stats": {"min": 25.9,
                                           "max": 25.9,
                                           "stdev": 0.0,
                                           "avg": 25.9,
                                           "samples": 1}}}
        s = searchtools.FileSearcher()
        root_key = "neutron-agent-checks"
        group_key = "neutron-ovs-agent"
        c = neutron_agent_checks.NeutronAgentEventChecks(s, root_key)
        c.register_search_terms()
        results = c.process_results(s.search())
        self.assertEqual(results.get(group_key), expected)

    @mock.patch.object(neutron_agent_checks.checks, "add_known_bug")
    def test_get_agents_bugs(self, mock_add_known_bug):
        s = searchtools.FileSearcher()
        c = neutron_agent_checks.NeutronAgentBugChecks(s, "neutron")
        c.register_search_terms()
        results = c.process_results(s.search())
        self.assertEqual(results, None)
        calls = [mock.call("1896506",
                           ('identified in syslog')),
                 mock.call("1929832",
                           ('identified in neutron-l3-agent logs'))]
        mock_add_known_bug.assert_has_calls(calls)

    def test_get_router_event_stats(self):
        router = '9b8efc4c-305b-48ce-a5bd-624bc5eeee67'
        spawn_start = datetime.datetime(2021, 3, 25, 18, 10, 14, 747000)
        spawn_end = datetime.datetime(2021, 3, 25, 18, 10, 50, 838000)
        update_start = datetime.datetime(2021, 3, 25, 18, 9, 54, 720000)
        update_end = datetime.datetime(2021, 3, 25, 18, 10, 36, 942000)
        expected = {'router-spawn-events': {'stats': {'avg': 36.09,
                                                      'max': 36.09,
                                                      'min': 36.09,
                                                      'samples': 1,
                                                      'stdev': 0.0},
                                            'top': {router:
                                                    {'duration': 36.09,
                                                     'end': spawn_end,
                                                     'start': spawn_start}}},
                    'router-updates': {'stats': {'avg': 28.14,
                                                 'max': 42.22,
                                                 'min': 14.07,
                                                 'samples': 2,
                                                 'stdev': 14.07},
                                       'top': {router:
                                               {'duration': 42.22,
                                                'end': update_end,
                                                'start': update_start}}}}

        s = searchtools.FileSearcher()
        root_key = "neutron-agent-checks"
        group_key = "neutron-l3-agent"
        c = neutron_agent_checks.NeutronAgentEventChecks(s, root_key)
        c.register_search_terms()
        results = c.process_results(s.search())
        self.assertEqual(results.get(group_key), expected)

    @mock.patch.object(neutron_agent_checks, "NeutronAgentEventChecks")
    @mock.patch.object(neutron_agent_checks, "NeutronAgentBugChecks")
    def test_run_neutron_agent_checks(self, mock_agent_bug_checks,
                                      mock_agent_event_checks):
        neutron_agent_checks.run_agent_checks()
        self.assertTrue(mock_agent_bug_checks.called)
        self.assertTrue(mock_agent_event_checks.called)


class TestOpenstackPluginPartAgentExceptions(utils.BaseTestCase):

    def test_get_agent_exceptions(self):
        neutron_expected = {'neutron-openvswitch-agent':
                            {'MessagingTimeout': {'2021-03-04': 2},
                             'AMQP server on 10.10.123.22:5672 is unreachable':
                             {'2021-03-04': 3},
                             'OVS is dead': {'2021-03-29': 1},
                             'RuntimeError': {'2021-03-29': 3}},
                            'neutron-l3-agent':
                            {'neutron_lib.exceptions.ProcessExecutionError':
                             {'2021-05-18': 1,
                              '2021-05-26': 1}},
                            }
        nova_expected = {'nova-api-wsgi':
                         {'OSError: Server unexpectedly closed connection':
                          {'2021-03-15': 1},
                          'AMQP server on 10.5.1.98:5672 is unreachable':
                          {'2021-03-15': 1},
                          'amqp.exceptions.ConnectionForced':
                          {'2021-03-15': 1}},
                         'nova-compute':
                         {'DBConnectionError': {'2021-03-08': 2}}}
        barbican_expected = {'barbican-api':
                             {'UnicodeDecodeError': {'2021-05-04': 1}}}
        expected = {"nova": nova_expected, "neutron": neutron_expected,
                    "barbican": barbican_expected}
        s = searchtools.FileSearcher()
        c = agent_exceptions.CommonAgentChecks(s)
        c.register_search_terms()
        results = c.process_results(s.search())
        self.assertEqual(results, expected)

    @mock.patch.object(agent_exceptions, "CommonAgentChecks")
    @mock.patch.object(agent_exceptions, "AGENT_CHECKS_RESULTS",
                       {"agent-exceptions": {}})
    def test_run_agent_checks(self, mock_common_agent_checks):
        c = mock_common_agent_checks.return_value
        c.process_results.return_value = "r1"

        agent_exceptions.run_agent_exception_checks()
        self.assertTrue(mock_common_agent_checks.called)
        # results should be empty if we have mocked everything
        self.assertEqual(agent_exceptions.AGENT_CHECKS_RESULTS,
                         {"agent-exceptions": "r1"})


class TestOpenstackPluginPartNeutronL3HA_checks(utils.BaseTestCase):

    @mock.patch.object(neutron_l3ha, "L3HA_CHECKS", {})
    def test_run_checks(self):
        expected = {'agent': {
                     'backup': ['71d46ba3-f737-41bd-a922-8b8012a6444d'],
                     'master': ['19c40509-225e-49f9-80df-e3c5873f4e64']},
                    'keepalived': {
                     'transitions': {
                      '19c40509-225e-49f9-80df-e3c5873f4e64': {
                       '2021-05-05': 3
                       }
                      }
                     }
                    }
        neutron_l3ha.run_checks()()
        self.assertEqual(neutron_l3ha.L3HA_CHECKS, expected)

    @mock.patch.object(neutron_l3ha.constants, "USE_ALL_LOGS", False)
    @mock.patch.object(neutron_l3ha.issues_utils, "add_issue")
    @mock.patch.object(neutron_l3ha, "VRRP_TRANSITION_WARN_THRESHOLD", 1)
    @mock.patch.object(neutron_l3ha, "L3HA_CHECKS", {})
    def test_run_checks_w_issue(self, mock_add_issue):
        expected = {'agent': {
                     'backup': ['71d46ba3-f737-41bd-a922-8b8012a6444d'],
                     'master': ['19c40509-225e-49f9-80df-e3c5873f4e64']},
                    'keepalived': {
                     'transitions': {
                      '19c40509-225e-49f9-80df-e3c5873f4e64': {
                       '2021-05-05': 3
                       }
                      }
                     }
                    }
        neutron_l3ha.run_checks()()
        self.assertEqual(neutron_l3ha.L3HA_CHECKS, expected)
        self.assertTrue(mock_add_issue.called)


class TestOpenstackPluginPartServiceChecks(utils.BaseTestCase):

    @mock.patch.object(service_checks.cli_helpers, "get_journalctl")
    @mock.patch.object(service_checks.issues_utils, "add_issue")
    def test_run_service_checks(self, mock_add_issue, mock_get_journalctl):
        mock_get_journalctl.return_value = \
            JOURNALCTL_OVS_CLEANUP_GOOD.splitlines(keepends=True)
        service_checks.run_service_checks()()
        self.assertFalse(mock_add_issue.called)

    @mock.patch.object(service_checks.cli_helpers, "get_journalctl")
    @mock.patch.object(service_checks.issues_utils, "add_issue")
    def test_run_service_checks_w_issue(self, mock_add_issue,
                                        mock_get_journalctl):
        mock_get_journalctl.return_value = \
            JOURNALCTL_OVS_CLEANUP_BAD.splitlines(keepends=True)
        service_checks.run_service_checks()()
        self.assertTrue(mock_add_issue.called)


class TestOpenstackPluginPartOctaviaLBs(utils.BaseTestCase):

    @mock.patch.object(octavia_agent_checks, "LB_CHECKS", {})
    def test_get_lb_failovers(self):
        expected = {'amp-missed-heartbeats': {
                     '2021-06-01': {
                      '3604bf2a-ee51-4135-97e2-ec08ed9321db': 1,
                      }},
                    'lb-failovers': {
                     'auto': {
                      '2021-03-09': {
                          '7a3b90ed-020e-48f0-ad6f-b28443fa2277': 1,
                          '98aefcff-60e5-4087-8ca6-5087ae970440': 1,
                          '9cd90142-5501-4362-93ef-1ad219baf45a': 1,
                          'e9cb98af-9c21-4cf6-9661-709179ce5733': 1,
                        }
                      }
                     }
                    }
        octavia_agent_checks.run_checks()()
        self.assertEqual(octavia_agent_checks.LB_CHECKS, expected)
