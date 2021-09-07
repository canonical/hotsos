import os

import datetime
import mock
import tempfile

import utils

from core import checks
import core.plugins.openstack as openstack_core
from plugins.openstack.pyparts import (
    openstack_info,
    vm_info,
    nova_external_events,
    package_info,
    network,
    service_features,
    cpu_pinning_check,
    agent_checks,
    agent_exceptions,
    neutron_l3ha,
    service_checks,
    config_checks,
)


APT_UCA = """
# Ubuntu Cloud Archive
deb http://ubuntu-cloud.archive.canonical.com/ubuntu bionic-updates/{} main
"""

SVC_CONF = """
[DEFAULT]
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


class TestOpenstackBase(utils.BaseTestCase):

    IP_LINK_SHOW = None

    def fake_ip_link_w_errors_drops(self):
        lines = ''.join(self.IP_LINK_SHOW).format(10000000, 100000000)
        return [line + '\n' for line in lines.split('\n')]

    def fake_ip_link_no_errors_drops(self):
        lines = ''.join(self.IP_LINK_SHOW).format(0, 0)
        return [line + '\n' for line in lines.split('\n')]

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        os.environ["PLUGIN_NAME"] = "openstack"

        if self.IP_LINK_SHOW is None:
            path = os.path.join(os.environ['DATA_ROOT'],
                                "sos_commands/networking/ip_-s_-d_link")
            with open(path) as fd:
                self.IP_LINK_SHOW = fd.readlines()


class TestOpenstackPluginPartOpenstackServices(TestOpenstackBase):

    def test_get_service_info(self):
        expected = ['apache2 (6)',
                    'dnsmasq (1)',
                    'glance-api (5)',
                    'haproxy (7)',
                    'keepalived (2)',
                    'mysqld (1)',
                    'neutron-dhcp-agent (1)',
                    'neutron-keepalived-state-change (2)',
                    'neutron-l3-agent (1)',
                    'neutron-metadata-agent (5)',
                    'neutron-openvswitch-agent (1)',
                    'neutron-server (11)',
                    'nova-api-metadata (5)',
                    'nova-compute (1)',
                    'qemu-system-x86_64 (2)',
                    'vault (1)']
        inst = openstack_info.OpenstackInfo()
        inst()
        self.assertEqual(inst.output["services"], expected)

    def test_get_release_info(self):
        with tempfile.TemporaryDirectory() as dtmp:
            for rel in ["stein", "ussuri", "train"]:
                with open(os.path.join(dtmp,
                                       "cloud-archive-{}.list".format(rel)),
                          'w') as fd:
                    fd.write(APT_UCA.format(rel))

            with mock.patch.object(openstack_core, "APT_SOURCE_PATH",
                                   dtmp):
                inst = openstack_info.OpenstackInfo()
                inst()
                self.assertEqual(inst.output["release"], "ussuri")

    def test_get_debug_log_info(self):
        expected = {'neutron': True, 'nova': True}
        with tempfile.TemporaryDirectory() as dtmp:
            for svc in ["nova", "neutron"]:
                conf_path = "etc/{svc}/{svc}.conf".format(svc=svc)
                os.makedirs(os.path.dirname(os.path.join(dtmp, conf_path)))
                with open(os.path.join(dtmp, conf_path), 'w') as fd:
                    fd.write(SVC_CONF)

            os.environ["DATA_ROOT"] = dtmp
            inst = openstack_info.OpenstackInfo()
            # fake some core packages
            inst.apt_check._core_packages = {"foo": 1}
            inst()
            self.assertEqual(inst.output["debug-logging-enabled"],
                             expected)


class TestOpenstackPluginPartVm_info(TestOpenstackBase):

    def test_get_vm_checks(self):
        expected = {"vm-info": {
                        "running": ['29bcaff8-3d85-43cb-b76f-01bad0e1d568',
                                    'c050e183-c808-43f9-bdb4-02e95fad58e2'],
                        "vcpu-info": {
                            "available-cores": 2,
                            "system-cores": 2,
                            "used": 2,
                            "overcommit-factor": 1.0,
                            }
                        }
                    }
        inst = vm_info.OpenstackInstanceChecks()
        inst()
        self.assertEquals(inst.output, expected)


class TestOpenstackPluginPartNovaExternalEvents(TestOpenstackBase):

    def test_get_events(self):
        inst = nova_external_events.NovaExternalEventChecks()
        inst()
        events = {'network-changed':
                  {"succeeded":
                   [{"port": "03c4d61b-60b0-4f1e-b29c-2554e0c78afd",
                     "instance": "29bcaff8-3d85-43cb-b76f-01bad0e1d568"},
                    {"port": "0906171f-17bb-478f-b8fa-9904983b26af",
                     "instance": "c050e183-c808-43f9-bdb4-02e95fad58e2"}]},
                  'network-vif-plugged':
                  {"succeeded":
                   [{"instance": '29bcaff8-3d85-43cb-b76f-01bad0e1d568',
                     "port": "03c4d61b-60b0-4f1e-b29c-2554e0c78afd"},
                    {"instance": 'c050e183-c808-43f9-bdb4-02e95fad58e2',
                     "port": "0906171f-17bb-478f-b8fa-9904983b26af"}]}}
        self.assertEquals(inst.output["os-server-external-events"], events)


class TestOpenstackPluginPartPackage_info(TestOpenstackBase):

    def test_get_pkg_info(self):
        expected = [
            'conntrack 1:1.4.5-2',
            'dnsmasq-base 2.80-1.1ubuntu1.4',
            'dnsmasq-utils 2.80-1.1ubuntu1.4',
            'haproxy 2.0.13-2ubuntu0.1',
            'keepalived 1:2.0.19-2',
            'keystone-common 2:17.0.0-0ubuntu0.20.04.1',
            'libvirt-daemon 6.0.0-0ubuntu8.11',
            'libvirt-daemon-driver-qemu 6.0.0-0ubuntu8.11',
            'libvirt-daemon-driver-storage-rbd 6.0.0-0ubuntu8.11',
            'libvirt-daemon-system 6.0.0-0ubuntu8.11',
            'libvirt-daemon-system-systemd 6.0.0-0ubuntu8.11',
            'mysql-common 5.8+1.0.5ubuntu2',
            'neutron-common 2:16.4.0-0ubuntu2',
            'neutron-dhcp-agent 2:16.4.0-0ubuntu2',
            'neutron-fwaas-common 1:16.0.0-0ubuntu0.20.04.1',
            'neutron-l3-agent 2:16.4.0-0ubuntu2',
            'neutron-metadata-agent 2:16.4.0-0ubuntu2',
            'neutron-openvswitch-agent 2:16.4.0-0ubuntu2',
            'nova-api-metadata 2:21.2.1-0ubuntu1',
            'nova-common 2:21.2.1-0ubuntu1',
            'nova-compute 2:21.2.1-0ubuntu1',
            'nova-compute-kvm 2:21.2.1-0ubuntu1',
            'nova-compute-libvirt 2:21.2.1-0ubuntu1',
            'python3-barbicanclient 4.10.0-0ubuntu1',
            'python3-cinderclient 1:7.0.0-0ubuntu1',
            'python3-designateclient 2.11.0-0ubuntu2',
            'python3-glanceclient 1:3.1.1-0ubuntu1',
            'python3-keystone 2:17.0.0-0ubuntu0.20.04.1',
            'python3-keystoneauth1 4.0.0-0ubuntu1',
            'python3-keystoneclient 1:4.0.0-0ubuntu1',
            'python3-keystonemiddleware 9.0.0-0ubuntu1',
            'python3-neutron 2:16.4.0-0ubuntu2',
            'python3-neutron-fwaas 1:16.0.0-0ubuntu0.20.04.1',
            'python3-neutron-lib 2.3.0-0ubuntu1',
            'python3-neutronclient 1:7.1.1-0ubuntu1',
            'python3-nova 2:21.2.1-0ubuntu1',
            'python3-novaclient 2:17.0.0-0ubuntu1',
            'python3-oslo.cache 2.3.0-0ubuntu1',
            'python3-oslo.concurrency 4.0.2-0ubuntu1',
            'python3-oslo.config 1:8.0.2-0ubuntu1',
            'python3-oslo.context 1:3.0.2-0ubuntu1',
            'python3-oslo.db 8.1.0-0ubuntu1',
            'python3-oslo.i18n 4.0.1-0ubuntu1',
            'python3-oslo.log 4.1.1-0ubuntu1',
            'python3-oslo.messaging 12.1.0-0ubuntu1',
            'python3-oslo.middleware 4.0.2-0ubuntu1',
            'python3-oslo.policy 3.1.0-0ubuntu1.1',
            'python3-oslo.privsep 2.1.1-0ubuntu1',
            'python3-oslo.reports 2.0.1-0ubuntu1',
            'python3-oslo.rootwrap 6.0.2-0ubuntu1',
            'python3-oslo.serialization 3.1.1-0ubuntu1',
            'python3-oslo.service 2.1.1-0ubuntu1.1',
            'python3-oslo.upgradecheck 1.0.1-0ubuntu1',
            'python3-oslo.utils 4.1.1-0ubuntu1',
            'python3-oslo.versionedobjects 2.0.1-0ubuntu1',
            'python3-oslo.vmware 3.3.1-0ubuntu1',
            'qemu-kvm 1:4.2-3ubuntu6.17']
        inst = package_info.OpenstackPackageChecks()
        inst()
        self.assertEquals(inst.output["dpkg"], expected)

    def test_get_docker_info(self):
        expected = ['libvirt-exporter 1.1.0',
                    'ubuntu-source-ceilometer-compute 10.2.0',
                    'ubuntu-source-chrony 10.2.0',
                    'ubuntu-source-cron 10.2.0',
                    'ubuntu-source-iscsid 10.2.0',
                    'ubuntu-source-kolla-toolbox 10.2.0',
                    'ubuntu-source-masakari-monitors 10.2.0',
                    'ubuntu-source-multipathd 10.2.0',
                    'ubuntu-source-neutron-dhcp-agent 10.2.0',
                    'ubuntu-source-neutron-metadata-agent 10.2.0',
                    'ubuntu-source-neutron-openvswitch-agent 10.2.0',
                    'ubuntu-source-nova-compute 10.2.0',
                    'ubuntu-source-nova-libvirt 10.2.0',
                    'ubuntu-source-nova-ssh 10.2.0',
                    'ubuntu-source-openvswitch-db-server 10.2.0',
                    'ubuntu-source-openvswitch-vswitchd 10.2.0',
                    'ubuntu-source-prometheus-node-exporter 10.2.0']

        inst = package_info.OpenstackDockerImageChecks()
        inst()
        self.assertEquals(inst.output["docker-images"], expected)

    def test_pkgbugchecks(self):
        os.environ['PLUGIN_NAME'] = 'openstack'
        with mock.patch.object(checks, 'add_known_bug') as mock_add_known_bug:
            obj = package_info.OpenstackPackageBugChecks()
            obj()
            self.assertTrue(mock_add_known_bug.called)


class TestOpenstackPluginPartNetwork(TestOpenstackBase):

    def test_get_ns_info(self):
        ns_info = {'namespaces': {'qdhcp': 1, 'qrouter': 1, 'fip': 1,
                                  'snat': 1}}
        inst = network.OpenstackNetworkChecks()
        inst.get_ns_info()
        self.assertEqual(inst.output["network"], ns_info)

    @mock.patch.object(network, 'CLIHelper')
    def test_get_ns_info_none(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.ip_link.return_value = []
        inst = network.OpenstackNetworkChecks()
        inst.get_ns_info()
        self.assertEqual(inst.output, None)

    def test_get_network_checker(self):
        expected = {'config':
                    {'nova':
                        {'my_ip': '10.0.0.49 (br-ens3)'},
                     'neutron':
                        {'local_ip': '10.0.0.49 (br-ens3)'}},
                    'namespaces':
                        {'fip': 1, 'qdhcp': 1, 'qrouter': 1, 'snat': 1},
                    'port-health':
                        {'phy-ports':
                         {'br-ens3': {
                             'rx': {'dropped': '131579 (36%)'}}}}}
        inst = network.OpenstackNetworkChecks()
        inst()
        self.assertEqual(inst.output["network"], expected)


class TestOpenstackPluginPartService_features(TestOpenstackBase):

    def test_get_service_features(self):
        inst = service_features.ServiceFeatureChecks()
        inst.get_service_features()
        expected = {'neutron': {'dhcp-agent': {
                                    'enable_isolated_metadata': True,
                                    'enable_metadata_network': True,
                                    'ovs_use_veth': False},
                                'l3-agent': {
                                    'agent_mode': 'dvr_snat'},
                                'neutron': {
                                    'availability_zone': 'nova'},
                                'openvswitch-agent': {
                                    'l2_population': True,
                                    'firewall_driver': 'openvswitch'}}}
        self.assertEqual(inst.output["features"], expected)


class TestOpenstackPluginPartCpu_pinning_check(TestOpenstackBase):

    def test_cores_to_list(self):
        ret = checks.ConfigBase.expand_value_ranges("0-4,8,9,28-32")
        self.assertEqual(ret, [0, 1, 2, 3, 4, 8, 9, 28, 29, 30, 31, 32])

    def test_pinning_checker(self):
        expected = {'cpu-pinning-checks': {
                        'input': {
                            'systemd': {
                                'cpuaffinity': '0-7,32-39'
                                }
                            }
                        }
                    }
        inst = cpu_pinning_check.CPUPinningChecker()
        self.assertEquals(inst.output, expected)


class TestOpenstackPluginPartAgentChecks(TestOpenstackBase):

    def test_process_rpc_loop_results(self):
        expected = {'rpc-loop': {
                        'top': {
                            '1329': {
                                'start':
                                    datetime.datetime(2021, 8, 3, 10, 29, 51,
                                                      272000),
                                'end':
                                    datetime.datetime(2021, 8, 3, 10, 29, 56,
                                                      861000),
                                'duration': 5.59},
                            '1328': {
                                'start':
                                    datetime.datetime(2021, 8, 3, 10, 29, 48,
                                                      591000),
                                'end':
                                    datetime.datetime(2021, 8, 3, 10, 29, 51,
                                                      271000),
                                'duration': 2.68},
                            '55': {
                                'start':
                                    datetime.datetime(2021, 8, 3, 9, 47, 20,
                                                      938000),
                                'end':
                                    datetime.datetime(2021, 8, 3, 9, 47, 22,
                                                      166000),
                                'duration': 1.23},
                            '41': {
                                'start':
                                    datetime.datetime(2021, 8, 3, 9, 46, 52,
                                                      597000),
                                'end':
                                    datetime.datetime(2021, 8, 3, 9, 46, 54,
                                                      923000),
                                'duration': 2.33},
                            '40': {
                                'start':
                                    datetime.datetime(2021, 8, 3, 9, 46, 50,
                                                      151000),
                                'end':
                                    datetime.datetime(2021, 8, 3, 9, 46, 52,
                                                      596000),
                                'duration': 2.44}},
                        'stats': {
                            'min': 0.0,
                            'max': 5.59,
                            'stdev': 0.2,
                            'avg': 0.02,
                            'samples': 1389,
                            'incomplete': 2}
                        }
                    }
        group_key = "neutron-agent-checks"
        section_key = "neutron-ovs-agent"
        c = agent_checks.NeutronAgentEventChecks(group_key)
        c()
        self.assertEqual(c.output.get(section_key), expected)

    @mock.patch.object(agent_checks.checks, "add_known_bug")
    def test_get_agents_bugs(self, mock_add_known_bug):
        bugs = []

        def fake_add_bug(*args, **kwargs):
            bugs.append((args, kwargs))

        mock_add_known_bug.side_effect = fake_add_bug
        c = agent_checks.NeutronAgentBugChecks("neutron")
        c.register_search_terms()
        results = c.process_results(c.searchobj.search())
        self.assertEqual(results, None)
        calls = [mock.call("1896506",
                           ('identified bug that critically impacts '
                            'keepalived')),
                 mock.call("1929832",
                           ('identified bug impacting deletion of HA '
                            'routers'))]
        mock_add_known_bug.assert_has_calls(calls)
        self.assertEqual(len(bugs), 4)

    def test_get_router_event_stats(self):
        updates = {0: {'start':
                       datetime.datetime(2021, 8, 3, 9, 46, 44, 593000),
                       'end':
                       datetime.datetime(2021, 8, 3, 9, 47, 0, 692000)},
                   1: {'start':
                       datetime.datetime(2021, 8, 2, 21, 53, 58, 516000),
                       'end':
                       datetime.datetime(2021, 8, 2, 21, 54, 10, 683000)},
                   2: {'start':
                       datetime.datetime(2021, 8, 2, 21, 51, 0, 306000),
                       'end':
                       datetime.datetime(2021, 8, 2, 21, 51, 16, 760000)},
                   3: {'start':
                       datetime.datetime(2021, 8, 2, 21, 50, 36, 610000),
                       'end':
                       datetime.datetime(2021, 8, 2, 21, 51, 0, 305000)},
                   4: {'start':
                       datetime.datetime(2021, 8, 2, 21, 47, 53, 325000),
                       'end':
                       datetime.datetime(2021, 8, 2, 21, 48, 18, 406000)}}
        spawn_start = datetime.datetime(2021, 8, 3, 9, 46, 48, 66000)
        spawn_end = datetime.datetime(2021, 8, 3, 9, 47, 7, 617000)
        expected = {'router-updates': {
                        'top': {
                            '0339c98d-13d9-4fb1-ab57-3874a3e56c3e': {
                                'start': updates[0]["start"],
                                'end': updates[0]["end"],
                                'duration': 16.1,
                                'router':
                                    '1e086be2-93c2-4740-921d-3e3237f23959'
                                },
                            '93350e2d-c717-44fd-a10f-cb6019cce18b': {
                                'start': updates[1]["start"],
                                'end': updates[1]["end"],
                                'duration': 12.17,
                                'router':
                                    '1e086be2-93c2-4740-921d-3e3237f23959'},
                            'caa3629f-e401-43d3-a2bf-aa3e6a3bfb6a': {
                                'start': updates[2]["start"],
                                'end': updates[2]["end"],
                                'duration': 16.45,
                                'router':
                                    '1e086be2-93c2-4740-921d-3e3237f23959'},
                            '2e401a45-c471-4472-8425-86bdc6ff27b3': {
                                'start': updates[3]["start"],
                                'end': updates[3]["end"],
                                'duration': 23.7,
                                'router':
                                    '1e086be2-93c2-4740-921d-3e3237f23959'},
                            'd30df808-c11e-401f-824d-b6f313658455': {
                                'start': updates[4]["start"],
                                'end': updates[4]["end"],
                                'duration': 25.08,
                                'router':
                                    '1e086be2-93c2-4740-921d-3e3237f23959'}
                            },
                        'stats': {
                            'min': 6.97,
                            'max': 25.08,
                            'stdev': 5.88,
                            'avg': 15.43,
                            'samples': 8}
                        },
                    'router-spawn-events': {
                        'top': {
                            '1e086be2-93c2-4740-921d-3e3237f23959': {
                                'start': spawn_start,
                                'end': spawn_end,
                                'duration': 19.55}},
                        'stats': {
                            'min': 19.55,
                            'max': 19.55,
                            'stdev': 0.0,
                            'avg': 19.55,
                            'samples': 1}
                        }
                    }
        group_key = "neutron-agent-checks"
        section_key = "neutron-l3-agent"
        c = agent_checks.NeutronAgentEventChecks(group_key)
        c()
        self.assertEqual(c.output.get(section_key), expected)

    @mock.patch.object(agent_checks, "NeutronAgentEventChecks")
    @mock.patch.object(agent_checks, "NeutronAgentBugChecks")
    def test_run_agent_checks(self, mock_agent_bug_checks,
                              mock_agent_event_checks):
        agent_checks.AgentChecks()()
        self.assertTrue(mock_agent_bug_checks.called)
        self.assertTrue(mock_agent_event_checks.called)

    def test_run_octavia_checks(self):
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
        group_key = "octavia-checks"
        for section_key in ["octavia-worker", "octavia-health-manager"]:
            c = agent_checks.OctaviaAgentEventChecks(group_key)
            c()
            self.assertEqual(c.output["octavia"].get(section_key),
                             expected.get(section_key))


class TestOpenstackPluginPartAgentExceptions(TestOpenstackBase):

    def test_get_agent_exceptions(self):
        neutron_expected = {
            'neutron-l3-agent': {
                'neutron_lib.exceptions.ProcessExecutionError': {
                    '2021-05-18': 1,
                    '2021-05-26': 1},
                'MessagingTimeout': {
                    '2021-08-02': 6,
                    '2021-08-03': 32},
                },
            'neutron-openvswitch-agent': {
                'RuntimeError': {
                    '2021-03-29': 3},
                'OVS is dead': {
                    '2021-03-29': 1},
                'MessagingTimeout': {
                    '2021-03-04': 2,
                    '2021-08-02': 6,
                    '2021-08-03': 32},
                'AMQP server on 10.10.123.22:5672 is unreachable': {
                    '2021-03-04': 3},
                }
        }
        nova_expected = {
            'nova-compute': {
                'MessagingTimeout': {'2021-08-16': 35}
            },
            'nova-api-wsgi': {
                'OSError: Server unexpectedly closed connection': {
                    '2021-03-15': 1},
                'AMQP server on 10.5.1.98:5672 is unreachable': {
                    '2021-03-15': 1},
                'amqp.exceptions.ConnectionForced': {
                    '2021-03-15': 1},
            }
        }
        barbican_expected = {'barbican-api':
                             {'UnicodeDecodeError': {'2021-05-04': 1}}}
        expected = {"nova": nova_expected, "neutron": neutron_expected,
                    "barbican": barbican_expected}
        inst = agent_exceptions.AgentExceptionChecks()
        inst()
        self.assertEqual(inst.output['agent-exceptions'], expected)


class TestOpenstackPluginPartNeutronL3HA_checks(TestOpenstackBase):

    def test_run_checks(self):
        expected = {'agent': {
                     'master': ['1e086be2-93c2-4740-921d-3e3237f23959']},
                    'keepalived': {
                     'transitions': {
                      '1e086be2-93c2-4740-921d-3e3237f23959': {
                          '2021-08-02': 7,
                          '2021-08-03': 2
                       }
                      }
                     }
                    }
        inst = neutron_l3ha.NeutronL3HAChecks()
        inst.get_neutron_ha_info()
        inst.get_vrrp_transitions()
        inst.check_vrrp_transitions()
        self.assertEqual(inst.output["neutron-l3ha"], expected)

    @mock.patch.object(neutron_l3ha.issue_utils, "add_issue")
    @mock.patch.object(neutron_l3ha, "VRRP_TRANSITION_WARN_THRESHOLD", 1)
    def test_run_checks_w_issue(self, mock_add_issue):
        os.environ["USE_ALL_LOGS"] = "False"
        expected = {'agent': {
                     'master': ['1e086be2-93c2-4740-921d-3e3237f23959']},
                    'keepalived': {
                     'transitions': {
                      '1e086be2-93c2-4740-921d-3e3237f23959': {
                       '2021-08-03': 2
                       }
                      }
                     }
                    }
        inst = neutron_l3ha.NeutronL3HAChecks()
        inst.get_neutron_ha_info()
        inst.get_vrrp_transitions()
        inst.check_vrrp_transitions()
        self.assertEqual(inst.output["neutron-l3ha"], expected)
        self.assertTrue(mock_add_issue.called)


class TestOpenstackPluginPartServiceChecks(TestOpenstackBase):

    @mock.patch.object(service_checks, 'CLIHelper')
    @mock.patch.object(service_checks.issue_utils, "add_issue")
    def test_run_service_checks(self, mock_add_issue, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.journalctl.return_value = \
            JOURNALCTL_OVS_CLEANUP_GOOD.splitlines(keepends=True)
        inst = service_checks.NeutronServiceChecks()
        inst()
        self.assertFalse(mock_add_issue.called)

    @mock.patch.object(service_checks, 'CLIHelper')
    @mock.patch.object(service_checks.issue_utils, "add_issue")
    def test_run_service_checks_w_issue(self, mock_add_issue, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.journalctl.return_value = \
            JOURNALCTL_OVS_CLEANUP_BAD.splitlines(keepends=True)
        inst = service_checks.NeutronServiceChecks()
        inst()
        self.assertTrue(mock_add_issue.called)


class TestOpenstackPluginPartConfigChecks(TestOpenstackBase):

    @mock.patch.object(service_checks.issue_utils, "add_issue")
    def test_config_checks_has_issue(self, mock_add_issue):
        inst = config_checks.OpenstackConfigChecks()
        with mock.patch.object(inst.apt_check,
                               'is_installed') as mock_installed:
            mock_installed.return_value = True
            inst()
            self.assertTrue(mock_add_issue.called)

    @mock.patch.object(service_checks.issue_utils, "add_issue")
    def test_config_checks_no_issue(self, mock_add_issue):
        inst = config_checks.OpenstackConfigChecks()
        with mock.patch.object(inst.apt_check,
                               'is_installed') as mock_installed:
            mock_installed.return_value = False
            inst()
            self.assertFalse(mock_add_issue.called)
