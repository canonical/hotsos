import os

import datetime
import mock
import tempfile

from importlib.util import spec_from_loader, module_from_spec
from importlib.machinery import SourceFileLoader

import utils


# need this for non-standard import
specs = {}
for plugin in ["01openstack", "02vm_info", "03nova_external_events",
               "04package_versions", "05network", "06service_features",
               "07cpu_pinning_check", "08neutron_openvswitch",
               "09agent_errors", "10neutron_l3agent"]:
    loader = SourceFileLoader("ost_{}".format(plugin),
                              "plugins/openstack/{}".format(plugin))
    specs[plugin] = spec_from_loader("ost_{}".format(plugin), loader)

ost_01openstack = module_from_spec(specs["01openstack"])
specs["01openstack"].loader.exec_module(ost_01openstack)

ost_02vm_info = module_from_spec(specs["02vm_info"])
specs["02vm_info"].loader.exec_module(ost_02vm_info)

ost_03nova_external_events = module_from_spec(specs["03nova_external_events"])
specs["03nova_external_events"].loader.exec_module(
                                              ost_03nova_external_events)

ost_04package_versions = module_from_spec(specs["04package_versions"])
specs["04package_versions"].loader.exec_module(ost_04package_versions)

ost_05network = module_from_spec(specs["05network"])
specs["05network"].loader.exec_module(ost_05network)

ost_06service_features = module_from_spec(specs["06service_features"])
specs["06service_features"].loader.exec_module(ost_06service_features)

ost_07cpu_pinning_check = module_from_spec(specs["07cpu_pinning_check"])
specs["07cpu_pinning_check"].loader.exec_module(ost_07cpu_pinning_check)

ost_08neutron_openvswitch = module_from_spec(specs["08neutron_openvswitch"])
specs["08neutron_openvswitch"].loader.exec_module(ost_08neutron_openvswitch)

ost_09agent_errors = module_from_spec(specs["09agent_errors"])
specs["09agent_errors"].loader.exec_module(ost_09agent_errors)

ost_10neutron_l3agent = module_from_spec(specs["10neutron_l3agent"])
specs["10neutron_l3agent"].loader.exec_module(ost_10neutron_l3agent)


APT_UCA = """
# Ubuntu Cloud Archive
deb http://ubuntu-cloud.archive.canonical.com/ubuntu bionic-updates/{} main
"""

SVC_CONF = """
debug = True
"""

with open(os.path.join(os.environ['DATA_ROOT'],
                       "sos_commands/networking/ip_-s_-d_link")) as fd:
    IP_LINK_SHOW = fd.readlines()


def fake_ip_link_show_w_errors_drops():
    lines = ''.join(IP_LINK_SHOW).format(10000000, 100000000)
    return [line + '\n' for line in lines.split('\n')]


def fake_ip_link_show_no_errors_drops():
    lines = ''.join(IP_LINK_SHOW).format(0, 0)
    return [line + '\n' for line in lines.split('\n')]


class TestOpenstackPlugin01openstack(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(ost_01openstack, "OPENSTACK_INFO", {})
    def test_get_service_info(self):
        result = {'services': ['haproxy (1)',
                               'neutron-ovn-metadata-agent (3)',
                               'nova-api-metadata (5)',
                               'nova-compute (1)',
                               'qemu-system-x86_64 (1)']}
        ost_01openstack.get_service_info()
        self.assertEqual(ost_01openstack.OPENSTACK_INFO, result)

    @mock.patch.object(ost_01openstack, "OPENSTACK_INFO", {})
    def test_get_release_info(self):
        with tempfile.TemporaryDirectory() as dtmp:
            for rel in ["stein", "ussuri", "train"]:
                with open(os.path.join(dtmp,
                                       "cloud-archive-{}.list".format(rel)),
                          'w') as fd:
                    fd.write(APT_UCA.format(rel))

            with mock.patch.object(ost_01openstack, "APT_SOURCE_PATH", dtmp):
                ost_01openstack.get_release_info()
                self.assertEqual(ost_01openstack.OPENSTACK_INFO,
                                 {"release": "ussuri"})

    @mock.patch.object(ost_01openstack, "OPENSTACK_INFO", {})
    def test_get_debug_log_info(self):
        result = {'debug-logging-enabled': {'neutron': True, 'nova': True}}
        with tempfile.TemporaryDirectory() as dtmp:
            for svc in ["nova", "neutron"]:
                conf_path = "etc/{svc}/{svc}.conf".format(svc=svc)
                os.makedirs(os.path.dirname(os.path.join(dtmp, conf_path)))
                with open(os.path.join(dtmp, conf_path), 'w') as fd:
                    fd.write(SVC_CONF)

            with mock.patch.object(ost_01openstack.constants,
                                   "DATA_ROOT", dtmp):
                ost_01openstack.get_debug_log_info()
                self.assertEqual(ost_01openstack.OPENSTACK_INFO, result)


class TestOpenstackPlugin02vm_info(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(ost_02vm_info, "VM_INFO", [])
    def test_get_vm_info(self):
        ost_02vm_info.get_vm_info()
        self.assertEquals(ost_02vm_info.VM_INFO,
                          ["09461f0b-297b-4ef5-9053-dd369c86b96b"])


class TestOpenstackPlugin03nova_external_events(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(ost_03nova_external_events, "EXT_EVENT_INFO", {})
    def test_get_events(self):
        data_root = ost_03nova_external_events.constants.DATA_ROOT
        data_source = os.path.join(data_root, "var/log/nova")
        ost_03nova_external_events.get_events("network-vif-plugged",
                                              data_source)
        events = {'network-vif-plugged':
                  {'succeeded': ['d2666e01-73c8-4a97-9c22-0c175659e6db'],
                   'failed': ['5b367a10-9e6a-4eb9-9c7d-891dab7e87fa']}}
        self.assertEquals(ost_03nova_external_events.EXT_EVENT_INFO, events)


class TestOpenstackPlugin04package_versions(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()


class TestOpenstackPlugin05network(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(ost_05network.helpers, 'get_ip_link_show',
                       fake_ip_link_show_w_errors_drops)
    def test_get_port_stat_by_name(self):
        stats = ost_05network.get_port_stats(name="bond1")
        self.assertEqual(stats, {'dropped': '100000000 (8%)'})

    @mock.patch.object(ost_05network.helpers, 'get_ip_link_show',
                       fake_ip_link_show_no_errors_drops)
    def test_get_port_stat_by_name_no_problems(self):
        stats = ost_05network.get_port_stats(name="bond1")
        self.assertEqual(stats, {})

    @mock.patch.object(ost_05network.helpers, 'get_ip_link_show',
                       fake_ip_link_show_w_errors_drops)
    def test_get_port_stat_by_mac(self):
        stats = ost_05network.get_port_stats(mac="ac:1f:6b:9e:d8:44")
        self.assertEqual(stats, {'errors': '10000000 (5%)'})

    def test_find_interface_name_by_ip_address(self):
        addr = "10.10.101.33"
        name = ost_05network.find_interface_name_by_ip_address(addr)
        self.assertEqual(name, "br-bond1")

    @mock.patch.object(ost_05network, "NETWORK_INFO", {})
    def test_get_ns_info(self):
        ns_info = {'namespaces': {'qdhcp': 35, 'qrouter': 35, 'fip': 1}}
        ost_05network.get_ns_info()
        self.assertEqual(ns_info, ost_05network.NETWORK_INFO)

    @mock.patch.object(ost_05network.helpers, "get_ip_netns", lambda: [])
    def test_get_ns_info_none(self):
        ns_info = ost_05network.get_ns_info()
        self.assertEqual(ns_info, None)


class TestOpenstackPlugin06service_features(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(ost_06service_features, "SERVICE_FEATURES", {})
    def test_get_service_features(self):
        ost_06service_features.get_service_features()
        expected = {'neutron': {'neutron': {'availability_zone': 'AZ1'}}}
        self.assertEqual(ost_06service_features.SERVICE_FEATURES, expected)


class TestOpenstackPlugin07cpu_pinning_check(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()


class TestOpenstackPlugin08neutron_openvswitch(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(ost_08neutron_openvswitch, "NEUTRON_OVS_AGENT_INFO", {})
    def test_get_rpc_loop_too_long(self):
        end = datetime.datetime(2021, 3, 2, 14, 26, 55, 682000)
        start = datetime.datetime(2021, 3, 2, 14, 26, 29, 780000)
        expected = {'rpc-loop': {"top": {1438: {'duration': 25.9,
                                                'end': end,
                                                'start': start}},
                                 "stats": {"min": 25.9,
                                           "max": 25.9,
                                           "stdev": 0.0,
                                           "avg": 25.9,
                                           "samples": 1}}}
        ost_08neutron_openvswitch.get_rpc_loop_too_long()
        self.assertEqual(ost_08neutron_openvswitch.NEUTRON_OVS_AGENT_INFO,
                         expected)


class TestOpenstackPlugin09agent_errors(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(ost_09agent_errors, "add_known_bug")
    @mock.patch.object(ost_09agent_errors, "AGENT_LOG_ISSUES", {})
    def test_get_agents_issues(self, mock_add_known_bug):
        neutron_expected = {'neutron-openvswitch-agent':
                            {'MessagingTimeout': {'2021-03-04': 2},
                             'AMQP server on 10.10.123.22:5672 is unreachable':
                             {'2021-03-04': 3},
                             'OVS is dead': {'2021-03-29': 1},
                             'RuntimeError': {'2021-03-29': 3},
                             }}
        nova_expected = {'nova-api-wsgi':
                         {'OSError: Server unexpectedly closed connection':
                          {'2021-03-15': 1},
                          'AMQP server on 10.5.1.98:5672 is unreachable':
                          {'2021-03-15': 1},
                          'amqp.exceptions.ConnectionForced':
                          {'2021-03-15': 1}},
                         'nova-compute':
                         {'DBConnectionError': {'2021-03-08': 2}}}
        ost_09agent_errors.get_agents_issues()
        self.assertEqual(ost_09agent_errors.AGENT_LOG_ISSUES,
                         {"neutron": neutron_expected, "nova": nova_expected})
        mock_add_known_bug.assert_has_calls([mock.call("1896506")])


class TestOpenstackPlugin10neutron_l3agent(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(ost_10neutron_l3agent, "NEUTRON_L3AGENT_INFO", {})
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
                                                    {'duration': 36.091,
                                                     'end': spawn_end,
                                                     'start': spawn_start}}},
                    'router-updates': {'stats': {'avg': 28.14,
                                                 'max': 42.22,
                                                 'min': 14.07,
                                                 'samples': 2,
                                                 'stdev': 14.08},
                                       'top': {router:
                                               {'duration': 42.222,
                                                'end': update_end,
                                                'start': update_start}}}}

        ost_10neutron_l3agent.get_router_event_stats()
        self.assertEqual(ost_10neutron_l3agent.NEUTRON_L3AGENT_INFO,
                         expected)
