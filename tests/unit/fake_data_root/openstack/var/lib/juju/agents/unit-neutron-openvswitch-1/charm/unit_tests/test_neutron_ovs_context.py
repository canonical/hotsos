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

from test_utils import CharmTestCase
from test_utils import patch_open
from unittest.mock import patch
import neutron_ovs_context as context
import charmhelpers

_LSB_RELEASE_XENIAL = {
    'DISTRIB_CODENAME': 'xenial',
}

_LSB_RELEASE_TRUSTY = {
    'DISTRIB_CODENAME': 'trusty',
}

TO_PATCH = [
    'config',
    'unit_get',
    'get_host_ip',
    'network_get_primary_address',
    'relation_ids',
    'relation_get',
    'related_units',
    'lsb_release',
    'write_file',
]


def fake_context(settings):
    def outer():
        def inner():
            return settings
        return inner
    return outer


class OVSPluginContextTest(CharmTestCase):

    def setUp(self):
        super(OVSPluginContextTest, self).setUp(context, TO_PATCH)
        self.config.side_effect = self.test_config.get
        self.test_config.set('debug', True)
        self.test_config.set('verbose', True)
        self.test_config.set('use-syslog', True)
        self.network_get_primary_address.side_effect = NotImplementedError
        self.lsb_release.return_value = _LSB_RELEASE_XENIAL

    def tearDown(self):
        super(OVSPluginContextTest, self).tearDown()

    @patch('charmhelpers.contrib.openstack.context.config')
    @patch('charmhelpers.contrib.openstack.context.NeutronPortContext.'
           'resolve_ports')
    def test_data_port_name(self, mock_resolve_ports, config):
        self.test_config.set('data-port', 'br-data:em1')
        config.side_effect = self.test_config.get
        mock_resolve_ports.side_effect = lambda ports: ports
        self.assertEqual(
            charmhelpers.contrib.openstack.context.DataPortContext()(),
            {'em1': 'br-data'}
        )

    @patch('charmhelpers.contrib.openstack.context.is_phy_iface',
           lambda port: True)
    @patch('charmhelpers.contrib.openstack.context.config')
    @patch('charmhelpers.contrib.openstack.context.get_nic_hwaddr')
    @patch('charmhelpers.contrib.openstack.context.list_nics')
    def test_data_port_mac(self, list_nics, get_nic_hwaddr, config):
        machine_machs = {
            'em1': 'aa:aa:aa:aa:aa:aa',
            'eth0': 'bb:bb:bb:bb:bb:bb',
        }
        absent_mac = "cc:cc:cc:cc:cc:cc"
        config_macs = ("br-d1:%s br-d2:%s" %
                       (absent_mac, machine_machs['em1']))
        self.test_config.set('data-port', config_macs)
        config.side_effect = self.test_config.get
        list_nics.return_value = machine_machs.keys()
        get_nic_hwaddr.side_effect = lambda nic: machine_machs[nic]
        self.assertEqual(
            charmhelpers.contrib.openstack.context.DataPortContext()(),
            {'em1': 'br-d2'}
        )

    @patch.object(charmhelpers.contrib.openstack.utils,
                  'get_os_codename_package')
    @patch.object(charmhelpers.contrib.openstack.context, 'config',
                  lambda *args: None)
    @patch.object(charmhelpers.contrib.openstack.context, 'relation_get')
    @patch.object(charmhelpers.contrib.openstack.context, 'relation_ids')
    @patch.object(charmhelpers.contrib.openstack.context, 'related_units')
    @patch.object(charmhelpers.contrib.openstack.context, 'config')
    @patch.object(charmhelpers.contrib.openstack.context, 'local_address')
    @patch.object(charmhelpers.contrib.openstack.context, 'is_clustered')
    @patch.object(charmhelpers.contrib.openstack.context, 'https')
    @patch.object(context.OVSPluginContext, '_ensure_packages')
    @patch.object(charmhelpers.contrib.openstack.context,
                  'neutron_plugin_attribute')
    @patch.object(charmhelpers.contrib.openstack.context, 'unit_private_ip')
    def test_neutroncc_context_api_rel(self, _unit_priv_ip, _npa, _ens_pkgs,
                                       _https, _is_clus,
                                       _local_address,
                                       _config, _runits, _rids, _rget,
                                       _get_os_cdnm_pkg):
        def mock_npa(plugin, section, manager):
            if section == "driver":
                return "neutron.randomdriver"
            if section == "config":
                return "neutron.randomconfig"

        config = {'vlan-ranges': "physnet1:1000:1500 physnet2:2000:2500",
                  'use-syslog': True,
                  'verbose': True,
                  'debug': True,
                  'bridge-mappings': "physnet1:br-data physnet2:br-data",
                  'flat-network-providers': 'physnet3 physnet4',
                  'prevent-arp-spoofing': False,
                  'enable-dpdk': False,
                  'security-group-log-output-base': '/var/log/nsg.log',
                  'security-group-log-rate-limit': None,
                  'security-group-log-burst-limit': 25,
                  'keepalived-healthcheck-interval': 0,
                  'of-inactivity-probe': 10,
                  'disable-mlockall': False}

        def mock_config(key=None):
            if key:
                return config.get(key)

            return config

        _get_os_cdnm_pkg.return_value = 'ocata'
        self.maxDiff = None
        self.config.side_effect = mock_config
        _npa.side_effect = mock_npa
        _local_address.return_value = '127.0.0.13'
        _unit_priv_ip.return_value = '127.0.0.14'
        _is_clus.return_value = False
        _runits.return_value = ['unit1']
        _rids.return_value = ['rid2']
        rdata = {
            'neutron-security-groups': 'True',
            'l2-population': 'True',
            'enable-qos': 'True',
            'network-device-mtu': 1500,
            'overlay-network-type': 'gre',
            'enable-dvr': 'True',
        }
        _rget.side_effect = lambda *args, **kwargs: rdata
        self.get_host_ip.return_value = '127.0.0.15'
        napi_ctxt = context.OVSPluginContext()
        expect = {
            'neutron_security_groups': True,
            'distributed_routing': True,
            'verbose': True,
            'extension_drivers': 'qos',
            'local_ip': '127.0.0.15',
            'network_device_mtu': 1500,
            'veth_mtu': 1500,
            'config': 'neutron.randomconfig',
            'use_syslog': True,
            'enable_dpdk': False,
            'firewall_driver': 'iptables_hybrid',
            'network_manager': 'neutron',
            'debug': True,
            'core_plugin': 'neutron.randomdriver',
            'neutron_plugin': 'ovs',
            'neutron_url': 'https://127.0.0.13:9696',
            'l2_population': True,
            'overlay_network_type': 'gre',
            'polling_interval': 2,
            'rpc_response_timeout': 60,
            'report_interval': 30,
            'network_providers': 'physnet3,physnet4',
            'bridge_mappings': 'physnet1:br-data,physnet2:br-data',
            'vlan_ranges': 'physnet1:1000:1500,physnet2:2000:2500',
            'prevent_arp_spoofing': False,
            'enable_nsg_logging': False,
            'nsg_log_output_base': '/var/log/nsg.log',
            'nsg_log_rate_limit': None,
            'nsg_log_burst_limit': 25,
            'keepalived_healthcheck_interval': 0,
            'of_inactivity_probe': 10,
            'disable_mlockall': False,
        }
        self.assertEqual(expect, napi_ctxt())

    @patch.object(charmhelpers.contrib.openstack.utils,
                  'get_os_codename_package')
    @patch.object(charmhelpers.contrib.openstack.context, 'relation_get')
    @patch.object(charmhelpers.contrib.openstack.context, 'relation_ids')
    @patch.object(charmhelpers.contrib.openstack.context, 'related_units')
    @patch.object(charmhelpers.contrib.openstack.context, 'config')
    @patch.object(charmhelpers.contrib.openstack.context, 'local_address')
    @patch.object(charmhelpers.contrib.openstack.context, 'is_clustered')
    @patch.object(charmhelpers.contrib.openstack.context, 'https')
    @patch.object(context.OVSPluginContext, '_ensure_packages')
    @patch.object(charmhelpers.contrib.openstack.context,
                  'neutron_plugin_attribute')
    @patch.object(charmhelpers.contrib.openstack.context, 'unit_private_ip')
    def test_neutroncc_context_api_rel_disable_security(self,
                                                        _unit_priv_ip, _npa,
                                                        _ens_pkgs,
                                                        _https, _is_clus,
                                                        _local_address,
                                                        _config, _runits,
                                                        _rids, _rget,
                                                        _get_os_cdnm_pkg):
        def mock_npa(plugin, section, manager):
            if section == "driver":
                return "neutron.randomdriver"
            if section == "config":
                return "neutron.randomconfig"

        _get_os_cdnm_pkg.return_value = 'ocata'
        _npa.side_effect = mock_npa
        _config.return_value = 'ovs'
        _local_address.return_value = '127.0.0.13'
        _unit_priv_ip.return_value = '127.0.0.14'
        _is_clus.return_value = False
        self.test_config.set('disable-security-groups', True)
        _runits.return_value = ['unit1']
        _rids.return_value = ['rid2']
        rdata = {
            'neutron-security-groups': 'True',
            'l2-population': 'True',
            'enable-qos': 'True',
            'network-device-mtu': 1500,
            'overlay-network-type': 'gre',
        }
        _rget.side_effect = lambda *args, **kwargs: rdata
        self.get_host_ip.return_value = '127.0.0.15'
        napi_ctxt = context.OVSPluginContext()
        expect = {
            'distributed_routing': False,
            'neutron_alchemy_flags': {},
            'neutron_security_groups': False,
            'verbose': True,
            'extension_drivers': 'qos',
            'local_ip': '127.0.0.15',
            'veth_mtu': 1500,
            'network_device_mtu': 1500,
            'config': 'neutron.randomconfig',
            'use_syslog': True,
            'enable_dpdk': False,
            'firewall_driver': 'iptables_hybrid',
            'network_manager': 'neutron',
            'debug': True,
            'core_plugin': 'neutron.randomdriver',
            'neutron_plugin': 'ovs',
            'neutron_url': 'https://127.0.0.13:9696',
            'l2_population': True,
            'overlay_network_type': 'gre',
            'polling_interval': 2,
            'rpc_response_timeout': 60,
            'sriov_vfs_blanket': 'auto',
            'report_interval': 30,
            'bridge_mappings': 'physnet1:br-data',
            'vlan_ranges': 'physnet1:1000:2000',
            'prevent_arp_spoofing': True,
            'enable_nsg_logging': False,
            'nsg_log_output_base': None,
            'nsg_log_rate_limit': None,
            'nsg_log_burst_limit': 25,
            'keepalived_healthcheck_interval': 0,
            'of_inactivity_probe': 10,
            'disable_mlockall': False,
        }
        self.maxDiff = None
        self.assertEqual(expect, napi_ctxt())

    @patch.object(context, 'is_container')
    @patch.object(context, 'os_release')
    def test_disable_mlockall(self, _os_release, _is_container):
        _os_release.return_value = 'victoria'

        _is_container.return_value = True
        ovsp_ctxt = context.OVSPluginContext()
        self.assertTrue(ovsp_ctxt.disable_mlockall())

        _is_container.return_value = False
        ovsp_ctxt = context.OVSPluginContext()
        self.assertFalse(ovsp_ctxt.disable_mlockall())

        _os_release.return_value = 'liberty'
        ovsp_ctxt = context.OVSPluginContext()
        self.test_config.set('disable-mlockall', True)
        self.assertFalse(ovsp_ctxt.disable_mlockall())

        _os_release.return_value = 'mitaka'
        ovsp_ctxt = context.OVSPluginContext()
        self.test_config.set('disable-mlockall', True)
        self.assertTrue(ovsp_ctxt.disable_mlockall())

        _os_release.return_value = 'victoria'
        ovsp_ctxt = context.OVSPluginContext()
        self.test_config.set('disable-mlockall', False)
        self.assertFalse(ovsp_ctxt.disable_mlockall())


class ZoneContextTest(CharmTestCase):

    def setUp(self):
        super(ZoneContextTest, self).setUp(context, TO_PATCH)
        self.config.side_effect = self.test_config.get

    def tearDown(self):
        super(ZoneContextTest, self).tearDown()

    def test_default_availability_zone_not_provided(self):
        self.relation_ids.return_value = ['rid1']
        self.related_units.return_value = ['nova-compute/0']
        self.relation_get.return_value = None
        self.assertEqual(
            context.ZoneContext()(),
            {}
        )
        self.relation_ids.assert_called_with('neutron-plugin')
        self.relation_get.assert_called_once_with(
            'default_availability_zone',
            rid='rid1',
            unit='nova-compute/0')

    def test_default_availability_zone_provided(self):
        self.relation_ids.return_value = ['rid1']
        self.related_units.return_value = ['nova-compute/0']
        self.relation_get.return_value = 'nova'
        self.assertEqual(
            context.ZoneContext()(),
            {'availability_zone': 'nova'}
        )
        self.relation_ids.assert_called_with('neutron-plugin')
        self.relation_get.assert_called_once_with(
            'default_availability_zone',
            rid='rid1',
            unit='nova-compute/0')


class L3AgentContextTest(CharmTestCase):

    def setUp(self):
        super(L3AgentContextTest, self).setUp(context, TO_PATCH)
        self.config.side_effect = self.test_config.get

    def tearDown(self):
        super(L3AgentContextTest, self).tearDown()

    @patch.object(context, 'os_release')
    @patch.object(charmhelpers.contrib.openstack.utils,
                  'get_os_codename_package')
    @patch.object(charmhelpers.contrib.openstack.context, 'relation_get')
    @patch.object(charmhelpers.contrib.openstack.context, 'relation_ids')
    @patch.object(charmhelpers.contrib.openstack.context, 'related_units')
    def test_dvr_enabled(self, _runits, _rids, _rget,
                         _get_os_cdnm_pkg, _os_release):
        _runits.return_value = ['unit1']
        _rids.return_value = ['rid2']
        _os_release.return_value = 'stein'
        rdata = {
            'neutron-security-groups': 'True',
            'enable-dvr': 'True',
            'enable-fwaas': 'True',
            'l2-population': 'True',
            'overlay-network-type': 'vxlan',
            'network-device-mtu': 1500,
        }
        _rget.side_effect = lambda *args, **kwargs: rdata
        self.assertEqual(
            context.L3AgentContext()(), {
                'agent_mode': 'dvr',
                'use_l3ha': False,
                'external_configuration_new': True,
                'enable_nfg_logging': False,
                'nfg_log_burst_limit': 25,
                'nfg_log_output_base': None,
                'nfg_log_rate_limit': None,
                'l3_extension_plugins': 'fwaas_v2',
            }
        )

    @patch.object(context, 'os_release')
    @patch.object(charmhelpers.contrib.openstack.utils,
                  'get_os_codename_package')
    @patch.object(charmhelpers.contrib.openstack.context, 'relation_get')
    @patch.object(charmhelpers.contrib.openstack.context, 'relation_ids')
    @patch.object(charmhelpers.contrib.openstack.context, 'related_units')
    def test_dvr_enabled_l3ha_enabled(self, _runits, _rids, _rget,
                                      _get_os_cdnm_pkg, _os_release):
        _runits.return_value = ['unit1']
        _rids.return_value = ['rid2']
        _os_release.return_value = 'rocky'
        rdata = {
            'neutron-security-groups': 'True',
            'enable-dvr': 'True',
            'l2-population': 'True',
            'overlay-network-type': 'vxlan',
            'network-device-mtu': 1500,
            'enable-l3ha': 'True',
        }
        _rget.side_effect = lambda *args, **kwargs: rdata
        self.assertEqual(
            context.L3AgentContext()(), {
                'agent_mode': 'dvr',
                'use_l3ha': True,
                'external_configuration_new': True,
                'enable_nfg_logging': False,
                'nfg_log_burst_limit': 25,
                'nfg_log_output_base': None,
                'nfg_log_rate_limit': None,
                'l3_extension_plugins': '',
            }
        )

    @patch.object(context, 'os_release')
    @patch.object(charmhelpers.contrib.openstack.utils,
                  'get_os_codename_package')
    @patch.object(context, 'validate_nfg_log_path')
    @patch.object(charmhelpers.contrib.openstack.context, 'relation_get')
    @patch.object(charmhelpers.contrib.openstack.context, 'relation_ids')
    @patch.object(charmhelpers.contrib.openstack.context, 'related_units')
    def test_dvr_nfg_enabled(self, _runits, _rids, _rget,
                             _validate_nfg_log_path,
                             _get_os_cdnm_pkg, _os_release):
        _runits.return_value = ['unit1']
        _rids.return_value = ['rid2']
        _os_release.return_value = 'stein'
        rdata = {
            'neutron-security-groups': 'True',
            'enable-dvr': 'True',
            'enable-fwaas': 'True',
            'l2-population': 'True',
            'overlay-network-type': 'vxlan',
            'network-device-mtu': 1500,
            'enable-nfg-logging': 'True',
            'use_l3ha': False,
        }
        _rget.side_effect = lambda *args, **kwargs: rdata
        _validate_nfg_log_path.side_effect = lambda x: x
        self.test_config.set('firewall-group-log-output-base',
                             '/var/log/neutron/firewall.log')
        self.test_config.set('firewall-group-log-rate-limit', 200)
        self.test_config.set('firewall-group-log-burst-limit', 30)
        self.assertEqual(
            context.L3AgentContext()(), {
                'agent_mode': 'dvr',
                'external_configuration_new': True,
                'enable_nfg_logging': True,
                'nfg_log_burst_limit': 30,
                'nfg_log_output_base': '/var/log/neutron/firewall.log',
                'nfg_log_rate_limit': 200,
                'use_l3ha': False,
                'l3_extension_plugins': 'fwaas_v2,fwaas_v2_log',
            }
        )

    @patch.object(context, 'os_release')
    @patch.object(charmhelpers.contrib.openstack.utils,
                  'get_os_codename_package')
    @patch.object(context, 'validate_nfg_log_path')
    @patch.object(charmhelpers.contrib.openstack.context, 'relation_get')
    @patch.object(charmhelpers.contrib.openstack.context, 'relation_ids')
    @patch.object(charmhelpers.contrib.openstack.context, 'related_units')
    def test_dvr_nfg_enabled_mins(self, _runits, _rids, _rget,
                                  _validate_nfg_log_path,
                                  _get_os_cdnm_pkg, _os_release):
        _runits.return_value = ['unit1']
        _rids.return_value = ['rid2']
        _os_release.return_value = 'stein'
        rdata = {
            'neutron-security-groups': 'True',
            'enable-dvr': 'True',
            'enable-fwaas': 'True',
            'l2-population': 'True',
            'overlay-network-type': 'vxlan',
            'network-device-mtu': 1500,
            'enable-nfg-logging': 'True',
        }
        _rget.side_effect = lambda *args, **kwargs: rdata
        _validate_nfg_log_path.side_effect = lambda x: x
        self.test_config.set('firewall-group-log-output-base',
                             '/var/log/neutron/firewall.log')
        self.test_config.set('firewall-group-log-rate-limit', 90)
        self.test_config.set('firewall-group-log-burst-limit', 20)
        self.assertEqual(
            context.L3AgentContext()(), {
                'agent_mode': 'dvr',
                'external_configuration_new': True,
                'enable_nfg_logging': True,
                'nfg_log_burst_limit': 25,
                'nfg_log_output_base': '/var/log/neutron/firewall.log',
                'nfg_log_rate_limit': 100,
                'use_l3ha': False,
                'l3_extension_plugins': 'fwaas_v2,fwaas_v2_log',
            }
        )

    @patch.object(context, 'os_release')
    @patch.object(charmhelpers.contrib.openstack.utils,
                  'get_os_codename_package')
    @patch.object(charmhelpers.contrib.openstack.context, 'relation_get')
    @patch.object(charmhelpers.contrib.openstack.context, 'relation_ids')
    @patch.object(charmhelpers.contrib.openstack.context, 'related_units')
    def test_dvr_enabled_dvr_snat_enabled(self, _runits, _rids, _rget,
                                          _get_os_cdnm_pkg, _os_release):
        self.test_config.set('use-dvr-snat', True)
        _runits.return_value = ['unit1']
        _rids.return_value = ['rid2']
        _os_release.return_value = 'stein'
        rdata = {
            'neutron-security-groups': 'True',
            'enable-dvr': 'True',
            'enable-fwaas': 'True',
            'l2-population': 'True',
            'overlay-network-type': 'vxlan',
            'network-device-mtu': 1500,
        }
        _rget.side_effect = lambda *args, **kwargs: rdata
        self.assertEqual(
            context.L3AgentContext()(), {
                'agent_mode': 'dvr_snat',
                'use_l3ha': False,
                'external_configuration_new': True,
                'enable_nfg_logging': False,
                'nfg_log_burst_limit': 25,
                'nfg_log_output_base': None,
                'nfg_log_rate_limit': None,
                'l3_extension_plugins': 'fwaas_v2',
            }
        )

    @patch.object(context, 'os_release')
    @patch.object(charmhelpers.contrib.openstack.utils,
                  'get_os_codename_package')
    @patch.object(charmhelpers.contrib.openstack.context, 'relation_get')
    @patch.object(charmhelpers.contrib.openstack.context, 'relation_ids')
    @patch.object(charmhelpers.contrib.openstack.context, 'related_units')
    def test_dvr_disabled(self, _runits, _rids, _rget,
                          _get_os_cdnm_pkg, _os_release):
        _runits.return_value = ['unit1']
        _rids.return_value = ['rid2']
        _os_release.return_value = 'stein'
        rdata = {
            'neutron-security-groups': 'True',
            'enable-dvr': 'False',
            'enable-fwaas': 'True',
            'l2-population': 'True',
            'overlay-network-type': 'vxlan',
            'network-device-mtu': 1500,
        }
        _rget.side_effect = lambda *args, **kwargs: rdata
        self.assertEqual(context.L3AgentContext()(), {
            'agent_mode': 'legacy',
            'enable_nfg_logging': False,
            'nfg_log_burst_limit': 25,
            'nfg_log_output_base': None,
            'nfg_log_rate_limit': None,
            'l3_extension_plugins': 'fwaas_v2',
        })


class SharedSecretContext(CharmTestCase):

    def setUp(self):
        super(SharedSecretContext, self).setUp(context,
                                               TO_PATCH)
        self.config.side_effect = self.test_config.get

    @patch('os.path')
    @patch('uuid.uuid4')
    def test_secret_created_stored(self, _uuid4, _path):
        _path.exists.return_value = False
        _uuid4.return_value = 'secret_thing'
        self.assertEqual(context.get_shared_secret(),
                         'secret_thing')
        self.write_file.assert_called_once_with(
            context.SHARED_SECRET,
            'secret_thing',
            perms=0o400,
        )

    @patch('os.chmod')
    @patch('os.path')
    def test_secret_retrieved(self, _path, _chmod):
        _path.exists.return_value = True
        with patch_open() as (_open, _file):
            _file.read.return_value = 'secret_thing\n'
            self.assertEqual(context.get_shared_secret(),
                             'secret_thing')
            _open.assert_called_with(
                context.SHARED_SECRET.format('quantum'), 'r')
        _chmod.assert_called_once_with(
            context.SHARED_SECRET,
            0o400
        )

    @patch.object(context, 'NeutronAPIContext')
    @patch.object(context, 'get_shared_secret')
    def test_shared_secretcontext_dvr(self, _shared_secret,
                                      _NeutronAPIContext):
        _NeutronAPIContext.side_effect = fake_context({'enable_dvr': True})
        _shared_secret.return_value = 'secret_thing'
        self.assertEqual(context.SharedSecretContext()(),
                         {'shared_secret': 'secret_thing'})

    @patch.object(context, 'NeutronAPIContext')
    @patch.object(context, 'get_shared_secret')
    def test_shared_secretcontext_nodvr(self, _shared_secret,
                                        _NeutronAPIContext):
        _NeutronAPIContext.side_effect = fake_context({'enable_dvr': False})
        _shared_secret.return_value = 'secret_thing'
        self.assertEqual(context.SharedSecretContext()(), {})


class TestRemoteRestartContext(CharmTestCase):

    def setUp(self):
        super(TestRemoteRestartContext, self).setUp(context,
                                                    TO_PATCH)
        self.config.side_effect = self.test_config.get

    def test_restart_trigger_present(self):
        self.relation_ids.return_value = ['rid1']
        self.related_units.return_value = ['nova-compute/0']
        self.relation_get.return_value = {
            'restart-trigger': '8f73-f3adb96a90d8',
        }
        self.assertEqual(
            context.RemoteRestartContext()(),
            {'restart_trigger': '8f73-f3adb96a90d8'}
        )
        self.relation_ids.assert_called_with('neutron-plugin')

    def test_restart_trigger_present_alt_relation(self):
        self.relation_ids.return_value = ['rid1']
        self.related_units.return_value = ['nova-compute/0']
        self.relation_get.return_value = {
            'restart-trigger': '8f73-f3adb96a90d8',
        }
        self.assertEqual(
            context.RemoteRestartContext(['neutron-control'])(),
            {'restart_trigger': '8f73-f3adb96a90d8'}
        )
        self.relation_ids.assert_called_with('neutron-control')

    def test_restart_trigger_present_multi_relation(self):
        self.relation_ids.return_value = ['rid1']
        self.related_units.return_value = ['nova-compute/0']
        ids = [
            {'restart-trigger': '8f73'},
            {'restart-trigger': '2ac3'}]
        self.relation_get.side_effect = lambda rid, unit: ids.pop()
        self.assertEqual(
            context.RemoteRestartContext(
                ['neutron-plugin', 'neutron-control'])(),
            {'restart_trigger': '2ac3-8f73'}
        )
        self.relation_ids.assert_called_with('neutron-control')

    def test_restart_trigger_absent(self):
        self.relation_ids.return_value = ['rid1']
        self.related_units.return_value = ['nova-compute/0']
        self.relation_get.return_value = {}
        self.assertEqual(context.RemoteRestartContext()(), {})

    def test_restart_trigger_service(self):
        self.relation_ids.return_value = ['rid1']
        self.related_units.return_value = ['nova-compute/0']
        self.relation_get.return_value = {
            'restart-trigger-neutron': 'neutron-uuid',
        }
        self.assertEqual(
            context.RemoteRestartContext()(),
            {'restart_trigger_neutron': 'neutron-uuid'}
        )


class TestFirewallDriver(CharmTestCase):

    TO_PATCH = [
        'config',
        'lsb_release',
    ]

    def setUp(self):
        super(TestFirewallDriver, self).setUp(context,
                                              self.TO_PATCH)
        self.config.side_effect = self.test_config.get

    def test_get_firewall_driver_xenial_unset(self):
        ctxt = {'enable_nsg_logging': False}
        self.lsb_release.return_value = _LSB_RELEASE_XENIAL
        self.assertEqual(context._get_firewall_driver(ctxt),
                         context.IPTABLES_HYBRID)

    def test_get_firewall_driver_xenial_openvswitch(self):
        ctxt = {'enable_nsg_logging': False}
        self.test_config.set('firewall-driver', 'openvswitch')
        self.lsb_release.return_value = _LSB_RELEASE_XENIAL
        self.assertEqual(context._get_firewall_driver(ctxt),
                         context.OPENVSWITCH)

    def test_get_firewall_driver_xenial_invalid(self):
        ctxt = {'enable_nsg_logging': False}
        self.test_config.set('firewall-driver', 'foobar')
        self.lsb_release.return_value = _LSB_RELEASE_XENIAL
        self.assertEqual(context._get_firewall_driver(ctxt),
                         context.IPTABLES_HYBRID)

    def test_get_firewall_driver_trusty_openvswitch(self):
        ctxt = {'enable_nsg_logging': False}
        self.test_config.set('firewall-driver', 'openvswitch')
        self.lsb_release.return_value = _LSB_RELEASE_TRUSTY
        self.assertEqual(context._get_firewall_driver(ctxt),
                         context.IPTABLES_HYBRID)

    def test_get_firewall_driver_nsg_logging(self):
        ctxt = {'enable_nsg_logging': True}
        self.lsb_release.return_value = _LSB_RELEASE_XENIAL
        self.test_config.set('firewall-driver', 'openvswitch')
        self.assertEqual(context._get_firewall_driver(ctxt),
                         context.OPENVSWITCH)

    def test_get_firewall_driver_nsg_logging_iptables_hybrid(self):
        ctxt = {'enable_nsg_logging': True}
        self.lsb_release.return_value = _LSB_RELEASE_XENIAL
        self.assertEqual(context._get_firewall_driver(ctxt),
                         context.IPTABLES_HYBRID)
