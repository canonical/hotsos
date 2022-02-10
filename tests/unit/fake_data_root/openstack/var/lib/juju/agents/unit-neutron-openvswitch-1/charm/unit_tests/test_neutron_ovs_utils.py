# Copyright 2016 Canonical Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import hashlib
import subprocess

from unittest.mock import MagicMock, patch, call, ANY
from collections import OrderedDict
import charmhelpers.contrib.openstack.templating as templating

from charmhelpers.contrib.openstack.context import EntityMac

templating.OSConfigRenderer = MagicMock()

import neutron_ovs_utils as nutils
import neutron_ovs_context

from test_utils import (
    CharmTestCase,
)
import charmhelpers
import charmhelpers.core.hookenv as hookenv


TO_PATCH = [
    'add_bridge',
    'add_bridge_port',
    'add_bridge_bond',
    'add_ovsbridge_linuxbridge',
    'is_linuxbridge_interface',
    'add_source',
    'apt_install',
    'apt_update',
    'config',
    'lsb_release',
    'os_release',
    'filter_installed_packages',
    'filter_missing_packages',
    'lsb_release',
    'neutron_plugin_attribute',
    'full_restart',
    'service_restart',
    'service_running',
    'ExternalPortContext',
    'determine_dkms_package',
    'headers_package',
    'status_set',
    'use_dpdk',
    'os_application_version_set',
    'enable_ipfix',
    'disable_ipfix',
    'ovs_has_late_dpdk_init',
    'ovs_vhostuser_client',
    'parse_data_port_mappings',
    'user_exists',
    'group_exists',
    'init_is_systemd',
    'modprobe',
    'is_container',
    'is_unit_paused_set',
    'deferrable_svc_restart',
    'log',
]

head_pkg = 'linux-headers-3.15.0-5-generic'


def _mock_npa(plugin, attr, net_manager=None):
    plugins = {
        'ovs': {
            'config': '/etc/neutron/plugins/ml2/ml2_conf.ini',
            'driver': 'neutron.plugins.ml2.plugin.Ml2Plugin',
            'contexts': [],
            'services': ['neutron-plugin-openvswitch-agent'],
            'packages': [[head_pkg], ['neutron-plugin-openvswitch-agent']],
            'server_packages': ['neutron-server',
                                'neutron-plugin-ml2'],
            'server_services': ['neutron-server']
        },
    }
    return plugins[plugin][attr]


class DummyContext():

    def __init__(self, return_value):
        self.return_value = return_value

    def __call__(self):
        return self.return_value


class TestNeutronOVSUtils(CharmTestCase):

    def setUp(self):
        super(TestNeutronOVSUtils, self).setUp(nutils, TO_PATCH)
        self.neutron_plugin_attribute.side_effect = _mock_npa
        self.config.side_effect = self.test_config.get
        self.use_dpdk.return_value = False
        self.ovs_has_late_dpdk_init.return_value = False
        self.ovs_vhostuser_client.return_value = False

    def tearDown(self):
        # Reset cached cache
        hookenv.cache = {}

    @patch.object(nutils, 'determine_packages')
    def test_install_packages(self, _determine_packages):
        self.os_release.return_value = 'mitaka'
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'xenial'}
        _determine_packages.return_value = 'randompkg'
        nutils.install_packages()
        self.apt_update.assert_called_with()
        self.apt_install.assert_called_with(self.filter_installed_packages(),
                                            fatal=True)
        self.modprobe.assert_not_called()

    @patch.object(nutils, 'determine_packages')
    def test_install_packages_container(self, _determine_packages):
        self.os_release.return_value = 'mitaka'
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'xenial'}
        self.is_container.return_value = True
        _determine_packages.return_value = 'randompkg'
        nutils.install_packages()
        self.apt_update.assert_called_with()
        self.apt_install.assert_called_with(self.filter_installed_packages(),
                                            fatal=True)
        self.modprobe.assert_not_called()

    @patch.object(nutils, 'determine_packages')
    def test_install_packages_ovs_firewall(self, _determine_packages):
        self.os_release.return_value = 'mitaka'
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'xenial'}
        _determine_packages.return_value = 'randompkg'
        self.is_container.return_value = False
        self.test_config.set('firewall-driver', 'openvswitch')
        nutils.install_packages()
        self.apt_update.assert_called_with()
        self.apt_install.assert_called_with(self.filter_installed_packages(),
                                            fatal=True)
        self.modprobe.assert_has_calls([call('nf_conntrack_ipv4', True),
                                        call('nf_conntrack_ipv6', True)])

    @patch.object(nutils, 'determine_packages')
    def test_install_packages_ovs_fw_newer_kernel(self, _determine_packages):
        self.os_release.return_value = 'mitaka'
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'xenial'}
        _determine_packages.return_value = 'randompkg'
        self.is_container.return_value = False
        self.test_config.set('firewall-driver', 'openvswitch')
        self.modprobe.side_effect = [subprocess.CalledProcessError(0, ""),
                                     None]
        nutils.install_packages()
        self.apt_update.assert_called_with()
        self.apt_install.assert_called_with(self.filter_installed_packages(),
                                            fatal=True)
        self.modprobe.assert_has_calls([call('nf_conntrack_ipv4', True),
                                        call('nf_conntrack', True)])

    @patch.object(nutils, 'determine_packages')
    def test_install_packages_dkms_needed(self, _determine_packages):
        self.os_release.return_value = 'mitaka'
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'xenial'}
        _determine_packages.return_value = 'randompkg'
        self.determine_dkms_package.return_value = \
            ['openvswitch-datapath-dkms']
        self.headers_package.return_value = 'linux-headers-foobar'
        nutils.install_packages()
        self.apt_update.assert_called_with()
        self.apt_install.assert_has_calls([
            call(['linux-headers-foobar',
                  'openvswitch-datapath-dkms'], fatal=True),
            call(self.filter_installed_packages(), fatal=True),
        ])

    @patch.object(nutils, 'use_hw_offload')
    @patch.object(nutils, 'enable_hw_offload')
    @patch.object(nutils, 'determine_packages')
    def test_install_packages_hwoffload(self, _determine_packages,
                                        _enable_hw_offload,
                                        _use_hw_offload):
        self.os_release.return_value = 'stein'
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'bionic'}
        _determine_packages.return_value = 'randompkg'
        _use_hw_offload.return_value = True
        self.determine_dkms_package.return_value = \
            ['openvswitch-datapath-dkms']
        self.headers_package.return_value = 'linux-headers-foobar'
        nutils.install_packages()
        self.apt_update.assert_called_with()
        self.apt_install.assert_has_calls([
            call(['linux-headers-foobar',
                  'openvswitch-datapath-dkms'], fatal=True),
            call(self.filter_installed_packages(), fatal=True),
        ])
        _enable_hw_offload.assert_called_once_with()

    @patch.object(nutils, 'use_l3ha')
    @patch.object(nutils, 'use_dvr')
    @patch.object(charmhelpers.contrib.openstack.neutron, 'os_release')
    @patch.object(charmhelpers.contrib.openstack.neutron, 'headers_package')
    def test_determine_packages(self, _head_pkgs, _os_rel,
                                _use_dvr, _use_l3ha):
        self.test_config.set('enable-local-dhcp-and-metadata', False)
        _use_dvr.return_value = False
        _use_l3ha.return_value = False
        _os_rel.return_value = 'mitaka'
        self.os_release.return_value = 'mitaka'
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'xenial'}
        _head_pkgs.return_value = head_pkg
        pkg_list = nutils.determine_packages()
        expect = [
            head_pkg,
            'neutron-openvswitch-agent',
        ]
        self.assertEqual(pkg_list, expect)

    @patch.object(nutils, 'use_l3ha')
    @patch.object(nutils, 'use_dvr')
    @patch.object(charmhelpers.contrib.openstack.neutron, 'os_release')
    @patch.object(charmhelpers.contrib.openstack.neutron, 'headers_package')
    def test_determine_packages_metadata(self, _head_pkgs, _os_rel,
                                         _use_dvr, _use_l3ha):
        self.is_container.return_value = False
        self.test_config.set('enable-local-dhcp-and-metadata', True)
        _use_dvr.return_value = False
        _use_l3ha.return_value = False
        _os_rel.return_value = 'mitaka'
        self.os_release.return_value = 'mitaka'
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'xenial'}
        _head_pkgs.return_value = head_pkg
        pkg_list = nutils.determine_packages()
        expect = [
            head_pkg,
            'neutron-dhcp-agent',
            'neutron-metadata-agent',
            'haproxy',
            'neutron-openvswitch-agent',
        ]
        self.assertEqual(pkg_list, expect)

    @patch.object(nutils, 'use_l3ha')
    @patch.object(nutils, 'use_dvr')
    @patch.object(charmhelpers.contrib.openstack.neutron, 'os_release')
    @patch.object(charmhelpers.contrib.openstack.neutron, 'headers_package')
    def test_determine_packages_dvr(self, _head_pkgs, _os_rel, _use_dvr,
                                    _use_l3ha):
        _use_dvr.return_value = True
        _use_l3ha.return_value = False
        _os_rel.return_value = 'mitaka'
        self.os_release.return_value = 'mitaka'
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'xenial'}
        _head_pkgs.return_value = head_pkg
        pkg_list = nutils.determine_packages()
        expect = [
            head_pkg,
            'neutron-l3-agent',
            'libnetfilter-log1',
            'neutron-openvswitch-agent',
        ]
        self.assertEqual(pkg_list, expect)

    @patch.object(nutils, 'use_l3ha')
    @patch.object(nutils, 'use_dvr')
    @patch.object(charmhelpers.contrib.openstack.neutron, 'os_release')
    @patch.object(charmhelpers.contrib.openstack.neutron, 'headers_package')
    def test_determine_packages_dvr_rocky(self, _head_pkgs, _os_rel, _use_dvr,
                                          _use_l3ha):
        _use_dvr.return_value = True
        _use_l3ha.return_value = False
        _os_rel.return_value = 'rocky'
        self.os_release.return_value = 'rocky'
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'bionic'}
        _head_pkgs.return_value = head_pkg
        pkg_list = nutils.determine_packages()
        expect = [
            head_pkg,
            'neutron-l3-agent',
            'libnetfilter-log1',
            'neutron-openvswitch-agent',
            'python3-neutron',
            'python3-zmq',
            'python3-neutron-fwaas',
        ]
        self.assertEqual(pkg_list, expect)

    @patch.object(nutils, 'use_l3ha')
    @patch.object(nutils, 'use_dvr')
    @patch.object(charmhelpers.contrib.openstack.neutron, 'os_release')
    @patch.object(charmhelpers.contrib.openstack.neutron, 'headers_package')
    def test_determine_packages_newton_dvr_l3ha(self, _head_pkgs, _os_rel,
                                                _use_dvr, _use_l3ha):
        self.test_config.set('enable-local-dhcp-and-metadata', False)
        _use_dvr.return_value = True
        _use_l3ha.return_value = True
        _os_rel.return_value = 'newton'
        self.os_release.return_value = 'newton'
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'xenial'}
        _head_pkgs.return_value = head_pkg
        pkg_list = nutils.determine_packages()
        expect = [
            head_pkg,
            'neutron-l3-agent',
            'libnetfilter-log1',
            'keepalived',
            'neutron-openvswitch-agent',
        ]
        self.assertEqual(pkg_list, expect)

    @patch.object(nutils, 'use_l3ha')
    @patch.object(nutils, 'use_dvr')
    @patch.object(charmhelpers.contrib.openstack.neutron, 'os_release')
    @patch.object(charmhelpers.contrib.openstack.neutron, 'headers_package')
    def test_determine_packages_newton_dvr_no_l3ha(self, _head_pkgs, _os_rel,
                                                   _use_dvr, _use_l3ha):
        self.test_config.set('enable-local-dhcp-and-metadata', False)
        _use_dvr.return_value = True
        _use_l3ha.return_value = False
        _os_rel.return_value = 'newton'
        self.os_release.return_value = 'newton'
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'xenial'}
        _head_pkgs.return_value = head_pkg
        pkg_list = nutils.determine_packages()
        expect = [
            head_pkg,
            'neutron-l3-agent',
            'libnetfilter-log1',
            'neutron-openvswitch-agent',
        ]
        self.assertEqual(pkg_list, expect)

    @patch.object(nutils, 'use_l3ha')
    @patch.object(nutils, 'use_dvr')
    @patch.object(charmhelpers.contrib.openstack.neutron, 'os_release')
    @patch.object(charmhelpers.contrib.openstack.neutron, 'headers_package')
    def test_determine_packages_mitaka_dvr_l3ha(self, _head_pkgs, _os_rel,
                                                _use_dvr, _use_l3ha):
        self.test_config.set('enable-local-dhcp-and-metadata', False)
        _use_dvr.return_value = True
        _use_l3ha.return_value = True
        _os_rel.return_value = 'mitaka'
        self.os_release.return_value = 'mitaka'
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'xenial'}
        _head_pkgs.return_value = head_pkg
        pkg_list = nutils.determine_packages()
        expect = [
            head_pkg,
            'neutron-l3-agent',
            'libnetfilter-log1',
            'neutron-openvswitch-agent',
        ]
        self.assertEqual(pkg_list, expect)

    @patch.object(nutils, 'use_l3ha')
    @patch.object(nutils, 'use_dvr')
    @patch.object(charmhelpers.contrib.openstack.neutron, 'os_release')
    @patch.object(charmhelpers.contrib.openstack.neutron, 'headers_package')
    def test_determine_pkgs_sriov(self, _head_pkgs, _os_rel,
                                  _use_dvr, _use_l3ha):
        self.test_config.set('enable-local-dhcp-and-metadata', False)
        self.test_config.set('enable-sriov', True)
        _use_dvr.return_value = False
        _use_l3ha.return_value = False
        _os_rel.return_value = 'mitaka'
        self.os_release.return_value = 'mitaka'
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'xenial'}
        _head_pkgs.return_value = head_pkg
        pkg_list = nutils.determine_packages()
        expect = [
            head_pkg,
            'neutron-openvswitch-agent',
            'neutron-sriov-agent',
        ]
        self.assertEqual(pkg_list, expect)

    @patch.object(nutils, 'use_hw_offload')
    @patch.object(nutils, 'use_l3ha')
    @patch.object(nutils, 'use_dvr')
    @patch.object(charmhelpers.contrib.openstack.neutron, 'os_release')
    @patch.object(charmhelpers.contrib.openstack.neutron, 'headers_package')
    def test_determine_pkgs_hardware_offload(self, _head_pkgs, _os_rel,
                                             _use_dvr, _use_l3ha,
                                             _use_hw_offload):
        self.test_config.set('enable-local-dhcp-and-metadata', False)
        self.test_config.set('enable-hardware-offload', True)
        _use_hw_offload.return_value = True
        _use_dvr.return_value = False
        _use_l3ha.return_value = False
        _os_rel.return_value = 'stein'
        self.os_release.return_value = 'stein'
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'bionic'}
        _head_pkgs.return_value = head_pkg
        pkg_list = nutils.determine_packages()
        expect = [
            head_pkg,
            'neutron-openvswitch-agent',
            'mlnx-switchdev-mode',
            'python3-neutron',
            'python3-zmq',
        ]
        self.assertEqual(pkg_list, expect)

    @patch.object(nutils, 'use_dvr')
    def test_register_configs(self, _use_dvr):
        class _mock_OSConfigRenderer():
            def __init__(self, templates_dir=None, openstack_release=None):
                self.configs = []
                self.ctxts = []

            def register(self, config, ctxt):
                self.configs.append(config)
                self.ctxts.append(ctxt)

        _use_dvr.return_value = False
        self.os_release.return_value = 'icehouse'
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'precise'}
        templating.OSConfigRenderer.side_effect = _mock_OSConfigRenderer
        _regconfs = nutils.register_configs()
        confs = ['/etc/neutron/neutron.conf',
                 '/etc/neutron/plugins/ml2/ml2_conf.ini',
                 '/etc/default/openvswitch-switch',
                 '/etc/init/os-charm-phy-nic-mtu.conf']
        self.assertEqual(_regconfs.configs, confs)

    @patch.object(nutils, 'use_dvr')
    def test_register_configs_mitaka(self, _use_dvr):
        class _mock_OSConfigRenderer():
            def __init__(self, templates_dir=None, openstack_release=None):
                self.configs = []
                self.ctxts = []

            def register(self, config, ctxt):
                self.configs.append(config)
                self.ctxts.append(ctxt)

        _use_dvr.return_value = False
        self.os_release.return_value = 'mitaka'
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'trusty'}
        templating.OSConfigRenderer.side_effect = _mock_OSConfigRenderer
        _regconfs = nutils.register_configs()
        confs = ['/etc/neutron/neutron.conf',
                 '/etc/neutron/plugins/ml2/openvswitch_agent.ini',
                 '/etc/default/openvswitch-switch',
                 '/etc/init/os-charm-phy-nic-mtu.conf']
        self.assertEqual(_regconfs.configs, confs)

    @patch.object(nutils, 'use_dvr')
    def test_resource_map(self, _use_dvr):
        _use_dvr.return_value = False
        self.os_release.return_value = 'icehouse'
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'precise'}
        _map = nutils.resource_map()
        svcs = ['neutron-plugin-openvswitch-agent']
        confs = [nutils.NEUTRON_CONF]
        [self.assertIn(q_conf, _map.keys()) for q_conf in confs]
        self.assertEqual(_map[nutils.NEUTRON_CONF]['services'], svcs)

    @patch.object(nutils, 'SRIOVContext_adapter')
    @patch.object(nutils, 'enable_sriov')
    @patch.object(nutils, 'use_dvr')
    def test_resource_map_kilo_sriov(self, _use_dvr, _enable_sriov,
                                     _sriovcontext_adapter):
        _use_dvr.return_value = False
        _enable_sriov.return_value = True
        self.os_release.return_value = 'kilo'
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'trusty'}
        _map = nutils.resource_map()
        svcs = ['neutron-plugin-openvswitch-agent',
                'neutron-plugin-sriov-agent']
        confs = [nutils.NEUTRON_CONF, nutils.NEUTRON_SRIOV_AGENT_CONF]
        [self.assertIn(q_conf, _map.keys()) for q_conf in confs]
        self.assertEqual(_map[nutils.NEUTRON_CONF]['services'], svcs)
        self.assertEqual(_map[nutils.NEUTRON_SRIOV_AGENT_CONF]['services'],
                         ['neutron-plugin-sriov-agent'])

    @patch.object(nutils, 'use_dvr')
    def test_resource_map_mitaka(self, _use_dvr):
        _use_dvr.return_value = False
        self.os_release.return_value = 'mitaka'
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'xenial'}
        _map = nutils.resource_map()
        svcs = ['neutron-openvswitch-agent']
        confs = [nutils.NEUTRON_CONF]
        [self.assertIn(q_conf, _map.keys()) for q_conf in confs]
        self.assertEqual(_map[nutils.NEUTRON_CONF]['services'], svcs)

    @patch.object(nutils, 'SRIOVContext_adapter')
    @patch.object(nutils, 'enable_sriov')
    @patch.object(nutils, 'use_dvr')
    def test_resource_map_mitaka_sriov(self, _use_dvr, _enable_sriov,
                                       _sriovcontext_adapter):
        _use_dvr.return_value = False
        _enable_sriov.return_value = True
        self.os_release.return_value = 'mitaka'
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'xenial'}
        _map = nutils.resource_map()
        svcs = ['neutron-openvswitch-agent',
                'neutron-sriov-agent']
        confs = [nutils.NEUTRON_CONF, nutils.NEUTRON_SRIOV_AGENT_CONF]
        [self.assertIn(q_conf, _map.keys()) for q_conf in confs]
        self.assertEqual(_map[nutils.NEUTRON_CONF]['services'], svcs)
        self.assertEqual(_map[nutils.NEUTRON_SRIOV_AGENT_CONF]['services'],
                         ['neutron-sriov-agent'])

    @patch.object(nutils, 'use_dvr')
    def test_resource_map_dvr(self, _use_dvr):
        _use_dvr.return_value = True
        self.os_release.return_value = 'icehouse'
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'xenial'}
        _map = nutils.resource_map()
        svcs = ['neutron-plugin-openvswitch-agent', 'neutron-metadata-agent',
                'neutron-l3-agent']
        confs = [nutils.NEUTRON_CONF]
        [self.assertIn(q_conf, _map.keys()) for q_conf in confs]
        self.assertEqual(_map[nutils.NEUTRON_CONF]['services'], svcs)

    @patch.object(nutils, 'enable_local_dhcp')
    @patch.object(nutils, 'use_dvr')
    def test_resource_map_dhcp(self, _use_dvr, _enable_local_dhcp):
        _enable_local_dhcp.return_value = True
        _use_dvr.return_value = False
        self.os_release.return_value = 'mitaka'
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'xenial'}
        _map = nutils.resource_map()
        svcs = ['neutron-metadata-agent', 'neutron-dhcp-agent',
                'neutron-openvswitch-agent']
        confs = [nutils.NEUTRON_CONF, nutils.NEUTRON_METADATA_AGENT_CONF,
                 nutils.NEUTRON_DHCP_AGENT_CONF]
        [self.assertIn(q_conf, _map.keys()) for q_conf in confs]
        self.assertEqual(_map[nutils.NEUTRON_CONF]['services'], svcs)

    @patch.object(nutils, 'use_dvr')
    def test_resource_map_mtu_trusty(self, _use_dvr):
        _use_dvr.return_value = False
        self.os_release.return_value = 'mitaka'
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'trusty'}
        _map = nutils.resource_map()
        self.assertTrue(nutils.NEUTRON_CONF in _map.keys())
        self.assertTrue(nutils.PHY_NIC_MTU_CONF in _map.keys())
        self.assertFalse(nutils.EXT_PORT_CONF in _map.keys())
        _use_dvr.return_value = True
        _map = nutils.resource_map()
        self.assertTrue(nutils.EXT_PORT_CONF in _map.keys())

    @patch.object(nutils, 'use_dvr')
    def test_resource_map_mtu_xenial(self, _use_dvr):
        _use_dvr.return_value = False
        self.os_release.return_value = 'mitaka'
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'xenial'}
        _map = nutils.resource_map()
        self.assertTrue(nutils.NEUTRON_CONF in _map.keys())
        self.assertFalse(nutils.PHY_NIC_MTU_CONF in _map.keys())
        self.assertFalse(nutils.EXT_PORT_CONF in _map.keys())
        _use_dvr.return_value = True
        _map = nutils.resource_map()
        self.assertFalse(nutils.EXT_PORT_CONF in _map.keys())

    @patch.object(nutils, 'use_l3ha')
    @patch.object(nutils, 'use_dpdk')
    @patch.object(nutils, 'use_dvr')
    @patch.object(nutils, 'enable_local_dhcp')
    def test_restart_map(self, mock_enable_local_dhcp, mock_use_dvr,
                         mock_use_dpdk, mock_use_l3ha):
        mock_use_dvr.return_value = False
        mock_use_l3ha.return_value = False
        mock_use_dpdk.return_value = False
        mock_enable_local_dhcp.return_value = False
        self.os_release.return_value = "mitaka"
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'xenial'}
        ML2CONF = "/etc/neutron/plugins/ml2/openvswitch_agent.ini"
        _restart_map = nutils.restart_map()
        expect = OrderedDict([
            (nutils.NEUTRON_CONF, ['neutron-openvswitch-agent']),
            (ML2CONF, ['neutron-openvswitch-agent']),
            (nutils.OVS_DEFAULT, ['openvswitch-switch'])
        ])
        for item in _restart_map:
            self.assertTrue(item in _restart_map)
            self.assertTrue(expect[item] == _restart_map[item])
        self.assertEqual(len(_restart_map.keys()), 3)

    @patch('charmhelpers.contrib.openstack.context.list_nics',
           return_value=['eth0'])
    @patch.object(nutils, 'use_dvr')
    @patch('charmhelpers.contrib.network.ovs.charm_name')
    @patch('charmhelpers.contrib.openstack.context.config')
    def test_configure_ovs_ovs_data_port(
            self, mock_config, _charm_name, _use_dvr, _nics):
        _use_dvr.return_value = False
        _charm_name.return_value = "neutron-openvswitch"
        self.is_linuxbridge_interface.return_value = False
        mock_config.side_effect = self.test_config.get
        self.config.side_effect = self.test_config.get
        _nics.return_value = ['eth0']
        self.ExternalPortContext.return_value = \
            DummyContext(return_value=None)
        # Test back-compatibility i.e. port but no bridge (so br-data is
        # assumed)
        self.test_config.set('data-port', 'eth0')
        # Ensure that bridges are marked as managed
        expected_brdata = {
            'datapath-type': 'system',
            'external-ids': {
                'charm-neutron-openvswitch': 'managed'
            }
        }
        expected_ifdata = {
            'external-ids': {
                'charm-neutron-openvswitch': 'br-data'
            }
        }
        nutils.configure_ovs()
        self.add_bridge.assert_has_calls([
            call('br-int', brdata=expected_brdata),
            call('br-ex', brdata=expected_brdata),
            call('br-data', brdata=expected_brdata)
        ])
        self.add_bridge_port.assert_called_with('br-data', 'eth0',
                                                ifdata=expected_ifdata,
                                                portdata=expected_ifdata,
                                                promisc=ANY)
        # Now test with bridge:port format
        self.test_config.set('data-port', 'br-foo:eth0')
        self.add_bridge.reset_mock()
        self.add_bridge_port.reset_mock()
        nutils.configure_ovs()
        self.add_bridge.assert_has_calls([
            call('br-int', brdata=expected_brdata),
            call('br-ex', brdata=expected_brdata),
            call('br-data', brdata=expected_brdata)
        ])
        # Not called since we have a bogus bridge in data-ports
        self.assertFalse(self.add_bridge_port.called)

    @patch('charmhelpers.contrib.openstack.context.list_nics',
           return_value=['eth0', 'br-juju'])
    @patch('charmhelpers.contrib.network.ovs.charm_name')
    @patch.object(nutils, 'use_dvr')
    @patch('charmhelpers.contrib.openstack.context.config')
    def test_configure_ovs_data_port_with_bridge(
            self, mock_config, _use_dvr, _charm_name, _nics):
        _use_dvr.return_value = False
        _charm_name.return_value = "neutron-openvswitch"
        self.is_linuxbridge_interface.return_value = True
        mock_config.side_effect = self.test_config.get
        self.config.side_effect = self.test_config.get
        self.ExternalPortContext.return_value = \
            DummyContext(return_value=None)

        # Now test with bridge:bridge format
        self.test_config.set('bridge-mappings', 'physnet1:br-foo')
        self.test_config.set('data-port', 'br-foo:br-juju')
        _nics.return_value = ['br-juju']
        self.add_bridge.reset_mock()
        self.add_bridge_port.reset_mock()
        expected_ifdata = {
            'external-ids': {
                'charm-neutron-openvswitch': 'br-foo'
            }
        }
        nutils.configure_ovs()
        self.add_ovsbridge_linuxbridge.assert_called_once_with(
            'br-foo',
            'br-juju',
            ifdata=expected_ifdata,
            portdata=expected_ifdata,
        )
        self.log.assert_called_with(
            'br-juju is a Linux bridge: using Linux bridges in the data-port '
            'config is deprecated for removal after 21.10 release of OpenStack'
            ' charms.', level='WARNING')

    @patch.object(nutils, 'use_dvr')
    @patch('charmhelpers.contrib.network.ovs.charm_name')
    @patch('charmhelpers.contrib.openstack.context.config')
    def test_configure_ovs_starts_service_if_required(
            self, mock_config, _charm_name, _use_dvr):
        _use_dvr.return_value = False
        _charm_name.return_value = "neutron-openvswitch"
        mock_config.side_effect = self.test_config.get
        self.config.return_value = 'ovs'
        self.service_running.return_value = False
        nutils.configure_ovs()
        self.assertTrue(self.full_restart.called)

    @patch.object(nutils, 'use_dvr')
    @patch('charmhelpers.contrib.network.ovs.charm_name')
    @patch('charmhelpers.contrib.openstack.context.config')
    def test_configure_ovs_doesnt_restart_service(
            self, mock_config, _charm_name, _use_dvr):
        _use_dvr.return_value = False
        _charm_name.return_value = "neutron-openvswitch"
        mock_config.side_effect = self.test_config.get
        self.config.side_effect = self.test_config.get
        self.service_running.return_value = True
        nutils.configure_ovs()
        self.assertFalse(self.full_restart.called)

    @patch.object(nutils, 'use_dvr')
    @patch('charmhelpers.contrib.network.ovs.charm_name')
    @patch('charmhelpers.contrib.openstack.context.config')
    def test_configure_ovs_ovs_ext_port(
            self, mock_config, _charm_name, _use_dvr):
        _use_dvr.return_value = True
        _charm_name.return_value = "neutron-openvswitch"
        mock_config.side_effect = self.test_config.get
        self.config.side_effect = self.test_config.get
        self.test_config.set('ext-port', 'eth0')
        self.ExternalPortContext.return_value = \
            DummyContext(return_value={'ext_port': 'eth0'})
        # Ensure that bridges are marked as managed
        expected_brdata = {
            'datapath-type': 'system',
            'external-ids': {
                'charm-neutron-openvswitch': 'managed'
            }
        }
        expected_ifdata = {
            'external-ids': {
                'charm-neutron-openvswitch': 'br-ex'
            }
        }
        nutils.configure_ovs()
        self.add_bridge.assert_has_calls([
            call('br-int', brdata=expected_brdata),
            call('br-ex', brdata=expected_brdata),
            call('br-data', brdata=expected_brdata)
        ])
        self.add_bridge_port.assert_called_with('br-ex', 'eth0',
                                                ifdata=expected_ifdata,
                                                portdata=expected_ifdata)

    def _run_configure_ovs_dpdk(self, mock_config, _use_dvr, _charm_name,
                                _OVSDPDKDeviceContext,
                                _BridgePortInterfaceMap,
                                _parse_data_port_mappings,
                                _parse_bridge_mappings,
                                _late_init, _test_bonds,
                                _ovs_vhostuser_client=False):
        def _resolve_port_name(pci_address, device_index, late_init):
            if late_init:
                return 'dpdk-{}'.format(
                    hashlib.sha1(pci_address.encode('UTF-8')).hexdigest()[:7]
                )
            else:
                return 'dpdk{}'.format(device_index)

        pci = ['0000:00:1c.1', '0000:00:1c.2', '0000:00:1c.3']
        mac = ['00:00:00:00:00:01', '00:00:00:00:00:02', '00:00:00:00:00:03']
        br = ['br-phynet1', 'br-phynet2', 'br-phynet3']

        map_mock = MagicMock()
        ovs_dpdk_mock = MagicMock()
        if _test_bonds:
            _parse_data_port_mappings.return_value = {
                'bond0': br[0], 'bond1': br[1], 'bond2': br[2]}
            ovs_dpdk_mock.devices.return_value = OrderedDict([
                (pci[0], EntityMac('bond0', mac[0])),
                (pci[1], EntityMac('bond1', mac[1])),
                (pci[2], EntityMac('bond2', mac[2]))])
            map_mock.items.return_value = [
                (br[0], {'bond0': {_resolve_port_name(pci[0], 0, _late_init):
                                   {'type': 'dpdk', 'pci-address': pci[0]}}}),
                (br[1], {'bond1': {_resolve_port_name(pci[1], 1, _late_init):
                                   {'type': 'dpdk', 'pci-address': pci[1]}}}),
                (br[2], {'bond2': {_resolve_port_name(pci[2], 2, _late_init):
                                   {'type': 'dpdk', 'pci-address': pci[2]}}})]
            map_mock.get_ifdatamap.side_effect = [
                {_resolve_port_name(pci[0], 0, _late_init): {
                    'type': 'dpdk', 'mtu-request': 1500,
                    'options': {'dpdk-devargs': pci[0]}}},
                {_resolve_port_name(pci[1], 1, _late_init): {
                    'type': 'dpdk', 'mtu-request': 1500,
                    'options': {'dpdk-devargs': pci[1]}}},
                {_resolve_port_name(pci[2], 2, _late_init): {
                    'type': 'dpdk', 'mtu-request': 1500,
                    'options': {'dpdk-devargs': pci[2]}}}]
        else:
            _parse_data_port_mappings.return_value = {
                mac[0]: br[0], mac[1]: br[1], mac[2]: br[2]}
            ovs_dpdk_mock.devices.return_value = OrderedDict([
                (pci[0], EntityMac(br[0], mac[0])),
                (pci[1], EntityMac(br[1], mac[1])),
                (pci[2], EntityMac(br[2], mac[2]))])
            map_mock.items.return_value = [
                (br[0], {_resolve_port_name(pci[0], 0, _late_init):
                         {_resolve_port_name(pci[0], 0, _late_init):
                          {'type': 'dpdk', 'pci-address': pci[0]}}}),
                (br[1], {_resolve_port_name(pci[1], 1, _late_init):
                         {_resolve_port_name(pci[1], 1, _late_init):
                          {'type': 'dpdk', 'pci-address': pci[1]}}}),
                (br[2], {_resolve_port_name(pci[2], 2, _late_init):
                         {_resolve_port_name(pci[2], 2, _late_init):
                          {'type': 'dpdk', 'pci-address': pci[2]}}})]
            map_mock.get_ifdatamap.side_effect = [
                {_resolve_port_name(pci[0], 0, _late_init):
                 {'type': 'dpdk', 'mtu-request': 1500,
                  'options': {'dpdk-devargs': pci[0]}}},
                {_resolve_port_name(pci[1], 1, _late_init):
                 {'type': 'dpdk', 'mtu-request': 1500,
                  'options': {'dpdk-devargs': pci[1]}}},
                {_resolve_port_name(pci[2], 2, _late_init):
                 {'type': 'dpdk', 'mtu-request': 1500,
                  'options': {'dpdk-devargs': pci[2]}}}]

        _OVSDPDKDeviceContext.return_value = ovs_dpdk_mock
        _BridgePortInterfaceMap.return_value = map_mock
        _parse_bridge_mappings.return_value = {
            'phynet1': br[0], 'phynet2': br[1], 'phynet3': br[2]}
        _use_dvr.return_value = True
        _charm_name.return_value = "neutron-openvswitch"
        self.use_dpdk.return_value = True
        self.ovs_has_late_dpdk_init.return_value = _late_init
        self.ovs_vhostuser_client.return_value = _ovs_vhostuser_client
        mock_config.side_effect = self.test_config.get
        self.config.side_effect = self.test_config.get
        self.test_config.set('enable-dpdk', True)
        self.use_dpdk.return_value = True
        self.ovs_has_late_dpdk_init.return_value = _late_init
        self.ovs_vhostuser_client.return_value = _ovs_vhostuser_client
        nutils.configure_ovs()
        expetected_brdata = {
            'datapath-type': 'netdev',
            'external-ids': {
                'charm-neutron-openvswitch': 'managed'
            }
        }
        self.add_bridge.assert_has_calls([
            call('br-int', brdata=expetected_brdata),
            call('br-ex', brdata=expetected_brdata),
            call(br[0], brdata=expetected_brdata),
            call(br[1], brdata=expetected_brdata),
            call(br[2], brdata=expetected_brdata)],
            any_order=True
        )
        if _test_bonds:
            self.add_bridge_bond.assert_has_calls(
                [call(br[0], 'bond0',
                      [_resolve_port_name(pci[0], 0, _late_init)],
                      portdata={'bond_mode': 'balance-tcp',
                                'lacp': 'active',
                                'other_config': {'lacp-time': 'fast'},
                                'external-ids': {
                                    'charm-neutron-openvswitch': br[0]}},
                      ifdatamap={
                          _resolve_port_name(pci[0], 0, _late_init): {
                              'type': 'dpdk',
                              'mtu-request': 1500,
                              'options': {'dpdk-devargs': pci[0]},
                              'external-ids':{
                                  'charm-neutron-openvswitch': br[0]}}}),
                    call(br[1], 'bond1',
                         [_resolve_port_name(pci[1], 1, _late_init)],
                         portdata={'bond_mode': 'balance-tcp',
                                   'lacp': 'active',
                                   'other_config': {'lacp-time': 'fast'},
                                   'external-ids': {
                                       'charm-neutron-openvswitch': br[1]}},
                         ifdatamap={
                             _resolve_port_name(pci[1], 1, _late_init):{
                                 'type': 'dpdk',
                                 'mtu-request': 1500,
                                 'options': {'dpdk-devargs': pci[1]},
                                 'external-ids':{
                                     'charm-neutron-openvswitch': br[1]}}}),
                    call(br[2], 'bond2',
                         [_resolve_port_name(pci[2], 2, _late_init)],
                         portdata={'bond_mode': 'balance-tcp',
                                   'lacp': 'active',
                                   'other_config': {'lacp-time': 'fast'},
                                   'external-ids': {
                                       'charm-neutron-openvswitch': br[2]}},
                         ifdatamap={
                             _resolve_port_name(pci[2], 2, _late_init): {
                                 'type': 'dpdk',
                                 'mtu-request': 1500,
                                 'options': {'dpdk-devargs': pci[2]},
                                 'external-ids':{
                                     'charm-neutron-openvswitch': br[2]}}})],
                any_order=True)
        else:
            if _late_init:
                self.add_bridge_port.assert_has_calls([
                    call(br[0], _resolve_port_name(pci[0], 0, _late_init),
                         ifdata={'type': 'dpdk',
                                 'mtu-request': 1500,
                                 'options': {'dpdk-devargs': pci[0]},
                                 'external-ids':{
                                     'charm-neutron-openvswitch': br[0]}},
                         portdata={'external-ids': {
                             'charm-neutron-openvswitch': br[0]}},
                         linkup=False, promisc=None),
                    call(br[1], _resolve_port_name(pci[1], 1, _late_init),
                         ifdata={'type': 'dpdk',
                                 'mtu-request': 1500,
                                 'options': {'dpdk-devargs': pci[1]},
                                 'external-ids':{
                                     'charm-neutron-openvswitch': br[1]}},
                         portdata={'external-ids': {
                             'charm-neutron-openvswitch': br[1]}},
                         linkup=False, promisc=None),
                    call(br[2], _resolve_port_name(pci[2], 2, _late_init),
                         ifdata={'type': 'dpdk',
                                 'mtu-request': 1500,
                                 'options': {'dpdk-devargs': pci[2]},
                                 'external-ids':{
                                     'charm-neutron-openvswitch': br[2]}},
                         portdata={'external-ids': {
                             'charm-neutron-openvswitch': br[2]}},
                         linkup=False, promisc=None)], any_order=True)
            else:
                self.add_bridge_port.assert_has_calls([
                    call(br[0], _resolve_port_name(pci[0], 0, _late_init),
                         ifdata={'type': 'dpdk', 'mtu-request': 1500,
                         'external-ids': {'charm-neutron-openvswitch': br[0]}},
                         portdata={'external-ids': {
                             'charm-neutron-openvswitch': br[0]}},
                         linkup=False, promisc=None),
                    call(br[1], _resolve_port_name(pci[1], 1, _late_init),
                         ifdata={'type': 'dpdk', 'mtu-request': 1500,
                         'external-ids': {'charm-neutron-openvswitch': br[1]}},
                         portdata={'external-ids': {
                             'charm-neutron-openvswitch': br[1]}},
                         linkup=False, promisc=None),
                    call(br[2], _resolve_port_name(pci[2], 2, _late_init),
                         ifdata={'type': 'dpdk', 'mtu-request': 1500,
                         'external-ids': {'charm-neutron-openvswitch': br[2]}},
                         portdata={'external-ids': {
                             'charm-neutron-openvswitch': br[2]}},
                         linkup=False, promisc=None)], any_order=True)

    @patch.object(nutils, 'use_hw_offload', return_value=False)
    @patch.object(nutils, 'parse_bridge_mappings')
    @patch.object(nutils, 'parse_data_port_mappings')
    @patch.object(neutron_ovs_context, 'NeutronAPIContext')
    @patch.object(nutils, 'BridgePortInterfaceMap')
    @patch.object(nutils, 'OVSDPDKDeviceContext')
    @patch('charmhelpers.contrib.network.ovs.charm_name')
    @patch.object(nutils, 'use_dvr')
    @patch('charmhelpers.contrib.openstack.context.config')
    def test_configure_ovs_dpdk(self, mock_config, _use_dvr, _charm_name,
                                _OVSDPDKDeviceContext,
                                _BridgePortInterfaceMap,
                                _NeutronAPIContext,
                                _parse_data_port_mappings,
                                _parse_bridge_mappings,
                                _use_hw_offload):
        _NeutronAPIContext.return_value = DummyContext(
            return_value={'global_physnet_mtu': 1500})
        return self._run_configure_ovs_dpdk(mock_config, _use_dvr, _charm_name,
                                            _OVSDPDKDeviceContext,
                                            _BridgePortInterfaceMap,
                                            _parse_data_port_mappings,
                                            _parse_bridge_mappings,
                                            _late_init=False,
                                            _test_bonds=False)

    @patch.object(nutils, 'use_hw_offload', return_value=False)
    @patch.object(nutils, 'parse_bridge_mappings')
    @patch.object(nutils, 'parse_data_port_mappings')
    @patch.object(neutron_ovs_context, 'NeutronAPIContext')
    @patch.object(nutils, 'BridgePortInterfaceMap')
    @patch.object(nutils, 'OVSDPDKDeviceContext')
    @patch('charmhelpers.contrib.network.ovs.charm_name')
    @patch.object(nutils, 'use_dvr')
    @patch('charmhelpers.contrib.openstack.context.config')
    def test_configure_ovs_dpdk_late_init(self, mock_config, _use_dvr,
                                          _charm_name,
                                          _OVSDPDKDeviceContext,
                                          _BridgePortInterfaceMap,
                                          _NeutronAPIContext,
                                          _parse_data_port_mappings,
                                          _parse_bridge_mappings,
                                          _use_hw_offload):
        _NeutronAPIContext.return_value = DummyContext(
            return_value={'global_physnet_mtu': 1500})
        return self._run_configure_ovs_dpdk(mock_config, _use_dvr, _charm_name,
                                            _OVSDPDKDeviceContext,
                                            _BridgePortInterfaceMap,
                                            _parse_data_port_mappings,
                                            _parse_bridge_mappings,
                                            _late_init=True,
                                            _test_bonds=False)

    @patch.object(nutils, 'use_hw_offload', return_value=False)
    @patch.object(nutils, 'parse_bridge_mappings')
    @patch.object(nutils, 'parse_data_port_mappings')
    @patch.object(neutron_ovs_context, 'NeutronAPIContext')
    @patch.object(nutils, 'BridgePortInterfaceMap')
    @patch.object(nutils, 'OVSDPDKDeviceContext')
    @patch('charmhelpers.contrib.network.ovs.charm_name')
    @patch.object(nutils, 'use_dvr')
    @patch('charmhelpers.contrib.openstack.context.config')
    def test_configure_ovs_dpdk_late_init_bonds(self, mock_config, _use_dvr,
                                                _charm_name,
                                                _OVSDPDKDeviceContext,
                                                _BridgePortInterfaceMap,
                                                _NeutronAPIContext,
                                                _parse_data_port_mappings,
                                                _parse_bridge_mappings,
                                                _use_hw_offload):
        _NeutronAPIContext.return_value = DummyContext(
            return_value={'global_physnet_mtu': 1500})
        return self._run_configure_ovs_dpdk(mock_config, _use_dvr, _charm_name,
                                            _OVSDPDKDeviceContext,
                                            _BridgePortInterfaceMap,
                                            _parse_data_port_mappings,
                                            _parse_bridge_mappings,
                                            _late_init=True,
                                            _test_bonds=True)

    @patch.object(nutils, 'use_dvr')
    @patch('charmhelpers.contrib.network.ovs.charm_name')
    @patch('charmhelpers.contrib.openstack.context.config')
    def test_configure_ovs_enable_ipfix(self, mock_config, mock_charm_name,
                                        mock_use_dvr):
        mock_use_dvr.return_value = False
        mock_charm_name.return_value = "neutron-openvswitch"
        mock_config.side_effect = self.test_config.get
        self.config.side_effect = self.test_config.get
        self.test_config.set('ipfix-target', '127.0.0.1:80')
        nutils.configure_ovs()
        self.enable_ipfix.assert_has_calls([
            call('br-int', '127.0.0.1:80'),
            call('br-ex', '127.0.0.1:80'),
        ])

    @patch.object(nutils, 'use_dvr')
    @patch('charmhelpers.contrib.network.ovs.charm_name')
    @patch('charmhelpers.contrib.openstack.context.config')
    def test_configure_ovs_ensure_ext_port_ignored(
            self, mock_config, mock_charm_name, mock_use_dvr):
        mock_use_dvr.return_value = True
        mock_charm_name.return_value = "neutron-openvswitch"
        mock_config.side_effect = self.test_config.get
        self.config.side_effect = self.test_config.get
        # configure ext-port and data-port at the same time
        self.test_config.set('ext-port', 'p0')
        self.ExternalPortContext.return_value = DummyContext(
            return_value={'ext_port': 'p0'})
        self.test_config.set('data-port', 'br-data:p1')
        self.test_config.set('bridge-mappings', 'net0:br-data')
        nutils.configure_ovs()
        # assert that p0 wasn't added to br-ex
        self.assertNotIn(call('br-ex', 'p0', ifdata=ANY, portdata=ANY),
                         self.add_bridge_port.call_args_list)

    @patch.object(nutils, 'use_dvr')
    @patch('charmhelpers.contrib.network.ovs.charm_name')
    @patch('charmhelpers.contrib.openstack.context.config')
    def test_configure_ovs_ensure_ext_port_used(
            self, mock_config, mock_charm_name, mock_use_dvr):
        mock_use_dvr.return_value = True
        mock_charm_name.return_value = "neutron-openvswitch"
        mock_config.side_effect = self.test_config.get
        self.config.side_effect = self.test_config.get
        self.test_config.set('ext-port', 'p0')
        self.ExternalPortContext.return_value = DummyContext(
            return_value={'ext_port': 'p0'})
        # leave data-port empty to simulate legacy config
        self.test_config.set('data-port', '')
        nutils.configure_ovs()
        # assert that p0 was added to br-ex
        self.assertIn(call('br-ex', 'p0', ifdata=ANY, portdata=ANY),
                      self.add_bridge_port.call_args_list)

    @patch.object(neutron_ovs_context, 'SharedSecretContext')
    def test_get_shared_secret(self, _dvr_secret_ctxt):
        _dvr_secret_ctxt.return_value = \
            DummyContext(return_value={'shared_secret': 'supersecret'})
        self.assertEqual(nutils.get_shared_secret(), 'supersecret')

    @patch.object(nutils, 'check_restart_timestamps')
    def test_assess_status(self, mock_check_restart_timestamps):
        with patch.object(nutils, 'assess_status_func') as asf:
            callee = MagicMock()
            asf.return_value = callee
            nutils.assess_status('test-config')
            asf.assert_called_once_with('test-config', ['openvswitch-switch'])
            callee.assert_called_once_with()
            self.os_application_version_set.assert_called_with(
                nutils.VERSION_PACKAGE
            )
            mock_check_restart_timestamps.assert_called_once_with()

    @patch('charmhelpers.contrib.openstack.context.config')
    def test_check_ext_port_data_port_config(self, mock_config):
        mock_config.side_effect = self.test_config.get
        self.config.side_effect = self.test_config.get
        configs = [
            # conflicting, incorrect
            (('data-port', 'br-data:p0'), ('ext-port', 'p1'), 'blocked'),
            # deperacted but still correct
            (('data-port', ''), ('ext-port', 'p1'), None),
            # correct, modern
            (('data-port', 'br-data:p0'), ('ext-port', ''), None)]
        for (dp, ep, expected) in configs:
            self.test_config.set(*dp)
            self.test_config.set(*ep)
            status = nutils.check_ext_port_data_port_config(mock_config)
            self.assertIn(expected, status)

    @patch.object(nutils, 'REQUIRED_INTERFACES')
    @patch.object(nutils, 'sequence_status_check_functions')
    @patch.object(nutils, 'services')
    @patch.object(nutils, 'determine_ports')
    @patch.object(nutils, 'make_assess_status_func')
    @patch.object(nutils, 'enable_nova_metadata')
    def test_assess_status_func(self,
                                enable_nova_metadata,
                                make_assess_status_func,
                                determine_ports,
                                services,
                                sequence_functions,
                                REQUIRED_INTERFACES):
        services.return_value = 's1'
        determine_ports.return_value = 'p1'
        enable_nova_metadata.return_value = False
        sequence_functions.return_value = 'sequence_return'
        REQUIRED_INTERFACES.copy.return_value = {'Test': True}
        nutils.assess_status_func('test-config')
        # ports=None whilst port checks are disabled.
        make_assess_status_func.assert_called_once_with(
            'test-config',
            {'Test': True},
            charm_func='sequence_return',
            services='s1',
            ports=None)
        sequence_functions.assert_called_once_with(
            nutils.validate_ovs_use_veth,
            nutils.check_ext_port_data_port_config)

    def test_pause_unit_helper(self):
        with patch.object(nutils, '_pause_resume_helper') as prh:
            nutils.pause_unit_helper('random-config')
            prh.assert_called_once_with(nutils.pause_unit,
                                        'random-config', [])
        with patch.object(nutils, '_pause_resume_helper') as prh:
            nutils.resume_unit_helper('random-config')
            prh.assert_called_once_with(nutils.resume_unit,
                                        'random-config', [])

    @patch.object(nutils, 'services')
    @patch.object(nutils, 'determine_ports')
    def test_pause_resume_helper(self, determine_ports, services):
        f = MagicMock()
        services.return_value = 's1'
        determine_ports.return_value = 'p1'
        with patch.object(nutils, 'assess_status_func') as asf:
            asf.return_value = 'assessor'
            nutils._pause_resume_helper(f, 'some-config')
            asf.assert_called_once_with('some-config', [])
            # ports=None whilst port checks are disabled.
            f.assert_called_once_with('assessor', services='s1', ports=None)

    @patch.object(nutils, 'subprocess')
    @patch.object(nutils, 'shutil')
    def test_install_tmpfilesd_lxd(self, mock_shutil, mock_subprocess):
        self.init_is_systemd.return_value = True
        self.group_exists.return_value = False
        self.user_exists.return_value = False
        nutils.install_tmpfilesd()
        mock_shutil.copy.assert_not_called()
        mock_subprocess.check_call.assert_not_called()

    @patch.object(nutils, 'subprocess')
    @patch.object(nutils, 'shutil')
    def test_install_tmpfilesd_libvirt(self, mock_shutil, mock_subprocess):
        self.init_is_systemd.return_value = True
        self.group_exists.return_value = True
        self.user_exists.return_value = True
        nutils.install_tmpfilesd()
        mock_shutil.copy.assert_called_once()
        mock_subprocess.check_call.assert_called_once_with(
            ['systemd-tmpfiles', '--create']
        )

    @patch.object(nutils, 'is_unit_paused_set')
    @patch.object(nutils.subprocess, 'check_call')
    @patch.object(nutils, 'OVSDPDKDeviceContext')
    @patch.object(nutils, 'set_Open_vSwitch_column_value')
    def test_enable_ovs_dpdk(self,
                             _set_Open_vSwitch_column_value,
                             _OVSDPDKDeviceContext,
                             _check_call,
                             _is_unit_paused_set):
        mock_context = MagicMock()
        mock_context.cpu_mask.return_value = '0x03'
        mock_context.socket_memory.return_value = '4096,4096'
        mock_context.pci_whitelist.return_value = \
            '--pci-whitelist 00:0300:01'
        _OVSDPDKDeviceContext.return_value = mock_context
        _set_Open_vSwitch_column_value.return_value = True
        self.ovs_has_late_dpdk_init.return_value = True
        self.ovs_vhostuser_client.return_value = False
        _is_unit_paused_set.return_value = False
        nutils.enable_ovs_dpdk()
        _set_Open_vSwitch_column_value.assert_has_calls([
            call('other_config:dpdk-lcore-mask', '0x03'),
            call('other_config:dpdk-socket-mem', '4096,4096'),
            call('other_config:dpdk-init', 'true'),
            call('other_config:dpdk-extra',
                 '--vhost-owner libvirt-qemu:kvm --vhost-perm 0660 '
                 '--pci-whitelist 00:0300:01')
        ])
        _check_call.assert_called_once_with(
            nutils.UPDATE_ALTERNATIVES + [nutils.OVS_DPDK_BIN]
        )
        self.deferrable_svc_restart.assert_called_with(
            'openvswitch-switch',
            reason='DPDK Config changed')

    @patch.object(nutils, 'is_unit_paused_set')
    @patch.object(nutils.subprocess, 'check_call')
    @patch.object(nutils, 'OVSDPDKDeviceContext')
    @patch.object(nutils, 'set_Open_vSwitch_column_value')
    def test_enable_ovs_dpdk_vhostuser_client(
            self,
            _set_Open_vSwitch_column_value,
            _OVSDPDKDeviceContext,
            _check_call,
            _is_unit_paused_set):
        mock_context = MagicMock()
        mock_context.cpu_mask.return_value = '0x03'
        mock_context.socket_memory.return_value = '4096,4096'
        mock_context.pci_whitelist.return_value = \
            '--pci-whitelist 00:0300:01'
        _OVSDPDKDeviceContext.return_value = mock_context
        _set_Open_vSwitch_column_value.return_value = True
        self.ovs_has_late_dpdk_init.return_value = True
        self.ovs_vhostuser_client.return_value = True
        _is_unit_paused_set.return_value = False
        nutils.enable_ovs_dpdk()
        _set_Open_vSwitch_column_value.assert_has_calls([
            call('other_config:dpdk-lcore-mask', '0x03'),
            call('other_config:dpdk-socket-mem', '4096,4096'),
            call('other_config:dpdk-init', 'true'),
            call('other_config:dpdk-extra',
                 '--pci-whitelist 00:0300:01')
        ])
        _check_call.assert_called_once_with(
            nutils.UPDATE_ALTERNATIVES + [nutils.OVS_DPDK_BIN]
        )
        self.deferrable_svc_restart.assert_called_with(
            'openvswitch-switch',
            reason='DPDK Config changed')

    @patch.object(nutils.context, 'NeutronAPIContext')
    @patch.object(nutils, 'is_container')
    def test_use_dvr(self, _is_container, _NeutronAPIContext):
        _is_container.return_value = False
        _NeutronAPIContext()().get.return_value = True
        self.assertEquals(nutils.use_dvr(), True)
        _is_container.return_value = True
        self.assertEquals(nutils.use_dvr(), False)

    @patch.object(nutils.context, 'NeutronAPIContext')
    @patch.object(nutils, 'is_container')
    def test_use_l3ha(self, _is_container, _NeutronAPIContext):
        _is_container.return_value = False
        _NeutronAPIContext()().get.return_value = True
        self.assertEquals(nutils.use_l3ha(), True)
        _is_container.return_value = True
        self.assertEquals(nutils.use_l3ha(), False)

    @patch.object(nutils.context, 'NeutronAPIContext')
    @patch.object(nutils, 'is_container')
    def test_enable_nova_metadata(self, _is_container, _NeutronAPIContext):
        _is_container.return_value = False
        _NeutronAPIContext()().get.return_value = True
        self.assertEquals(nutils.enable_nova_metadata(), True)
        _is_container.return_value = True
        self.assertEquals(nutils.enable_nova_metadata(), False)

    @patch.object(nutils, 'config')
    @patch.object(nutils, 'is_container')
    def test_enable_local_dhcp(self, _is_container, _config):
        _is_container.return_value = False
        _config.return_value = True
        self.assertEquals(nutils.enable_local_dhcp(), True)
        _is_container.return_value = True
        self.assertEquals(nutils.enable_local_dhcp(), False)

    @patch.object(nutils, 'kv')
    def test_use_fqdn_hint(self, _kv):
        _kv().get.return_value = False
        self.assertEquals(nutils.use_fqdn_hint(), False)
        _kv().get.return_value = True
        self.assertEquals(nutils.use_fqdn_hint(), True)

    def test_use_hw_offload_rocky(self):
        self.os_release.return_value = 'rocky'
        self.test_config.set('enable-hardware-offload', True)
        self.assertFalse(nutils.use_hw_offload())

    def test_use_hw_offload_stein(self):
        self.os_release.return_value = 'stein'
        self.test_config.set('enable-hardware-offload', True)
        self.assertTrue(nutils.use_hw_offload())

    def test_use_hw_offload_disabled(self):
        self.os_release.return_value = 'stein'
        self.test_config.set('enable-hardware-offload', False)
        self.assertFalse(nutils.use_hw_offload())

    @patch.object(nutils, 'set_Open_vSwitch_column_value')
    def test_enable_hw_offload(self, _ovs_set):
        _ovs_set.return_value = True
        self.is_unit_paused_set.return_value = False
        nutils.enable_hw_offload()
        _ovs_set.assert_has_calls([
            call('other_config:hw-offload', 'true'),
            call('other_config:max-idle', '30000'),
        ])
        self.deferrable_svc_restart.assert_called_once_with(
            'openvswitch-switch',
            reason='Hardware offload config changed')

    @patch.object(nutils, 'set_Open_vSwitch_column_value')
    def test_enable_hw_offload_unit_paused(self, _ovs_set):
        _ovs_set.return_value = True
        self.is_unit_paused_set.return_value = True
        nutils.enable_hw_offload()
        _ovs_set.assert_has_calls([
            call('other_config:hw-offload', 'true'),
            call('other_config:max-idle', '30000'),
        ])
        self.service_restart.assert_not_called()

    @patch.object(nutils, 'set_Open_vSwitch_column_value')
    def test_enable_hw_offload_no_changes(self, _ovs_set):
        _ovs_set.return_value = False
        self.is_unit_paused_set.return_value = False
        nutils.enable_hw_offload()
        _ovs_set.assert_has_calls([
            call('other_config:hw-offload', 'true'),
            call('other_config:max-idle', '30000'),
        ])
        self.service_restart.assert_not_called()
