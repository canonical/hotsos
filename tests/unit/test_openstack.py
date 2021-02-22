import os
import mock
import tempfile

from importlib.util import spec_from_loader, module_from_spec
from importlib.machinery import SourceFileLoader

import utils


# need this for non-standard import
specs = {}
for plugin in ["01openstack", "02vm_info", "03nova_external_events",
               "04package_versions", "05network", "06_service_features",
               "07_cpu_pinning_check"]:
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

ost_06_service_features = module_from_spec(specs["06_service_features"])
specs["06_service_features"].loader.exec_module(ost_06_service_features)

ost_07_cpu_pinning_check = module_from_spec(specs["07_cpu_pinning_check"])
specs["07_cpu_pinning_check"].loader.exec_module(ost_07_cpu_pinning_check)


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


class TestOpenstackPlugin06_service_features(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()


class TestOpenstackPlugin07_cpu_pinning_check(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()
