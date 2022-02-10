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

import platform

from unittest.mock import patch
from test_utils import CharmTestCase

import nova_compute_context as context

TO_PATCH = [
    'apt_install',
    'filter_installed_packages',
    'kv',
    'relation_ids',
    'relation_get',
    'related_units',
    'config',
    'log',
    '_save_flag_file',
    'lsb_release',
    'os_release',
    'get_relation_ip',
]

NEUTRON_CONTEXT = {
    'network_manager': 'neutron',
    'quantum_auth_strategy': 'keystone',
    'keystone_host': 'keystone_host',
    'auth_port': '5000',
    'auth_protocol': 'https',
    'quantum_url': 'http://quantum_url',
    'service_tenant_name': 'admin',
    'service_username': 'admin',
    'service_password': 'openstack',
    'admin_domain_name': 'admin_domain',
    'quantum_security_groups': 'yes',
    'quantum_plugin': 'ovs',
    'auth_host': 'keystone_host',
}


def fake_log(msg, level=None):
    level = level or 'INFO'
    print('[juju test log ({})] {}'.format(level, msg))


def raise_no_space(self):
    raise context.NoNetworkBinding


class FakeUnitdata(object):

    def __init__(self, **kwargs):
        self.unit_data = {}
        for name, value in kwargs.items():
            self.unit_data[name] = value

    def get(self, key, default=None, record=False):
        return self.unit_data.get(key, default)

    def set(self, key, value):
        self.unit_data[key] = value

    def flush(self):
        pass


class LxdContextTests(CharmTestCase):

    def setUp(self):
        super(LxdContextTests, self).setUp(context, TO_PATCH)
        self.relation_get.side_effect = self.test_relation.get
        self.relation_ids.return_value = 'lxd:0'
        self.related_units.return_value = 'lxd/0'

    def test_with_pool(self):
        self.test_relation.set({'pool': 'juju_lxd'})
        lxd = context.LxdContext()()
        self.assertEqual(lxd.get('storage_pool'), 'juju_lxd')

    def test_without_pool(self):
        lxd = context.LxdContext()()
        self.assertEqual(lxd.get('storage_pool'), None)


class NovaComputeContextTests(CharmTestCase):

    def setUp(self):
        super(NovaComputeContextTests, self).setUp(context, TO_PATCH)
        self.os_release.return_value = 'kilo'
        self.relation_get.side_effect = self.test_relation.get
        self.config.side_effect = self.test_config.get
        self.log.side_effect = fake_log
        self.host_uuid = 'e46e530d-18ae-4a67-9ff0-e6e2ba7c60a7'
        self.maxDiff = None

    def test_cloud_compute_context_no_relation(self):
        self.relation_ids.return_value = []
        cloud_compute = context.CloudComputeContext()
        self.assertEqual({}, cloud_compute())

    @patch.object(context, '_network_manager')
    def test_cloud_compute_context_restart_trigger(self, nm):
        nm.return_value = None
        cloud_compute = context.CloudComputeContext()
        with patch.object(cloud_compute, 'restart_trigger') as rt:
            rt.return_value = 'footrigger'
            ctxt = cloud_compute()
        self.assertEqual(ctxt.get('restart_trigger'), 'footrigger')

        with patch.object(cloud_compute, 'restart_trigger') as rt:
            rt.return_value = None
            ctxt = cloud_compute()
        self.assertEqual(ctxt.get('restart_trigger'), None)

    @patch.object(context, '_network_manager')
    def test_cloud_compute_volume_context_cinder(self, netman):
        netman.return_value = None
        self.relation_ids.return_value = 'cloud-compute:0'
        self.related_units.return_value = 'nova-cloud-controller/0'
        cloud_compute = context.CloudComputeContext()
        self.test_relation.set({'volume_service': 'cinder'})
        self.assertEqual({'volume_service': 'cinder',
                          'cross_az_attach': True}, cloud_compute())

    @patch.object(context, '_network_manager')
    def test_cloud_compute_cross_az_context(self, netman):
        netman.return_value = None
        self.relation_ids.return_value = 'cloud-compute:1'
        self.related_units.return_value = 'nova-cloud-controller/0'
        cloud_compute = context.CloudComputeContext()

        # Check no cross_az_attach value set, defaults to cross_az_attach=True
        self.test_relation.set({'volume_service': 'cinder'})
        self.assertEqual({'volume_service': 'cinder',
                          'cross_az_attach': True}, cloud_compute())

        # Check that explicit True setting for cross_az_attach
        self.test_relation.set({'volume_service': 'cinder',
                                'cross_az_attach': True})
        self.assertEqual({'volume_service': 'cinder',
                          'cross_az_attach': True}, cloud_compute())

        # Check false setting for cross_az_attach
        self.test_relation.set({'volume_service': 'cinder',
                                'cross_az_attach': False})
        self.assertEqual({'volume_service': 'cinder',
                          'cross_az_attach': False}, cloud_compute())

    @patch.object(context, '_network_manager')
    def test_cloud_compute_flatdhcp_context(self, netman):
        netman.return_value = 'flatdhcpmanager'
        self.relation_ids.return_value = 'cloud-compute:0'
        self.related_units.return_value = 'nova-cloud-controller/0'
        self.test_relation.set({
            'network_manager': 'FlatDHCPManager',
            'ec2_host': 'novaapihost'})
        cloud_compute = context.CloudComputeContext()
        ex_ctxt = {
            'network_manager': 'flatdhcpmanager',
            'network_manager_config': {
                'ec2_dmz_host': 'novaapihost',
                'flat_interface': 'eth1'
            },
        }
        self.assertEqual(ex_ctxt, cloud_compute())

    @patch.object(context, '_network_manager')
    def test_cloud_compute_vendordata_context(self, netman):
        self.relation_ids.return_value = 'cloud-compute:0'
        self.related_units.return_value = 'nova-cloud-controller/0'
        data = ('{"vendor_data": true, "vendor_data_url": "fake_url",'
                ' "foo": "bar",'
                ' "vendordata_providers": "StaticJSON,DynamicJSON"}')
        self.test_relation.set({
            'vendor_data': data
        })
        cloud_compute = context.CloudComputeContext()
        ex_ctxt = {
            'vendor_data': True,
            'vendor_data_url': 'fake_url',
            'vendordata_providers': 'StaticJSON,DynamicJSON',
        }
        self.assertEqual(ex_ctxt, cloud_compute())

    def test_cloud_compute_vendorJSON_context(self):
        self.relation_ids.return_value = 'cloud-compute:0'
        self.related_units.return_value = 'nova-cloud-controller/0'
        data = '{"good": json"}'
        self.test_relation.set({
            'vendor_json': data
        })
        cloud_compute = context.CloudComputeVendorJSONContext()
        ex_ctxt = {'vendor_data_json': data}
        self.assertEqual(ex_ctxt, cloud_compute())

    def test_cloud_compute_vendorJSON_context_empty(self):
        self.relation_ids.return_value = 'cloud-compute:0'
        self.related_units.return_value = 'nova-cloud-controller/0'
        data = ''
        self.test_relation.set({
            'vendor_json': data
        })
        cloud_compute = context.CloudComputeVendorJSONContext()
        ex_ctxt = {'vendor_data_json': '{}'}
        self.assertEqual(ex_ctxt, cloud_compute())

    @patch.object(context, '_neutron_plugin')
    @patch.object(context, '_neutron_url')
    @patch.object(context, '_network_manager')
    def test_cloud_compute_neutron_context(self, netman, url, plugin):
        self.relation_ids.return_value = 'cloud-compute:0'
        self.related_units.return_value = 'nova-cloud-controller/0'
        netman.return_value = 'neutron'
        plugin.return_value = 'ovs'
        url.return_value = 'http://nova-c-c:9696'
        self.test_relation.set(NEUTRON_CONTEXT)
        cloud_compute = context.CloudComputeContext()
        ex_ctxt = {
            'network_manager': 'neutron',
            'network_manager_config': {
                'api_version': '2.0',
                'auth_protocol': 'https',
                'service_protocol': 'http',
                'auth_port': '5000',
                'keystone_host': 'keystone_host',
                'neutron_admin_auth_url': 'https://keystone_host:5000/v2.0',
                'neutron_admin_password': 'openstack',
                'neutron_admin_tenant_name': 'admin',
                'neutron_admin_username': 'admin',
                'neutron_admin_domain_name': 'admin_domain',
                'neutron_auth_strategy': 'keystone',
                'neutron_plugin': 'ovs',
                'neutron_security_groups': True,
                'neutron_url': 'http://nova-c-c:9696',
                'service_protocol': 'http',
                'service_port': '5000',
            },
            'service_host': 'keystone_host',
            'admin_tenant_name': 'admin',
            'admin_user': 'admin',
            'admin_password': 'openstack',
            'admin_domain_name': 'admin_domain',
            'auth_port': '5000',
            'auth_protocol': 'https',
            'auth_host': 'keystone_host',
            'api_version': '2.0',
            'service_protocol': 'http',
            'service_port': '5000',
        }
        self.assertEqual(ex_ctxt, cloud_compute())
        self._save_flag_file.assert_called_with(
            path='/etc/nova/nm.conf', data='neutron')

    @patch.object(context, '_neutron_plugin')
    @patch.object(context, '_neutron_url')
    @patch.object(context, '_network_manager')
    def test_cloud_compute_neutron_ctxt_dns_domain(self, netman, url, plugin):
        self.relation_ids.return_value = 'cloud-compute:0'
        self.related_units.return_value = 'nova-cloud-controller/0'
        netman.return_value = 'neutron'
        plugin.return_value = 'ovs'
        url.return_value = 'http://nova-c-c:9696'
        neutron_context = NEUTRON_CONTEXT.copy()
        neutron_context.update({'dns_domain': 'example.tld'})
        self.test_relation.set(neutron_context)
        cloud_compute = context.CloudComputeContext()
        ex_ctxt = {
            'network_manager': 'neutron',
            'network_manager_config': {
                'api_version': '2.0',
                'auth_protocol': 'https',
                'service_protocol': 'http',
                'auth_port': '5000',
                'dns_domain': 'example.tld',
                'keystone_host': 'keystone_host',
                'neutron_admin_auth_url': 'https://keystone_host:5000/v2.0',
                'neutron_admin_password': 'openstack',
                'neutron_admin_tenant_name': 'admin',
                'neutron_admin_username': 'admin',
                'neutron_admin_domain_name': 'admin_domain',
                'neutron_auth_strategy': 'keystone',
                'neutron_plugin': 'ovs',
                'neutron_security_groups': True,
                'neutron_url': 'http://nova-c-c:9696',
                'service_protocol': 'http',
                'service_port': '5000',
            },
            'service_host': 'keystone_host',
            'admin_tenant_name': 'admin',
            'admin_user': 'admin',
            'admin_password': 'openstack',
            'admin_domain_name': 'admin_domain',
            'auth_port': '5000',
            'auth_protocol': 'https',
            'auth_host': 'keystone_host',
            'api_version': '2.0',
            'dns_domain': 'example.tld',
            'service_protocol': 'http',
            'service_port': '5000',
        }
        self.assertEqual(ex_ctxt, cloud_compute())
        self._save_flag_file.assert_called_with(
            path='/etc/nova/nm.conf', data='neutron')

    @patch.object(context, '_neutron_plugin')
    @patch.object(context, '_neutron_url')
    @patch.object(context, '_network_manager')
    def test_cloud_compute_neutron_ctxt_physnets(self, netman, url, plugin):
        self.relation_ids.return_value = 'cloud-compute:0'
        self.related_units.return_value = 'nova-cloud-controller/0'
        self.test_config.set('neutron-physnets', 'foo:0;bar:0,1')
        self.test_config.set('neutron-tunnel', '0,1')
        netman.return_value = 'neutron'
        plugin.return_value = 'ovs'
        url.return_value = 'http://nova-c-c:9696'
        self.test_relation.set(NEUTRON_CONTEXT)
        cloud_compute = context.CloudComputeContext()
        ex_ctxt = {
            'api_version': '2.0',
            'auth_protocol': 'https',
            'service_protocol': 'http',
            'auth_port': '5000',
            'keystone_host': 'keystone_host',
            'neutron_admin_auth_url': 'https://keystone_host:5000/v2.0',
            'neutron_admin_password': 'openstack',
            'neutron_admin_tenant_name': 'admin',
            'neutron_admin_username': 'admin',
            'neutron_admin_domain_name': 'admin_domain',
            'neutron_auth_strategy': 'keystone',
            'neutron_physnets': {'bar': '0,1', 'foo': '0'},
            'neutron_tunnel': '0,1',
            'neutron_plugin': 'ovs',
            'neutron_security_groups': True,
            'neutron_url': 'http://nova-c-c:9696',
            'service_protocol': 'http',
            'service_port': '5000',
        }
        self.assertEqual(ex_ctxt, cloud_compute()['network_manager_config'])

    @patch.object(context, '_network_manager')
    @patch.object(context, '_neutron_plugin')
    def test_neutron_plugin_context_no_setting(self, plugin, nm):
        plugin.return_value = None
        nm.return_Value = None
        qplugin = context.NeutronComputeContext()
        self.assertEqual({}, qplugin())

    def test_libvirt_context_libvirtd(self):
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'yakkety'}
        self.os_release.return_value = 'ocata'
        self.kv.return_value = FakeUnitdata(**{'host_uuid': self.host_uuid})
        self.test_config.set('enable-live-migration', False)
        libvirt = context.NovaComputeLibvirtContext()

        self.assertEqual(
            {'libvirtd_opts': '',
             'libvirt_user': 'libvirt',
             'arch': platform.machine(),
             'ksm': 'AUTO',
             'kvm_hugepages': 0,
             'listen_tls': 0,
             'host_uuid': self.host_uuid,
             'force_raw_images': True,
             'inject_password': False,
             'inject_partition': -2,
             'default_ephemeral_format': 'ext4',
             'reserved_host_disk': 0,
             'reserved_host_memory': 512}, libvirt())

    def test_libvirt_context_inject_password(self):
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'zesty'}
        self.os_release.return_value = 'ocata'
        self.kv.return_value = FakeUnitdata(**{'host_uuid': self.host_uuid})
        self.test_config.set('inject-password', True)
        libvirt = context.NovaComputeLibvirtContext()

        self.assertEqual(
            {'libvirtd_opts': '',
             'libvirt_user': 'libvirt',
             'arch': platform.machine(),
             'ksm': 'AUTO',
             'kvm_hugepages': 0,
             'listen_tls': 0,
             'host_uuid': self.host_uuid,
             'force_raw_images': True,
             'inject_password': True,
             'inject_partition': -1,
             'default_ephemeral_format': 'ext4',
             'reserved_host_disk': 0,
             'reserved_host_memory': 512}, libvirt())

    def test_libvirt_context_libvirtd_reserved_huge_pages_1(self):
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'yakkety'}
        self.os_release.return_value = 'ocata'
        self.kv.return_value = FakeUnitdata(**{'host_uuid': self.host_uuid})
        self.test_config.set('reserved-huge-pages', 'node:0,size:2048,count:6')
        libvirt = context.NovaComputeLibvirtContext()

        self.assertEqual(
            {'libvirtd_opts': '',
             'libvirt_user': 'libvirt',
             'arch': platform.machine(),
             'ksm': 'AUTO',
             'kvm_hugepages': 0,
             'listen_tls': 0,
             'host_uuid': self.host_uuid,
             'force_raw_images': True,
             'inject_password': False,
             'inject_partition': -2,
             'default_ephemeral_format': 'ext4',
             'reserved_host_disk': 0,
             'reserved_host_memory': 512,
             'reserved_huge_pages': ['node:0,size:2048,count:6']}, libvirt())

    def test_libvirt_context_libvirtd_reserved_huge_pages_2(self):
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'yakkety'}
        self.os_release.return_value = 'ocata'
        self.kv.return_value = FakeUnitdata(**{'host_uuid': self.host_uuid})
        self.test_config.set(
            'reserved-huge-pages',
            'node:0,size:2048,count:6;node:1,size:1G,count:32')
        libvirt = context.NovaComputeLibvirtContext()

        self.assertEqual(
            {'libvirtd_opts': '',
             'libvirt_user': 'libvirt',
             'arch': platform.machine(),
             'ksm': 'AUTO',
             'kvm_hugepages': 0,
             'listen_tls': 0,
             'host_uuid': self.host_uuid,
             'force_raw_images': True,
             'inject_password': False,
             'inject_partition': -2,
             'default_ephemeral_format': 'ext4',
             'reserved_host_disk': 0,
             'reserved_host_memory': 512,
             'reserved_huge_pages': ['node:0,size:2048,count:6',
                                     'node:1,size:1G,count:32']}, libvirt())

    def test_libvirt_bin_context_no_migration(self):
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'lucid'}
        self.kv.return_value = FakeUnitdata(**{'host_uuid': self.host_uuid})
        self.test_config.set('enable-live-migration', False)
        libvirt = context.NovaComputeLibvirtContext()

        self.assertEqual(
            {'libvirtd_opts': '-d',
             'libvirt_user': 'libvirtd',
             'arch': platform.machine(),
             'ksm': 'AUTO',
             'kvm_hugepages': 0,
             'listen_tls': 0,
             'host_uuid': self.host_uuid,
             'force_raw_images': True,
             'inject_password': False,
             'inject_partition': -2,
             'default_ephemeral_format': 'ext4',
             'reserved_host_disk': 0,
             'reserved_host_memory': 512}, libvirt())

    def test_libvirt_bin_context_migration_tcp_listen(self):
        self.kv.return_value = FakeUnitdata(**{'host_uuid': self.host_uuid})
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'lucid'}
        self.test_config.set('enable-live-migration', True)
        libvirt = context.NovaComputeLibvirtContext()

        self.assertEqual(
            {'libvirtd_opts': '-d -l',
             'libvirt_user': 'libvirtd',
             'arch': platform.machine(),
             'ksm': 'AUTO',
             'kvm_hugepages': 0,
             'listen_tls': 0,
             'host_uuid': self.host_uuid,
             'live_migration_uri': 'qemu+ssh://%s/system',
             'live_migration_completion_timeout': 800,
             'live_migration_downtime': 500,
             'live_migration_downtime_delay': 75,
             'live_migration_downtime_steps': 10,
             'live_migration_permit_auto_converge': False,
             'live_migration_permit_post_copy': False,
             'default_ephemeral_format': 'ext4',
             'force_raw_images': True,
             'inject_password': False,
             'inject_partition': -2,
             'reserved_host_disk': 0,
             'reserved_host_memory': 512}, libvirt())

    def test_libvirt_context_without_migration_network(self):
        self.kv.return_value = FakeUnitdata(**{'host_uuid': self.host_uuid})
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'xenial'}
        self.test_config.set('enable-live-migration', True)
        self.test_config.set('migration-auth-type', 'ssh')
        self.os_release.return_value = 'kilo'
        self.assertEquals(context.NovaComputeLibvirtContext()()[
                          'live_migration_uri'], 'qemu+ssh://%s/system')

    def test_libvirt_context_with_migration_network(self):
        self.kv.return_value = FakeUnitdata(**{'host_uuid': self.host_uuid})
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'xenial'}
        self.test_config.set('enable-live-migration', True)
        self.test_config.set('migration-auth-type', 'ssh')
        self.test_config.set('libvirt-migration-network', '10.5.0.0/16')
        self.os_release.return_value = 'rocky'
        context.NovaComputeLibvirtContext()()
        self.get_relation_ip.assert_called_with('migration',
                                                cidr_network="10.5.0.0/16")

    def test_libvirt_context_with_migration_space(self):
        self.kv.return_value = FakeUnitdata(**{'host_uuid': self.host_uuid})
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'xenial'}
        self.test_config.set('enable-live-migration', True)
        self.os_release.return_value = 'ocata'
        self.get_relation_ip.return_value = "10.5.0.5"
        libvirt_context = context.NovaComputeLibvirtContext()()
        self.get_relation_ip.assert_called_with('migration',
                                                cidr_network=None)
        self.assertTrue('live_migration_uri' not in libvirt_context.keys())
        self.assertEquals(libvirt_context['live_migration_scheme'], 'ssh')
        self.assertEquals(libvirt_context['live_migration_inbound_addr'],
                          '10.5.0.5')

    def test_libvirt_bin_context_migration_tcp_listen_with_auto_converge(self):
        self.kv.return_value = FakeUnitdata(**{'host_uuid': self.host_uuid})
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'lucid'}
        self.test_config.set('enable-live-migration', True)
        self.test_config.set('live-migration-permit-auto-converge', True)
        libvirt = context.NovaComputeLibvirtContext()

        self.assertEqual(
            {'libvirtd_opts': '-d -l',
             'libvirt_user': 'libvirtd',
             'arch': platform.machine(),
             'ksm': 'AUTO',
             'kvm_hugepages': 0,
             'listen_tls': 0,
             'host_uuid': self.host_uuid,
             'live_migration_uri': 'qemu+ssh://%s/system',
             'live_migration_completion_timeout': 800,
             'live_migration_downtime': 500,
             'live_migration_downtime_delay': 75,
             'live_migration_downtime_steps': 10,
             'live_migration_permit_auto_converge': True,
             'live_migration_permit_post_copy': False,
             'force_raw_images': True,
             'inject_password': False,
             'inject_partition': -2,
             'default_ephemeral_format': 'ext4',
             'reserved_host_disk': 0,
             'reserved_host_memory': 512}, libvirt())

    def test_libvirt_bin_context_migration_tcp_listen_with_post_copy(self):
        self.kv.return_value = FakeUnitdata(**{'host_uuid': self.host_uuid})
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'lucid'}
        self.test_config.set('enable-live-migration', True)
        self.test_config.set('live-migration-permit-post-copy', True)
        libvirt = context.NovaComputeLibvirtContext()

        self.assertEqual(
            {'libvirtd_opts': '-d -l',
             'libvirt_user': 'libvirtd',
             'arch': platform.machine(),
             'ksm': 'AUTO',
             'kvm_hugepages': 0,
             'listen_tls': 0,
             'host_uuid': self.host_uuid,
             'live_migration_uri': 'qemu+ssh://%s/system',
             'live_migration_completion_timeout': 800,
             'live_migration_downtime': 500,
             'live_migration_downtime_delay': 75,
             'live_migration_downtime_steps': 10,
             'live_migration_permit_auto_converge': False,
             'live_migration_permit_post_copy': True,
             'default_ephemeral_format': 'ext4',
             'force_raw_images': True,
             'inject_password': False,
             'inject_partition': -2,
             'reserved_host_disk': 0,
             'reserved_host_memory': 512}, libvirt())

    def test_libvirt_disk_cachemodes(self):
        self.kv.return_value = FakeUnitdata(**{'host_uuid': self.host_uuid})
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'lucid'}
        self.test_config.set('disk-cachemodes', 'file=unsafe,block=none')
        libvirt = context.NovaComputeLibvirtContext()

        self.assertEqual(
            {'libvirtd_opts': '-d',
             'libvirt_user': 'libvirtd',
             'disk_cachemodes': 'file=unsafe,block=none',
             'arch': platform.machine(),
             'ksm': 'AUTO',
             'kvm_hugepages': 0,
             'listen_tls': 0,
             'host_uuid': self.host_uuid,
             'force_raw_images': True,
             'inject_password': False,
             'inject_partition': -2,
             'default_ephemeral_format': 'ext4',
             'reserved_host_disk': 0,
             'reserved_host_memory': 512}, libvirt())

    def test_libvirt_hugepages(self):
        self.kv.return_value = FakeUnitdata(**{'host_uuid': self.host_uuid})
        self.os_release.return_value = 'kilo'
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'lucid'}
        self.test_config.set('hugepages', '22')
        libvirt = context.NovaComputeLibvirtContext()

        self.assertEqual(
            {'libvirtd_opts': '-d',
             'libvirt_user': 'libvirtd',
             'arch': platform.machine(),
             'hugepages': True,
             'ksm': 'AUTO',
             'kvm_hugepages': 1,
             'listen_tls': 0,
             'host_uuid': self.host_uuid,
             'force_raw_images': True,
             'inject_password': False,
             'inject_partition': -2,
             'default_ephemeral_format': 'ext4',
             'reserved_host_disk': 0,
             'reserved_host_memory': 512}, libvirt())

    def test_libvirt_context_libvirtd_force_raw_images(self):
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'zesty'}
        self.os_release.return_value = 'ocata'
        self.kv.return_value = FakeUnitdata(**{'host_uuid': self.host_uuid})
        self.test_config.set('force-raw-images', False)
        libvirt = context.NovaComputeLibvirtContext()

        self.assertEqual(
            {'libvirtd_opts': '',
             'libvirt_user': 'libvirt',
             'arch': platform.machine(),
             'ksm': 'AUTO',
             'kvm_hugepages': 0,
             'listen_tls': 0,
             'host_uuid': self.host_uuid,
             'force_raw_images': False,
             'inject_password': False,
             'inject_partition': -2,
             'default_ephemeral_format': 'ext4',
             'reserved_host_disk': 0,
             'reserved_host_memory': 512}, libvirt())

    def test_lxd_live_migration_opts_xenial(self):
        self.kv.return_value = FakeUnitdata(**{'host_uuid': self.host_uuid})
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'xenial'}
        self.test_config.set('enable-live-migration', False)
        self.test_config.set('virt-type', 'lxd')

        lxd = context.NovaComputeVirtContext()
        self.assertEqual({'resume_guests_state_on_host_boot': False}, lxd())

    def test_lxd_live_migration_opts_yakkety(self):
        self.kv.return_value = FakeUnitdata(**{'host_uuid': self.host_uuid})
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'yakkety'}
        self.test_config.set('enable-live-migration', True)
        self.test_config.set('virt-type', 'lxd')

        lxd = context.NovaComputeVirtContext()
        self.assertEqual(
            {'enable_live_migration': True,
             'resume_guests_state_on_host_boot': False,
             'virt_type': 'lxd'}, lxd())

    def test_resume_guests_state_on_host_boot(self):
        self.kv.return_value = FakeUnitdata(**{'host_uuid': self.host_uuid})
        self.os_release.return_value = 'diablo'
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'lucid'}
        self.test_config.set('resume-guests-state-on-host-boot', True)
        lxd = context.NovaComputeVirtContext()
        self.assertEqual({'resume_guests_state_on_host_boot': True}, lxd())

    @patch.object(context.uuid, 'uuid4')
    def test_libvirt_new_uuid(self, mock_uuid):
        self.kv.return_value = FakeUnitdata()
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'lucid'}
        mock_uuid.return_value = '73874c1c-ba48-406d-8d99-ac185d83b9bc'
        libvirt = context.NovaComputeLibvirtContext()
        self.assertEqual(libvirt()['host_uuid'],
                         '73874c1c-ba48-406d-8d99-ac185d83b9bc')

    def test_libvirt_opts_trusty(self):
        self.kv.return_value = FakeUnitdata(**{'host_uuid': self.host_uuid})
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'trusty'}
        libvirt = context.NovaComputeLibvirtContext()
        self.assertEqual(libvirt()['libvirtd_opts'], '-d')

    def test_libvirt_opts_xenial(self):
        self.kv.return_value = FakeUnitdata(**{'host_uuid': self.host_uuid})
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'xenial'}
        libvirt = context.NovaComputeLibvirtContext()
        self.assertEqual(libvirt()['libvirtd_opts'], '')

    @patch.object(context.uuid, 'uuid4')
    def test_libvirt_cpu_mode_host_passthrough(self, mock_uuid):
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'lucid'}
        self.test_config.set('cpu-mode', 'host-passthrough')
        mock_uuid.return_value = 'e46e530d-18ae-4a67-9ff0-e6e2ba7c60a7'
        libvirt = context.NovaComputeLibvirtContext()

        self.assertEqual(libvirt()['cpu_mode'],
                         'host-passthrough')

    @patch.object(context.uuid, 'uuid4')
    def test_libvirt_cpu_mode_none(self, mock_uuid):
        self.test_config.set('cpu-mode', 'none')
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'lucid'}
        mock_uuid.return_value = 'e46e530d-18ae-4a67-9ff0-e6e2ba7c60a7'
        libvirt = context.NovaComputeLibvirtContext()

        self.assertEqual(libvirt()['cpu_mode'],
                         'none')

    @patch.object(context, 'platform')
    @patch.object(context.uuid, 'uuid4')
    def test_libvirt_cpu_mode_aarch64(self, mock_uuid, mock_platform):
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'xenial'}
        mock_uuid.return_value = 'e46e530d-18ae-4a67-9ff0-e6e2ba7c60a7'
        mock_platform.machine.return_value = 'aarch64'
        libvirt = context.NovaComputeLibvirtContext()

        self.assertEqual(libvirt()['cpu_mode'],
                         'host-passthrough')

    def test_libvirt_vnf_configs(self):
        self.kv.return_value = FakeUnitdata(**{'host_uuid': self.host_uuid})
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'lucid'}
        self.test_config.set('hugepages', '22')
        self.test_config.set('reserved-host-memory', 1024)
        self.test_config.set('reserved-host-disk', 65536)
        self.test_config.set('vcpu-pin-set', '^0^2')
        self.test_config.set('pci-passthrough-whitelist', 'mypcidevices')
        self.test_config.set('virtio-net-tx-queue-size', 512)
        self.test_config.set('virtio-net-rx-queue-size', 1024)
        self.test_config.set('num-pcie-ports', 15)
        self.test_config.set('cpu-shared-set', "4-12,^8,15")
        self.test_config.set('cpu-dedicated-set', "0-3,^10,33")
        libvirt = context.NovaComputeLibvirtContext()

        self.assertEqual(
            {'libvirtd_opts': '-d',
             'libvirt_user': 'libvirtd',
             'arch': platform.machine(),
             'ksm': 'AUTO',
             'hugepages': True,
             'kvm_hugepages': 1,
             'listen_tls': 0,
             'host_uuid': self.host_uuid,
             'reserved_host_memory': 1024,
             'reserved_host_disk': 65536,
             'force_raw_images': True,
             'inject_password': False,
             'inject_partition': -2,
             'pci_passthrough_whitelist': 'mypcidevices',
             'virtio_net_tx_queue_size': 512,
             'virtio_net_rx_queue_size': 1024,
             'num_pcie_ports': 15,
             'default_ephemeral_format': 'ext4',
             'cpu_shared_set': "4-12,^8,15",
             'cpu_dedicated_set': "0-3,^10,33"}, libvirt())

    def test_vcpu_pin_set(self):
        self.kv.return_value = FakeUnitdata(**{'host_uuid': self.host_uuid})
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'lucid'}
        self.test_config.set('vcpu-pin-set', '^0^2')
        libvirt = context.NovaComputeLibvirtContext()

        self.assertEqual(
            {'libvirtd_opts': '-d',
             'libvirt_user': 'libvirtd',
             'arch': platform.machine(),
             'ksm': 'AUTO',
             'kvm_hugepages': 0,
             'listen_tls': 0,
             'host_uuid': self.host_uuid,
             'reserved_host_disk': 0,
             'reserved_host_memory': 512,
             'vcpu_pin_set': '^0^2',
             'force_raw_images': True,
             'inject_password': False,
             'inject_partition': -2,
             'default_ephemeral_format': 'ext4'}, libvirt())

    def test_cpu_dedicated_set(self):
        self.kv.return_value = FakeUnitdata(**{'host_uuid': self.host_uuid})
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'lucid'}
        self.test_config.set('cpu-shared-set', '4-15')
        self.test_config.set('cpu-dedicated-set', '16-31')
        libvirt = context.NovaComputeLibvirtContext()

        expected = {'libvirtd_opts': '-d',
                    'libvirt_user': 'libvirtd',
                    'arch': platform.machine(),
                    'ksm': 'AUTO',
                    'kvm_hugepages': 0,
                    'listen_tls': 0,
                    'host_uuid': self.host_uuid,
                    'reserved_host_disk': 0,
                    'reserved_host_memory': 512,
                    'cpu_shared_set': '4-15',
                    'cpu_dedicated_set': '16-31',
                    'force_raw_images': True,
                    'inject_password': False,
                    'inject_partition': -2,
                    'default_ephemeral_format': 'ext4'}

        self.assertEqual(expected, libvirt())

        # should be ignored
        self.test_config.set('vcpu-pin-set', '16-31')
        libvirt = context.NovaComputeLibvirtContext()
        self.assertEqual(expected, libvirt())

    def test_ksm_configs(self):
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'lucid'}

        self.test_config.set('ksm', '1')
        libvirt = context.NovaComputeLibvirtContext()
        self.assertTrue(libvirt()['ksm'] == '1')

        self.test_config.set('ksm', '0')
        libvirt = context.NovaComputeLibvirtContext()
        self.assertTrue(libvirt()['ksm'] == '0')

        self.test_config.set('ksm', 'AUTO')
        libvirt = context.NovaComputeLibvirtContext()
        self.assertTrue(libvirt()['ksm'] == 'AUTO')

        self.test_config.set('ksm', '')
        libvirt = context.NovaComputeLibvirtContext()
        self.assertTrue(libvirt()['ksm'] == 'AUTO')

        self.os_release.return_value = 'ocata'
        self.test_config.set('ksm', 'AUTO')
        libvirt = context.NovaComputeLibvirtContext()
        self.assertTrue(libvirt()['ksm'] == 'AUTO')

        self.os_release.return_value = 'kilo'
        self.test_config.set('ksm', 'AUTO')
        libvirt = context.NovaComputeLibvirtContext()
        self.assertTrue(libvirt()['ksm'] == 'AUTO')

        self.os_release.return_value = 'diablo'
        self.test_config.set('ksm', 'AUTO')
        libvirt = context.NovaComputeLibvirtContext()
        self.assertTrue(libvirt()['ksm'] == '1')

    @patch.object(context.uuid, 'uuid4')
    def test_libvirt_cpu_mode_default(self, mock_uuid):
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'lucid'}
        libvirt = context.NovaComputeLibvirtContext()
        self.assertFalse('cpu-mode' in libvirt())

    @patch('subprocess.call')
    def test_host_IP_context(self, _call):
        self.log = fake_log
        self.get_relation_ip.return_value = '172.24.0.79'
        host_ip = context.HostIPContext()
        self.assertEqual({'host_ip': '172.24.0.79'}, host_ip())
        self.get_relation_ip.assert_called_with('cloud-compute',
                                                cidr_network=None)

    @patch('subprocess.call')
    def test_host_IP_context_ipv6(self, _call):
        self.log = fake_log
        self.test_config.set('prefer-ipv6', True)
        self.get_relation_ip.return_value = '2001:db8:0:1::2'
        self.kv.return_value = FakeUnitdata()
        host_ip = context.HostIPContext()
        self.assertEqual({'host_ip': '2001:db8:0:1::2'}, host_ip())
        self.assertTrue(self.get_relation_ip.called)

    def test_metadata_service_ctxt(self):
        self.relation_ids.return_value = 'neutron-plugin:0'
        self.related_units.return_value = 'neutron-openvswitch/0'
        self.test_relation.set({'metadata-shared-secret': 'shared_secret'})
        metadatactxt = context.MetadataServiceContext()
        self.assertEqual(metadatactxt(), {'metadata_shared_secret':
                                          'shared_secret'})

    def test_nova_metadata_requirement(self):
        self.relation_ids.return_value = ['neutron-plugin:0']
        self.related_units.return_value = ['neutron-api/0']
        self.test_relation.set({'metadata-shared-secret': 'secret'})
        self.assertEqual(context.nova_metadata_requirement(),
                         (True, 'secret'))
        self.test_relation.set({})
        self.assertEqual(context.nova_metadata_requirement(),
                         (False, None))
        self.test_relation.set({'enable-metadata': 'true'})
        self.assertEqual(context.nova_metadata_requirement(),
                         (True, None))

    def test_nova_compute_extra_flags(self):
        self.test_config.set('cpu-model-extra-flags', 'pcid vmx pdpe1gb')
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'bionic'}
        libvirt = context.NovaComputeLibvirtContext()

        self.assertEqual(libvirt()['cpu_model_extra_flags'],
                         'pcid, vmx, pdpe1gb')

    _pci_alias1 = (
        '{'
        '"name": "IntelNIC",'
        '"capability_type": "pci",'
        '"product_id": "1111",'
        '"vendor_id": "8086",'
        '"device_type": "type-PF"'
        '}'
    )

    _pci_alias2 = (
        '{'
        '"name": " Cirrus Logic ",'
        '"capability_type": "pci",'
        '"product_id": "0ff2",'
        '"vendor_id": "10de",'
        '"device_type": "type-PCI"'
        '}'
    )

    _pci_alias_list = "[" + _pci_alias1 + "," + _pci_alias2 + "]"

    @patch('charmhelpers.contrib.openstack.ip.unit_get')
    @patch('charmhelpers.contrib.hahelpers.cluster.relation_ids')
    @patch('charmhelpers.core.hookenv.local_unit')
    @patch('charmhelpers.contrib.openstack.context.config')
    def test_nova_config_context_multi_pci_alias_pike(self, mock_config,
                                                      local_unit,
                                                      mock_relation_ids,
                                                      mock_unit_get):
        self.os_release.return_value = 'pike'
        local_unit.return_value = 'nova-compute/0'
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'xenial'}
        mock_config.side_effect = self.test_config.get
        mock_unit_get.return_value = '127.0.0.1'
        self.test_config.set('pci-alias', self._pci_alias_list)
        ctxt = context.NovaComputeLibvirtContext()()
        self.assertEqual(
            ctxt['pci_alias'],
            ('[{"capability_type": "pci", "device_type": "type-PF", '
             '"name": "IntelNIC", "product_id": "1111", '
             '"vendor_id": "8086"}, '
             '{"capability_type": "pci", "device_type": "type-PCI", '
             '"name": " Cirrus Logic ", "product_id": "0ff2", '
             '"vendor_id": "10de"}]'))

    @patch('charmhelpers.contrib.openstack.ip.unit_get')
    @patch('charmhelpers.contrib.hahelpers.cluster.relation_ids')
    @patch('charmhelpers.core.hookenv.local_unit')
    @patch('charmhelpers.contrib.openstack.context.config')
    def test_nova_config_context_multi_pci_alias(self, mock_config,
                                                 local_unit,
                                                 mock_relation_ids,
                                                 mock_unit_get):
        local_unit.return_value = 'nova-compute/0'
        self.os_release.return_value = 'queens'
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'bionic'}
        mock_config.side_effect = self.test_config.get
        mock_unit_get.return_value = '127.0.0.1'
        self.test_config.set('pci-alias', self._pci_alias1)
        ctxt = context.NovaComputeLibvirtContext()()
        self.assertEqual(
            ctxt['pci_alias'],
            ('{"capability_type": "pci", "device_type": "type-PF", '
             '"name": "IntelNIC", "product_id": "1111", '
             '"vendor_id": "8086"}'))

    @patch('charmhelpers.contrib.openstack.ip.unit_get')
    @patch('charmhelpers.contrib.hahelpers.cluster.relation_ids')
    @patch('charmhelpers.core.hookenv.local_unit')
    @patch('charmhelpers.contrib.openstack.context.config')
    def test_nova_config_context_multi_pci_aliases(self, mock_config,
                                                   local_unit,
                                                   mock_relation_ids,
                                                   mock_unit_get):
        local_unit.return_value = 'nova-compute/0'
        self.os_release.return_value = 'queens'
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'bionic'}
        mock_config.side_effect = self.test_config.get
        mock_unit_get.return_value = '127.0.0.1'
        self.test_config.set('pci-alias', self._pci_alias_list)
        ctxt = context.NovaComputeLibvirtContext()()
        self.assertEqual(
            ctxt['pci_aliases'][0],
            ('{"capability_type": "pci", "device_type": "type-PF", '
             '"name": "IntelNIC", "product_id": "1111", '
             '"vendor_id": "8086"}'))
        self.assertEqual(
            ctxt['pci_aliases'][1],
            ('{"capability_type": "pci", "device_type": "type-PCI", '
             '"name": " Cirrus Logic ", "product_id": "0ff2", '
             '"vendor_id": "10de"}'))


class IronicAPIContextTests(CharmTestCase):

    def setUp(self):
        super(IronicAPIContextTests, self).setUp(context, TO_PATCH)
        self.relation_get.side_effect = self.test_relation.get

    def test_ironic_api_ready_no_relation(self):
        self.relation_ids.return_value = []
        self.assertEqual(
            context.IronicAPIContext()(), {})

    def test_ironic_api_ready(self):
        self.relation_ids.return_value = ['ironic-api:0']
        self.related_units.return_value = 'ironic-api/0'
        self.test_relation.set({
            'ironic-api-ready': True,
        })
        self.assertEqual(
            context.IronicAPIContext()(),
            {'ironic_api_ready': True})

    def test_ironic_api_not_ready(self):
        self.relation_ids.return_value = ['ironic-api:0']
        self.related_units.return_value = 'ironic-api/0'
        self.test_relation.set({
            'ready': False,
        })
        self.assertEqual(
            context.IronicAPIContext()(), {})


class SerialConsoleContextTests(CharmTestCase):

    def setUp(self):
        super(SerialConsoleContextTests, self).setUp(context, TO_PATCH)
        self.relation_get.side_effect = self.test_relation.get
        self.config.side_effect = self.test_config.get
        self.host_uuid = 'e46e530d-18ae-4a67-9ff0-e6e2ba7c60a7'

    def test_serial_console_disabled(self):
        self.relation_ids.return_value = ['cloud-compute:0']
        self.related_units.return_value = 'nova-cloud-controller/0'
        self.test_relation.set({
            'enable_serial_console': 'false',
        })
        self.assertEqual(
            context.SerialConsoleContext()(),
            {'enable_serial_console': 'false',
             'serial_console_base_url': 'ws://127.0.0.1:6083/'}
        )

    def test_serial_console_not_provided(self):
        self.relation_ids.return_value = ['cloud-compute:0']
        self.related_units.return_value = 'nova-cloud-controller/0'
        self.test_relation.set({
            'enable_serial_console': None,
        })
        self.assertEqual(
            context.SerialConsoleContext()(),
            {'enable_serial_console': 'false',
             'serial_console_base_url': 'ws://127.0.0.1:6083/'}
        )

    def test_serial_console_provided(self):
        self.relation_ids.return_value = ['cloud-compute:0']
        self.related_units.return_value = 'nova-cloud-controller/0'
        self.test_relation.set({
            'enable_serial_console': 'true',
            'serial_console_base_url': 'ws://10.10.10.1:6083/'
        })
        self.assertEqual(
            context.SerialConsoleContext()(),
            {'enable_serial_console': 'true',
             'serial_console_base_url': 'ws://10.10.10.1:6083/'}
        )

    def test_libvirt_use_multipath(self):
        self.kv.return_value = FakeUnitdata(**{'host_uuid': self.host_uuid})
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'yakkety'}
        self.os_release.return_value = 'ocata'
        self.test_config.set('use-multipath', True)
        libvirt = context.NovaComputeLibvirtContext()

        self.assertEqual(
            {'libvirtd_opts': '',
             'libvirt_user': 'libvirt',
             'use_multipath': True,
             'arch': platform.machine(),
             'ksm': 'AUTO',
             'kvm_hugepages': 0,
             'listen_tls': 0,
             'host_uuid': self.host_uuid,
             'force_raw_images': True,
             'inject_password': False,
             'inject_partition': -2,
             'default_ephemeral_format': 'ext4',
             'reserved_host_disk': 0,
             'reserved_host_memory': 512}, libvirt())


class NovaComputeAvailabilityZoneContextTests(CharmTestCase):

    def setUp(self):
        super(NovaComputeAvailabilityZoneContextTests,
              self).setUp(context, TO_PATCH)
        self.os_release.return_value = 'kilo'

    @patch('nova_compute_utils.config')
    @patch('os.environ.get')
    def test_availability_zone_no_juju_with_env(self, mock_get,
                                                mock_config):
        def environ_get_side_effect(key):
            return {
                'JUJU_AVAILABILITY_ZONE': 'az1',
            }[key]
        mock_get.side_effect = environ_get_side_effect

        def config_side_effect(key):
            return {
                'customize-failure-domain': False,
                'default-availability-zone': 'nova',
            }[key]

        mock_config.side_effect = config_side_effect
        az_context = context.NovaComputeAvailabilityZoneContext()
        self.assertEqual(
            {'default_availability_zone': 'nova'}, az_context())

    @patch('nova_compute_utils.config')
    @patch('os.environ.get')
    def test_availability_zone_no_juju_no_env(self, mock_get,
                                              mock_config):
        def environ_get_side_effect(key):
            return {
                'JUJU_AVAILABILITY_ZONE': '',
            }[key]
        mock_get.side_effect = environ_get_side_effect

        def config_side_effect(key):
            return {
                'customize-failure-domain': False,
                'default-availability-zone': 'nova',
            }[key]

        mock_config.side_effect = config_side_effect
        az_context = context.NovaComputeAvailabilityZoneContext()

        self.assertEqual(
            {'default_availability_zone': 'nova'}, az_context())

    @patch('os.environ.get')
    def test_availability_zone_juju(self, mock_get):
        def environ_get_side_effect(key):
            return {
                'JUJU_AVAILABILITY_ZONE': 'az1',
            }[key]
        mock_get.side_effect = environ_get_side_effect

        self.config.side_effect = self.test_config.get
        self.test_config.set('customize-failure-domain', True)
        az_context = context.NovaComputeAvailabilityZoneContext()
        self.assertEqual(
            {'default_availability_zone': 'az1'}, az_context())


class InstanceConsoleContextTest(CharmTestCase):

    def setUp(self):
        super(InstanceConsoleContextTest, self).setUp(context, TO_PATCH)
        self.os_release.return_value = 'mitaka'

    @patch.object(context, 'resolve_address')
    @patch.object(context, 'relation_ids')
    @patch.object(context, 'related_units')
    def test_spice(self,
                   mock_related_units,
                   mock_relation_ids,
                   mock_resolve_address):
        mock_relation_ids.return_value = ['cloud-compute:15']
        mock_related_units.return_value = ['nova-compute/0']
        mock_resolve_address.return_value = "internal-address"

        rel_settings = {
            'console_access_protocol': 'spice',
            'spice_agent_enabled': True,
            'console_keymap': 'en-us',
            'console_proxy_spice_address': 'http://1.2.3.4:56/spice_auto.html',
            'console_proxy_spice_host': '1.2.3.4',
            'console_proxy_spice_port': '56',
        }

        def rel_get(key, rid, unit):
            return rel_settings[key]

        self.relation_get.side_effect = rel_get

        ctxt = context.InstanceConsoleContext()()

        self.assertEqual(ctxt['spice_agent_enabled'], True, str(ctxt))


class NovaComputeCephContextTest(CharmTestCase):

    def setUp(self):
        super().setUp(context, TO_PATCH)
        self.config.side_effect = self.test_config.get
        self.os_release.return_value = 'queens'

    @patch('charmhelpers.contrib.openstack.context.CephContext.__call__')
    def test_rbd_replicated_pool(self, mock_call):
        mock_call.return_value = {'mon_hosts': 'foo,bar'}
        ctxt = context.NovaComputeCephContext()()
        self.assertEqual(ctxt['rbd_pool'], 'nova')

    @patch('charmhelpers.contrib.openstack.context.CephContext.__call__')
    def test_rbd_ec_pool(self, mock_call):
        self.test_config.set('pool-type', 'erasure-coded')
        mock_call.return_value = {'mon_hosts': 'foo,bar'}
        ctxt = context.NovaComputeCephContext()()
        self.assertEqual(ctxt['rbd_pool'], 'nova-metadata')

        self.test_config.set('ec-rbd-metadata-pool', 'nova-newmetadata')
        ctxt = context.NovaComputeCephContext()()
        self.assertEqual(ctxt['rbd_pool'], 'nova-newmetadata')


class NeutronPluginSubordinateConfigContextTest(CharmTestCase):

    def setUp(self):
        super().setUp(context, TO_PATCH)

    @patch('charmhelpers.contrib.openstack.context.relation_ids')
    def test_context_complete(self, mock_relation_ids):
        mock_relation_ids.return_value = []
        ctxt = context.NeutronPluginSubordinateConfigContext(
            interface=['neutron-plugin'],
            service=['nova-compute', 'nova'],
            config_file='/etc/nova.conf')
        self.assertFalse(ctxt.context_complete({}))
        self.assertTrue(ctxt.context_complete({'sections': {}}))


class NovaComputePlacementContextTest(CharmTestCase):

    def setUp(self):
        super(NovaComputePlacementContextTest, self).setUp(context, TO_PATCH)
        self.config.side_effect = self.test_config.get
        self.os_release.return_value = 'train'
        self.maxDiff = None

    def test_allocation_ratio(self):
        self.test_config.set('cpu-allocation-ratio', 64)
        self.test_config.set('ram-allocation-ratio', 32.3)
        self.test_config.set('disk-allocation-ratio', 16)

        ctxt = context.NovaComputePlacementContext()

        self.assertEqual(
            {'cpu_allocation_ratio': 64,
             'ram_allocation_ratio': 32.3,
             'disk_allocation_ratio': 16,
             'initial_cpu_allocation_ratio': None,
             'initial_ram_allocation_ratio': None,
             'initial_disk_allocation_ratio': None}, ctxt())
