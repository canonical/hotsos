# Copyright 2016-2021 Canonical Ltd
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

import os
import tempfile

import charmhelpers.contrib.openstack.utils as os_utils

import nova_compute_context as compute_context
import nova_compute_utils as utils

from unittest.mock import (
    patch,
    MagicMock,
    call
)
from test_utils import (
    CharmTestCase,
    patch_open,
    TestKV,
)


VIRSH_NET_LIST = """ Name                 State      Autostart     Persistent
----------------------------------------------------------
 somenet              active     yes           yes
 default              active     yes           yes
 altnet               active     yes           yes
"""

TO_PATCH = [
    'apt_install',
    'apt_update',
    'apt_purge',
    'apt_autoremove',
    'apt_mark',
    'filter_missing_packages',
    'config',
    'os_release',
    'log',
    'related_units',
    'relation_ids',
    'relation_get',
    'service_restart',
    'mkdir',
    'install_alternative',
    'MetadataServiceContext',
    'lsb_release',
    'charm_dir',
    'hugepage_support',
    'rsync',
    'Fstab',
    'os_application_version_set',
    'lsb_release',
    'storage_list',
    'storage_get',
    'vaultlocker',
    'kv',
    'check_call',
    'mkfs_xfs',
    'is_block_device',
    'is_device_mounted',
    'fstab_add',
    'mount',
]


class NovaComputeUtilsTests(CharmTestCase):

    def setUp(self):
        super(NovaComputeUtilsTests, self).setUp(utils, TO_PATCH)
        self.config.side_effect = self.test_config.get
        self.charm_dir.return_value = 'mycharm'
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'precise'}
        self.test_kv = TestKV()
        self.kv.return_value = self.test_kv

    @patch.object(utils, 'get_subordinate_release_packages')
    @patch.object(utils, 'nova_metadata_requirement')
    @patch.object(utils, 'network_manager')
    @patch('platform.machine')
    def test_determine_packages_nova_network(
            self, machine, net_man, en_meta,
            mock_get_subordinate_release_packages):
        self.os_release.return_value = 'icehouse'
        en_meta.return_value = (False, None)
        net_man.return_value = 'flatdhcpmanager'
        machine.return_value = 'x86_64'
        self.relation_ids.return_value = []
        mock_get_subordinate_release_packages.return_value = \
            os_utils.SubordinatePackages(set(), set())
        result = utils.determine_packages()
        ex = utils.BASE_PACKAGES + [
            'nova-api',
            'nova-network',
            'nova-compute-kvm'
        ]
        self.assertTrue(ex.sort() == result.sort())

    @patch.object(utils, 'get_subordinate_release_packages')
    @patch.object(utils, 'nova_metadata_requirement')
    def test_determine_packages_ironic(self, en_meta,
                                       mock_get_subordinate_release_packages):
        self.os_release.return_value = 'victoria'
        self.test_config.set('virt-type', 'ironic')
        en_meta.return_value = (False, None)
        self.relation_ids.return_value = []
        mock_get_subordinate_release_packages.return_value = \
            os_utils.SubordinatePackages(set(), set())
        result = utils.determine_packages()
        ex = utils.BASE_PACKAGES + [
            'nova-compute-ironic'
        ]
        self.assertTrue(ex.sort() == result.sort())

    @patch.object(utils, 'get_subordinate_release_packages')
    @patch.object(utils, 'nova_metadata_requirement')
    def test_determine_packages_ironic_pre_victoria(
            self, en_meta, mock_get_subordinate_release_packages):
        self.os_release.return_value = 'train'
        self.test_config.set('virt-type', 'ironic')
        en_meta.return_value = (False, None)
        self.relation_ids.return_value = []
        mock_get_subordinate_release_packages.return_value = \
            os_utils.SubordinatePackages(set(), set())
        result = utils.determine_packages()
        ex = utils.BASE_PACKAGES + [
            'nova-compute-vmware',
            'python3-ironicclient'
        ]
        self.assertTrue(ex.sort() == result.sort())

    @patch.object(utils, 'get_subordinate_release_packages')
    @patch.object(utils, 'nova_metadata_requirement')
    @patch.object(utils, 'network_manager')
    @patch('platform.machine')
    def test_determine_packages_nova_network_ocata(
            self, machine, net_man, en_meta,
            mock_get_subordinate_release_packages):
        self.os_release.return_value = 'ocata'
        en_meta.return_value = (False, None)
        net_man.return_value = 'flatdhcpmanager'
        machine.return_value = 'x86_64'
        self.relation_ids.return_value = []
        mock_get_subordinate_release_packages.return_value = \
            os_utils.SubordinatePackages(set(), set())
        result = utils.determine_packages()
        ex = utils.BASE_PACKAGES + [
            'nova-compute-kvm'
        ]
        self.assertTrue(ex.sort() == result.sort())

    @patch.object(utils, 'get_subordinate_release_packages')
    @patch.object(utils, 'nova_metadata_requirement')
    @patch.object(utils, 'neutron_plugin')
    @patch.object(utils, 'network_manager')
    @patch('platform.machine')
    def test_determine_packages_neutron(
            self, machine, net_man, n_plugin, en_meta,
            mock_get_subordinate_release_packages):
        self.os_release.return_value = 'ocata'
        en_meta.return_value = (False, None)
        net_man.return_value = 'neutron'
        n_plugin.return_value = 'ovs'
        machine.return_value = 'x86_64'
        self.relation_ids.return_value = []
        mock_get_subordinate_release_packages.return_value = \
            os_utils.SubordinatePackages(set(), set())
        result = utils.determine_packages()
        ex = utils.BASE_PACKAGES + ['nova-compute-kvm']
        self.assertTrue(ex.sort() == result.sort())

    @patch.object(utils, 'get_subordinate_release_packages')
    @patch.object(utils, 'nova_metadata_requirement')
    @patch.object(utils, 'neutron_plugin')
    @patch.object(utils, 'network_manager')
    @patch('platform.machine')
    def test_determine_packages_neutron_rocky(
            self, machine, net_man, n_plugin, en_meta,
            mock_get_subordinate_release_packages):
        self.os_release.return_value = 'rocky'
        en_meta.return_value = (False, None)
        net_man.return_value = 'neutron'
        n_plugin.return_value = 'ovs'
        machine.return_value = 'x86_64'
        self.relation_ids.return_value = []
        mock_get_subordinate_release_packages.return_value = \
            os_utils.SubordinatePackages(set(), set())
        result = utils.determine_packages()
        ex = (
            [p for p in utils.BASE_PACKAGES
             if not p.startswith('python-')] +
            ['nova-compute-kvm'] +
            utils.PY3_PACKAGES +
            ['python3-ceilometer', 'python3-neutron', 'python3-neutron-fwaas']
        )
        self.assertTrue(ex.sort() == result.sort())

    @patch.object(utils, 'get_subordinate_release_packages')
    @patch.object(utils, 'nova_metadata_requirement')
    @patch.object(utils, 'neutron_plugin')
    @patch.object(utils, 'network_manager')
    @patch('platform.machine')
    def test_determine_packages_neutron_aarch64_xenial(
            self, machine, net_man, n_plugin, en_meta,
            mock_get_subordinate_release_packages):
        self.os_release.return_value = 'ocata'
        self.lsb_release.return_value = {
            'DISTRIB_CODENAME': 'xenial'
        }
        en_meta.return_value = (False, None)
        net_man.return_value = 'neutron'
        n_plugin.return_value = 'ovs'
        machine.return_value = 'aarch64'
        self.relation_ids.return_value = []
        mock_get_subordinate_release_packages.return_value = \
            os_utils.SubordinatePackages(set(), set())
        result = utils.determine_packages()
        ex = utils.BASE_PACKAGES + ['nova-compute-kvm', 'qemu-efi']
        self.assertTrue(ex.sort() == result.sort())

    @patch.object(utils, 'get_subordinate_release_packages')
    @patch.object(utils, 'nova_metadata_requirement')
    @patch.object(utils, 'neutron_plugin')
    @patch.object(utils, 'network_manager')
    @patch('platform.machine')
    def test_determine_packages_neutron_aarch64_trusty(
            self, machine, net_man, n_plugin, en_meta,
            mock_get_subordinate_release_packages):
        self.os_release.return_value = 'ocata'
        self.lsb_release.return_value = {
            'DISTRIB_CODENAME': 'trusty'
        }
        en_meta.return_value = (False, None)
        net_man.return_value = 'neutron'
        n_plugin.return_value = 'ovs'
        machine.return_value = 'aarch64'
        self.relation_ids.return_value = []
        mock_get_subordinate_release_packages.return_value = \
            os_utils.SubordinatePackages(set(), set())
        result = utils.determine_packages()
        ex = utils.BASE_PACKAGES + ['nova-compute-kvm']
        self.assertTrue(ex.sort() == result.sort())

    @patch.object(utils, 'get_subordinate_release_packages')
    @patch.object(utils, 'nova_metadata_requirement')
    @patch.object(utils, 'neutron_plugin')
    @patch.object(utils, 'network_manager')
    @patch('platform.machine')
    def test_determine_packages_neutron_ceph(
            self, machine, net_man, n_plugin, en_meta,
            mock_get_subordinate_release_packages):
        self.os_release.return_value = 'ocata'
        en_meta.return_value = (False, None)
        net_man.return_value = 'neutron'
        n_plugin.return_value = 'ovs'
        machine.return_value = 'x86_64'
        self.relation_ids.return_value = ['ceph:0']
        mock_get_subordinate_release_packages.return_value = \
            os_utils.SubordinatePackages(set(), set())
        result = utils.determine_packages()
        ex = (utils.BASE_PACKAGES + ['ceph-common', 'nova-compute-kvm'])
        self.assertTrue(ex.sort() == result.sort())

    @patch.object(utils, 'get_subordinate_release_packages')
    @patch.object(utils, 'nova_metadata_requirement')
    @patch.object(utils, 'neutron_plugin')
    @patch.object(utils, 'network_manager')
    def test_determine_packages_metadata(
            self, net_man, n_plugin, en_meta,
            mock_get_subordinate_release_packages):
        self.os_release.return_value = 'ocata'
        en_meta.return_value = (True, None)
        net_man.return_value = 'bob'
        n_plugin.return_value = 'ovs'
        self.relation_ids.return_value = []
        mock_get_subordinate_release_packages.return_value = \
            os_utils.SubordinatePackages(set(), set())
        result = utils.determine_packages()
        self.assertTrue('nova-api-metadata' in result)

    @patch.object(utils, 'get_subordinate_release_packages')
    @patch.object(utils, 'nova_metadata_requirement')
    @patch.object(utils, 'neutron_plugin')
    @patch.object(utils, 'network_manager')
    def test_determine_packages_use_multipath(
            self, net_man, n_plugin, en_meta,
            mock_get_subordinate_release_packages):
        self.os_release.return_value = 'ocata'
        en_meta.return_value = (False, None)
        net_man.return_value = 'bob'
        self.test_config.set('use-multipath', True)
        self.relation_ids.return_value = []
        mock_get_subordinate_release_packages.return_value = \
            os_utils.SubordinatePackages(set(), set())
        result = utils.determine_packages()
        for pkg in utils.MULTIPATH_PACKAGES:
            self.assertTrue(pkg in result)

    @patch.object(utils, 'get_subordinate_release_packages')
    @patch.object(utils, 'nova_metadata_requirement')
    @patch.object(utils, 'neutron_plugin')
    @patch.object(utils, 'network_manager')
    def test_determine_packages_no_multipath(
            self, net_man, n_plugin, en_meta,
            mock_get_subordinate_release_packages):
        self.os_release.return_value = 'ocata'
        en_meta.return_value = (False, None)
        net_man.return_value = 'bob'
        self.test_config.set('use-multipath', False)
        self.relation_ids.return_value = []
        mock_get_subordinate_release_packages.return_value = \
            os_utils.SubordinatePackages(set(), set())
        result = utils.determine_packages()
        for pkg in utils.MULTIPATH_PACKAGES:
            self.assertFalse(pkg in result)

    @patch.object(utils, 'os')
    @patch.object(utils, 'nova_metadata_requirement')
    @patch.object(utils, 'network_manager')
    def test_resource_map_nova_network_no_multihost(self, net_man, en_meta,
                                                    _os):
        self.os_release.return_value = 'icehouse'
        self.test_config.set('multi-host', 'no')
        en_meta.return_value = (False, None)
        net_man.return_value = 'flatdhcpmanager'
        _os.path.exists.return_value = True
        result = utils.resource_map()
        ex = {
            '/etc/default/libvirt-bin': {
                'contexts': [],
                'services': ['libvirt-bin']
            },
            '/etc/libvirt/qemu.conf': {
                'contexts': [],
                'services': ['libvirt-bin']
            },
            '/etc/nova/nova.conf': {
                'contexts': [],
                'services': ['nova-compute']
            },
            '/etc/nova/vendor_data.json': {
                'contexts': [],
                'services': []
            },
            '/etc/ceph/secret.xml': {
                'contexts': [],
                'services': []
            },
            '/var/lib/charm/nova_compute/ceph.conf': {
                'contexts': [],
                'services': ['nova-compute']
            },
            '/etc/default/qemu-kvm': {
                'contexts': [],
                'services': ['qemu-kvm']
            },
            '/etc/init/libvirt-bin.override': {
                'contexts': [],
                'services': ['libvirt-bin']
            },
            '/etc/libvirt/libvirtd.conf': {
                'contexts': [],
                'services': ['libvirt-bin']
            },
            '/etc/apparmor.d/usr.bin.nova-compute': {
                'contexts': [],
                'services': ['nova-compute']
            },
        }
        # Mocking contexts is tricky but we can still test that
        # the correct files are monitored and the correct services
        # will be started
        self.assertEqual(set(ex.keys()), set(result.keys()))
        for k in ex.keys():
            self.assertEqual(set(ex[k]['services']),
                             set(result[k]['services']))

    @patch.object(utils, 'os')
    @patch.object(utils, 'nova_metadata_requirement')
    @patch.object(utils, 'network_manager')
    def test_resource_map_nova_network_ocata(self, net_man, en_meta, _os):
        self.os_release.return_value = 'ocata'
        self.test_config.set('multi-host', 'yes')
        en_meta.return_value = (False, None)
        net_man.return_value = 'flatdhcpmanager'
        _os.path.exists.return_value = False
        result = utils.resource_map()
        ex = {
            '/etc/default/libvirt-bin': {
                'contexts': [],
                'services': ['libvirtd']
            },
            '/etc/libvirt/qemu.conf': {
                'contexts': [],
                'services': ['libvirtd']
            },
            '/etc/nova/nova.conf': {
                'contexts': [],
                'services': ['nova-compute']
            },
            '/etc/nova/vendor_data.json': {
                'contexts': [],
                'services': []
            },
            '/etc/ceph/secret.xml': {
                'contexts': [],
                'services': []
            },
            '/var/lib/charm/nova_compute/ceph.conf': {
                'contexts': [],
                'services': ['nova-compute']
            },
            '/etc/default/qemu-kvm': {
                'contexts': [],
                'services': ['qemu-kvm']
            },
            '/etc/libvirt/libvirtd.conf': {
                'contexts': [],
                'services': ['libvirtd']
            },
            '/etc/apparmor.d/usr.bin.nova-compute': {
                'contexts': [],
                'services': ['nova-compute']
            },
        }
        # Mocking contexts is tricky but we can still test that
        # the correct files are monitored and the correct services
        # will be started
        self.assertEqual(set(ex.keys()), set(result.keys()))
        for k in ex.keys():
            self.assertEqual(set(ex[k]['services']),
                             set(result[k]['services']))

    @patch.object(utils, 'os')
    @patch.object(utils, 'nova_metadata_requirement')
    @patch.object(utils, 'network_manager')
    def test_resource_map_nova_network(self, net_man, en_meta, _os):

        self.os_release.return_value = 'icehouse'
        en_meta.return_value = (False, None)
        self.test_config.set('multi-host', 'yes')
        net_man.return_value = 'flatdhcpmanager'
        _os.path.exists.return_value = True
        result = utils.resource_map()

        ex = {
            '/etc/default/libvirt-bin': {
                'contexts': [],
                'services': ['libvirt-bin']
            },
            '/etc/libvirt/qemu.conf': {
                'contexts': [],
                'services': ['libvirt-bin']
            },
            '/etc/nova/nova.conf': {
                'contexts': [],
                'services': ['nova-compute', 'nova-api', 'nova-network']
            },
            '/etc/nova/vendor_data.json': {
                'contexts': [],
                'services': []
            },
            '/etc/ceph/secret.xml': {
                'contexts': [],
                'services': []
            },
            '/var/lib/charm/nova_compute/ceph.conf': {
                'contexts': [],
                'services': ['nova-compute']
            },
            '/etc/default/qemu-kvm': {
                'contexts': [],
                'services': ['qemu-kvm']
            },
            '/etc/init/libvirt-bin.override': {
                'contexts': [],
                'services': ['libvirt-bin']
            },
            '/etc/libvirt/libvirtd.conf': {
                'contexts': [],
                'services': ['libvirt-bin']
            },
            '/etc/apparmor.d/usr.bin.nova-network': {
                'contexts': [],
                'services': ['nova-network']
            },
            '/etc/apparmor.d/usr.bin.nova-compute': {
                'contexts': [],
                'services': ['nova-compute']
            },
            '/etc/apparmor.d/usr.bin.nova-api': {
                'contexts': [],
                'services': ['nova-api']
            },

        }
        # Mocking contexts is tricky but we can still test that
        # the correct files are monitored and the correct services
        # will be started
        self.assertEqual(set(ex.keys()), set(result.keys()))
        for k in ex.keys():
            self.assertEqual(set(ex[k]['services']),
                             set(result[k]['services']))

    def _test_resource_map_neutron(self, net_man, en_meta,
                                   libvirt_daemon):
        en_meta.return_value = (False, None)
        self.test_config.set('multi-host', 'yes')
        net_man.return_value = 'neutron'
        result = utils.resource_map()

        ex = {
            '/etc/default/libvirt-bin': {
                'contexts': [],
                'services': [libvirt_daemon]
            },
            '/etc/libvirt/qemu.conf': {
                'contexts': [],
                'services': [libvirt_daemon]
            },
            '/etc/nova/nova.conf': {
                'contexts': [],
                'services': ['nova-compute']
            },
            '/etc/nova/vendor_data.json': {
                'contexts': [],
                'services': []
            },
            '/etc/ceph/secret.xml': {
                'contexts': [],
                'services': []
            },
            '/var/lib/charm/nova_compute/ceph.conf': {
                'contexts': [],
                'services': ['nova-compute']
            },
            '/etc/default/qemu-kvm': {
                'contexts': [],
                'services': ['qemu-kvm']
            },
            '/etc/init/libvirt-bin.override': {
                'contexts': [],
                'services': [libvirt_daemon]
            },
            '/etc/libvirt/libvirtd.conf': {
                'contexts': [],
                'services': [libvirt_daemon]
            },
            '/etc/apparmor.d/usr.bin.nova-compute': {
                'contexts': [],
                'services': ['nova-compute']
            },
        }
        # Mocking contexts is tricky but we can still test that
        # the correct files are monitored and the correct services
        # will be started
        self.assertEqual(set(ex.keys()), set(result.keys()))
        for k in ex.keys():
            self.assertEqual(set(ex[k]['services']),
                             set(result[k]['services']))

    @patch.object(utils.os.path, 'exists')
    @patch.object(utils, 'nova_metadata_requirement')
    @patch.object(utils, 'network_manager')
    def test_resource_map_neutron(self, net_man, en_meta, exists):
        exists.return_value = True
        self.os_release.return_value = 'diablo'
        self._test_resource_map_neutron(net_man, en_meta, 'libvirt-bin')

    @patch.object(utils.os.path, 'exists')
    @patch.object(utils, 'nova_metadata_requirement')
    @patch.object(utils, 'network_manager')
    def test_resource_map_neutron_yakkety(self, net_man, en_meta, exists):
        exists.return_value = True
        self.lsb_release.return_value = {'DISTRIB_CODENAME': 'yakkety'}
        self.os_release.return_value = 'diablo'
        self._test_resource_map_neutron(net_man, en_meta, 'libvirtd')

    @patch.object(utils, 'nova_metadata_requirement')
    @patch.object(utils, 'neutron_plugin')
    @patch.object(utils, 'network_manager')
    def test_resource_map_metadata(self, net_man, _plugin, _metadata):
        _metadata.return_value = (True, None)
        net_man.return_value = 'bob'
        _plugin.return_value = 'ovs'
        self.relation_ids.return_value = []
        self.os_release.return_value = 'diablo'
        result = utils.resource_map()['/etc/nova/nova.conf']['services']
        self.assertTrue('nova-api-metadata' in result)

    @patch.object(utils, 'nova_metadata_requirement')
    def test_resource_map_ironic_pre_victoria(self, _metadata):
        _metadata.return_value = (True, None)
        self.relation_ids.return_value = []
        self.os_release.return_value = 'train'
        self.test_config.set('virt-type', 'ironic')
        result = utils.resource_map()
        self.assertTrue(utils.NOVA_COMPUTE_CONF in result)
        self.assertEqual(
            result[utils.NOVA_COMPUTE_CONF]["services"], ["nova-compute"])
        self.assertEqual(
            result[utils.NOVA_COMPUTE_CONF]["contexts"], [])

    @patch.object(utils, 'nova_metadata_requirement')
    def test_resource_map_ironic(self, _metadata):
        _metadata.return_value = (True, None)
        self.relation_ids.return_value = []
        self.os_release.return_value = 'victoria'
        self.test_config.set('virt-type', 'ironic')
        result = utils.resource_map()
        self.assertTrue(utils.NOVA_COMPUTE_CONF not in result)

    def fake_user(self, username='foo'):
        user = MagicMock()
        user.pw_dir = '/home/' + username
        return user

    @patch('builtins.open')
    @patch('pwd.getpwnam')
    def test_public_ssh_key_not_found(self, getpwnam, _open):
        _open.side_effect = OSError
        getpwnam.return_value = self.fake_user('foo')
        self.assertEqual(None, utils.public_ssh_key())

    @patch('pwd.getpwnam')
    def test_public_ssh_key(self, getpwnam):
        getpwnam.return_value = self.fake_user('foo')
        with patch_open() as (_open, _file):
            _file.read.return_value = 'mypubkey'
            result = utils.public_ssh_key('foo')
        self.assertEqual(result, 'mypubkey')

    def test_import_authorized_keys_missing_data(self):
        self.relation_get.return_value = None
        with patch_open() as (_open, _file):
            utils.import_authorized_keys(user='foo')
            self.assertFalse(_open.called)

    @patch('pwd.getpwnam')
    def _test_import_authorized_keys_base(self, getpwnam, prefix=None,
                                          auth_key_path='/home/foo/.ssh/'
                                                        'authorized_keys'):
        getpwnam.return_value = self.fake_user('foo')

        d = {
            'known_hosts_max_index': 3,
            'known_hosts_0': 'k_h_0',
            'known_hosts_1': 'k_h_1',
            'known_hosts_2': 'k_h_2',
            'authorized_keys_max_index': 3,
            'authorized_keys_0': 'auth_0',
            'authorized_keys_1': 'auth_1',
            'authorized_keys_2': 'auth_2',
        }
        if prefix:
            for k, v in d.copy().items():
                d["{}_{}".format(prefix, k)] = v

        def _relation_get(scope=None, *args, **kwargs):
            if scope is not None:
                return d.get(scope, None)
            return d

        self.relation_get.side_effect = _relation_get

        ex_open = [
            call('/home/foo/.ssh/known_hosts', 'wt'),
            call(auth_key_path, 'wt')
        ]
        ex_write = [
            call('k_h_0\n'),
            call('k_h_1\n'),
            call('k_h_2\n'),
            call('auth_0\n'),
            call('auth_1\n'),
            call('auth_2\n')
        ]

        # we only have to verify that the files are written as expected as this
        # implicitly checks that the relation_get calls have occurred.
        with patch_open() as (_open, _file):
            utils.import_authorized_keys(user='foo', prefix=prefix)
            self.assertEqual(ex_open, _open.call_args_list)
            self.assertEqual(ex_write, _file.write.call_args_list)

    def test_import_authorized_keys_noprefix(self):
        self._test_import_authorized_keys_base()

    def test_import_authorized_keys_prefix(self):
        self._test_import_authorized_keys_base(prefix='bar')

    def test_import_authorized_keys_authkeypath(self):
        nonstandard_path = '/etc/ssh/user-authorized-keys/{username}'
        self.test_config.set('authorized-keys-path', nonstandard_path)
        self._test_import_authorized_keys_base(
            auth_key_path='/etc/ssh/user-authorized-keys/foo')

    @patch('subprocess.check_call')
    def test_import_keystone_cert_missing_data(self, check_call):
        self.relation_get.return_value = None
        with patch_open() as (_open, _file):
            utils.import_keystone_ca_cert()
            self.assertFalse(_open.called)
        self.assertFalse(check_call.called)

    @patch.object(utils, 'check_call')
    def test_import_keystone_cert(self, check_call):
        self.relation_get.return_value = 'Zm9vX2NlcnQK'
        with patch_open() as (_open, _file):
            utils.import_keystone_ca_cert()
            _open.assert_called_with(utils.CA_CERT_PATH, 'wb')
            _file.write.assert_called_with(b'foo_cert\n')
        check_call.assert_called_with(['update-ca-certificates'])

    @patch.object(utils, 'ceph_config_file')
    @patch('charmhelpers.contrib.openstack.templating.OSConfigRenderer')
    @patch.object(utils, 'resource_map')
    def test_register_configs(self, resource_map, renderer,
                              mock_ceph_config_file):
        self.os_release.return_value = 'havana'
        fake_renderer = MagicMock()
        fake_renderer.register = MagicMock()
        renderer.return_value = fake_renderer
        ctxt1 = MagicMock()
        ctxt2 = MagicMock()
        rsc_map = {
            '/etc/nova/nova.conf': {
                'services': ['nova-compute'],
                'contexts': [ctxt1],
            },
            '/etc/nova/nova-compute.conf': {
                'services': ['nova-compute'],
                'contexts': [ctxt2],
            },
        }
        resource_map.return_value = rsc_map
        with tempfile.NamedTemporaryFile() as tmpfile:
            mock_ceph_config_file.return_value = tmpfile.name
            utils.register_configs()
            renderer.assert_called_with(
                openstack_release='havana', templates_dir='templates/')
            ex_reg = [
                call('/etc/nova/nova.conf', [ctxt1]),
                call('/etc/nova/nova-compute.conf', [ctxt2]),
            ]
            fake_renderer.register.assert_has_calls(ex_reg, any_order=True)

    @patch.object(utils, 'check_call')
    def test_enable_shell(self, _check_call):
        utils.enable_shell('dummy')
        _check_call.assert_called_with(['usermod', '-s', '/bin/bash', 'dummy'])

    @patch.object(utils, 'check_call')
    def test_disable_shell(self, _check_call):
        utils.disable_shell('dummy')
        _check_call.assert_called_with(['usermod', '-s', '/bin/false',
                                        'dummy'])

    @patch.object(utils, 'check_call')
    def test_configure_subuid(self, _check_call):
        utils.configure_subuid('dummy')
        _check_call.assert_called_with(['usermod', '-v', '100000-200000',
                                        '-w', '100000-200000', 'dummy'])

    @patch.object(utils, 'check_call')
    @patch.object(utils, 'check_output')
    def test_create_libvirt_key(self, _check_output, _check_call):
        key = 'AQCR2dRUaFQSOxAAC5fr79sLL3d7wVvpbbRFMg=='
        self.test_config.set('virt-type', 'kvm')
        utils.create_libvirt_secret(utils.CEPH_SECRET,
                                    compute_context.CEPH_SECRET_UUID, key)
        _check_output.assert_called_with(['virsh', '-c',
                                          utils.LIBVIRT_URIS['kvm'],
                                          'secret-list'])
        _check_call.assert_called_with(['virsh', '-c',
                                        utils.LIBVIRT_URIS['kvm'],
                                        'secret-set-value', '--secret',
                                        compute_context.CEPH_SECRET_UUID,
                                        '--base64', key])

    @patch.object(utils, 'check_call')
    @patch.object(utils, 'check_output')
    def test_create_libvirt_key_existing(self, _check_output, _check_call):
        key = 'AQCR2dRUaFQSOxAAC5fr79sLL3d7wVvpbbRFMg=='
        old_key = 'AQCR2dRUaFQSOxAAC5fr79sLL3d7wVvpbbRFMg==\n'
        self.test_config.set('virt-type', 'kvm')
        _check_output.side_effect = [
            compute_context.CEPH_SECRET_UUID.encode(),
            old_key.encode()]
        utils.create_libvirt_secret(utils.CEPH_SECRET,
                                    compute_context.CEPH_SECRET_UUID, key)
        expected = [call(['virsh', '-c',
                          utils.LIBVIRT_URIS['kvm'], 'secret-list']),
                    call(['virsh', '-c',
                          utils.LIBVIRT_URIS['kvm'], 'secret-get-value',
                          compute_context.CEPH_SECRET_UUID])]
        _check_output.assert_has_calls(expected)
        self.assertFalse(_check_call.called)

    @patch.object(utils, 'check_call')
    @patch.object(utils, 'check_output')
    def test_create_libvirt_key_stale(self, _check_output, _check_call):
        key = 'AQCR2dRUaFQSOxAAC5fr79sLL3d7wVvpbbRFMg=='
        old_key = 'CCCCCdRUaFQSOxAAC5fr79sLL3d7wVvpbbRFMg=='
        self.test_config.set('virt-type', 'kvm')
        _check_output.side_effect = [
            compute_context.CEPH_SECRET_UUID.encode(),
            old_key.encode()]
        utils.create_libvirt_secret(utils.CEPH_SECRET,
                                    compute_context.CEPH_SECRET_UUID, key)
        expected = [call(['virsh', '-c',
                          utils.LIBVIRT_URIS['kvm'], 'secret-list']),
                    call(['virsh', '-c',
                          utils.LIBVIRT_URIS['kvm'], 'secret-get-value',
                          compute_context.CEPH_SECRET_UUID])]
        _check_output.assert_has_calls(expected)
        _check_call.assert_any_call(['virsh', '-c',
                                     utils.LIBVIRT_URIS['kvm'],
                                     'secret-set-value', '--secret',
                                     compute_context.CEPH_SECRET_UUID,
                                     '--base64', key])

    @patch.object(utils, 'lxc_list')
    @patch.object(utils, 'configure_subuid')
    def test_configure_lxd_vivid(self, _configure_subuid, _lxc_list):
        self.lsb_release.return_value = {
            'DISTRIB_CODENAME': 'vivid'
        }
        utils.configure_lxd('nova')
        _configure_subuid.assert_called_with('nova')
        _lxc_list.assert_called_with('nova')

    @patch.object(utils, 'lxc_list')
    @patch.object(utils, 'configure_subuid')
    def test_configure_lxd_pre_vivid(self, _configure_subuid, _lxc_list):
        self.lsb_release.return_value = {
            'DISTRIB_CODENAME': 'trusty'
        }
        with self.assertRaises(Exception):
            utils.configure_lxd('nova')
        self.assertFalse(_configure_subuid.called)

    @patch('psutil.virtual_memory')
    @patch('subprocess.check_call')
    @patch('subprocess.call')
    def test_install_hugepages(self, _call, _check_call, _virt_mem):
        class mem(object):
            def __init__(self):
                self.total = 10000000 * 1024
        self.test_config.set('hugepages', '10%')
        _virt_mem.side_effect = mem
        _call.return_value = 1
        utils.install_hugepages()
        self.hugepage_support.assert_called_with(
            'nova',
            mnt_point='/run/hugepages/kvm',
            group='root',
            nr_hugepages=488,
            mount=False,
            set_shmmax=True,
        )
        check_call_calls = [
            call('/etc/init.d/qemu-hugefsdir'),
            call(['update-rc.d', 'qemu-hugefsdir', 'defaults']),
        ]
        _check_call.assert_has_calls(check_call_calls)
        self.Fstab.remove_by_mountpoint.assert_called_with(
            '/run/hugepages/kvm')

    @patch('psutil.virtual_memory')
    @patch('subprocess.check_call')
    @patch('subprocess.call')
    def test_install_hugepages_explicit_size(self, _call, _check_call,
                                             _virt_mem):
        self.test_config.set('hugepages', '2048')
        utils.install_hugepages()
        self.hugepage_support.assert_called_with(
            'nova',
            mnt_point='/run/hugepages/kvm',
            group='root',
            nr_hugepages=2048,
            mount=False,
            set_shmmax=True,
        )

    @patch.object(utils, 'is_unit_paused_set')
    @patch.object(utils, 'services')
    def test_assess_status(self, services, mock_is_paused):
        services.return_value = 's1'
        mock_is_paused.return_value = False
        with patch.object(utils, 'assess_status_func') as asf:
            callee = MagicMock()
            asf.return_value = callee
            utils.assess_status('test-config')
            asf.assert_called_once_with('test-config', 's1')
            callee.assert_called_once_with()
            self.os_application_version_set.assert_called_with(
                utils.VERSION_PACKAGE
            )

    @patch.object(utils, 'os_release')
    @patch.object(utils, 'is_unit_paused_set')
    @patch.object(utils, 'services')
    def test_assess_status_paused(self, services, mock_is_paused,
                                  mock_os_release):
        services.return_value = ['qemu-kvm', 'libvirtd', 'nova-compute']
        mock_is_paused.return_value = True
        mock_os_release.return_value = 'pike'
        with patch.object(utils, 'assess_status_func') as asf:
            callee = MagicMock()
            asf.return_value = callee
            utils.assess_status('test-config')
            asf.assert_called_once_with('test-config',
                                        ['qemu-kvm', 'nova-compute'])
            callee.assert_called_once_with()
            self.os_application_version_set.assert_called_with(
                utils.VERSION_PACKAGE
            )

    @patch.object(utils, 'REQUIRED_INTERFACES')
    @patch.object(utils, 'services')
    @patch.object(utils, 'make_assess_status_func')
    @patch.object(utils, 'get_optional_relations')
    def test_assess_status_func(self,
                                get_optional_relations,
                                make_assess_status_func,
                                services,
                                REQUIRED_INTERFACES):
        services.return_value = ['s1']
        REQUIRED_INTERFACES.copy.return_value = {'test-interface': True}
        get_optional_relations.return_value = {'optional': False}
        test_interfaces = {
            'test-interface': True,
            'optional': False,
        }
        utils.assess_status_func('test-config')
        # ports=None whilst port checks are disabled.
        make_assess_status_func.assert_called_once_with(
            'test-config', test_interfaces,
            charm_func=utils.check_optional_config_and_relations,
            services=['s1'], ports=None)

    def test_pause_unit_helper(self):
        with patch.object(utils, '_pause_resume_helper') as prh:
            utils.pause_unit_helper('random-config')
            prh.assert_called_once_with(utils.pause_unit, 'random-config')
        with patch.object(utils, '_pause_resume_helper') as prh:
            utils.resume_unit_helper('random-config')
            prh.assert_called_once_with(utils.resume_unit, 'random-config')

    @patch.object(utils, 'os_release')
    @patch.object(utils, 'is_unit_paused_set')
    @patch.object(utils, 'services')
    def test_pause_resume_helper(self, services, mock_is_paused,
                                 mock_os_release):
        f = MagicMock()
        services.return_value = ['s1']
        mock_is_paused.return_value = False
        mock_os_release.return_value = 'queens'
        with patch.object(utils, 'assess_status_func') as asf:
            asf.return_value = 'assessor'
            utils._pause_resume_helper(f, 'some-config')
            asf.assert_called_once_with('some-config', ['s1'])
            # ports=None whilst port checks are disabled.
            f.assert_called_once_with('assessor', services=['s1'], ports=None)

    @patch.object(utils, 'check_call')
    @patch.object(utils, 'check_output')
    def test_remove_libvirt_network(self, mock_check_output, mock_check_call):
        mock_check_output.return_value = VIRSH_NET_LIST.encode()
        utils.remove_libvirt_network('default')
        cmd = ['virsh', 'net-destroy', 'default']
        mock_check_call.assert_has_calls([call(cmd)])

    @patch.object(utils, 'check_call')
    @patch.object(utils, 'check_output')
    def test_remove_libvirt_network_no_exist(self, mock_check_output,
                                             mock_check_call):
        mock_check_output.return_value = VIRSH_NET_LIST.encode()
        utils.remove_libvirt_network('defaultX')
        self.assertFalse(mock_check_call.called)

    @patch.object(utils, 'check_call')
    @patch.object(utils, 'check_output')
    def test_remove_libvirt_network_no_virsh(self, mock_check_output,
                                             mock_check_call):
        mock_check_output.side_effect = OSError(2, 'No such file')
        utils.remove_libvirt_network('default')

    @patch.object(utils, 'check_call')
    @patch.object(utils, 'check_output')
    def test_remove_libvirt_network_no_virsh_unknown_error(self,
                                                           mock_check_output,
                                                           mock_check_call):
        mock_check_output.side_effect = OSError(100, 'Break things')
        with self.assertRaises(OSError):
            utils.remove_libvirt_network('default')

    def test_libvirt_daemon_yakkety(self):
        self.lsb_release.return_value = {
            'DISTRIB_CODENAME': 'yakkety'
        }
        self.assertEqual(utils.libvirt_daemon(), utils.LIBVIRTD_DAEMON)

    def test_libvirt_daemon_preyakkety(self):
        self.os_release.return_value = 'diablo'
        self.lsb_release.return_value = {
            'DISTRIB_CODENAME': 'xenial'
        }
        self.assertEqual(utils.libvirt_daemon(), utils.LIBVIRT_BIN_DAEMON)

    @patch.object(utils, 'os')
    def test_determine_block_device(self, mock_os):
        self.test_config.set('ephemeral-device', '/dev/sdd')
        mock_os.path.exists.return_value = True
        self.assertEqual(utils.determine_block_device(), '/dev/sdd')
        self.config.assert_called_with('ephemeral-device')

    def test_determine_block_device_storage(self):
        _test_devices = {
            'a': '/dev/bcache0'
        }
        self.storage_list.side_effect = _test_devices.keys()
        self.storage_get.side_effect = lambda _, key: _test_devices.get(key)
        self.assertEqual(utils.determine_block_device(), '/dev/bcache0')
        self.config.assert_called_with('ephemeral-device')
        self.storage_get.assert_called_with('location', 'a')
        self.storage_list.assert_called_with('ephemeral-device')

    def test_determine_block_device_none(self):
        self.storage_list.return_value = []
        self.assertEqual(utils.determine_block_device(), None)
        self.config.assert_called_with('ephemeral-device')
        self.storage_list.assert_called_with('ephemeral-device')

    @patch.object(utils, 'install_mount_override')
    @patch.object(utils, 'filter_installed_packages')
    @patch.object(utils, 'uuid')
    @patch.object(utils, 'determine_block_device')
    def test_configure_local_ephemeral_storage_encrypted(
            self,
            determine_block_device,
            uuid,
            filter_installed_packages,
            install_mount_override):
        filter_installed_packages.return_value = []
        determine_block_device.return_value = '/dev/sdb'
        uuid.uuid4.return_value = 'test'

        mock_context = MagicMock()
        mock_context.complete = True
        mock_context.return_value = 'test_context'

        self.test_config.set('encrypt', True)
        self.vaultlocker.VaultKVContext.return_value = mock_context
        self.is_block_device.return_value = True
        self.is_device_mounted.return_value = False

        utils.configure_local_ephemeral_storage()

        self.mkfs_xfs.assert_called_with(
            '/dev/mapper/crypt-test',
            force=True
        )
        self.check_call.assert_has_calls([
            call(['vaultlocker', 'encrypt',
                  '--uuid', 'test', '/dev/sdb']),
            call(['chown', '-R', 'nova:nova',
                  '/var/lib/nova/instances']),
            call(['chmod', '-R', '0755',
                  '/var/lib/nova/instances'])
        ])
        self.mount.assert_called_with(
            '/dev/mapper/crypt-test',
            '/var/lib/nova/instances',
            filesystem='xfs')
        self.fstab_add.assert_called_with(
            '/dev/mapper/crypt-test',
            '/var/lib/nova/instances',
            'xfs',
            options='defaults,nofail,'
            'x-systemd.requires=vaultlocker-decrypt@test.service,'
            'comment=vaultlocker'
        )
        install_mount_override.assert_called_with(
            '/var/lib/nova/instances'
        )
        self.assertTrue(self.test_kv.get('storage-configured'))
        self.vaultlocker.write_vaultlocker_conf.assert_called_with(
            'test_context',
            priority=80
        )

    @patch.object(utils, 'install_mount_override')
    @patch.object(utils, 'uuid')
    @patch.object(utils, 'determine_block_device')
    def test_configure_local_ephemeral_storage(self,
                                               determine_block_device,
                                               uuid,
                                               install_mount_override):
        determine_block_device.return_value = '/dev/sdb'
        uuid.uuid4.return_value = 'test'

        mock_context = MagicMock()
        mock_context.complete = False
        mock_context.return_value = {}

        self.test_config.set('encrypt', False)
        self.vaultlocker.VaultKVContext.return_value = mock_context
        self.is_block_device.return_value = True
        self.is_device_mounted.return_value = False

        utils.configure_local_ephemeral_storage()

        self.mkfs_xfs.assert_called_with(
            '/dev/sdb',
            force=True
        )
        self.check_call.assert_has_calls([
            call(['chown', '-R', 'nova:nova',
                  '/var/lib/nova/instances']),
            call(['chmod', '-R', '0755',
                  '/var/lib/nova/instances'])
        ])
        self.mount.assert_called_with(
            '/dev/sdb',
            '/var/lib/nova/instances',
            filesystem='xfs')
        self.fstab_add.assert_called_with(
            '/dev/sdb',
            '/var/lib/nova/instances',
            'xfs',
            options=None
        )
        install_mount_override.assert_called_with(
            '/var/lib/nova/instances'
        )
        self.assertTrue(self.test_kv.get('storage-configured'))
        self.vaultlocker.write_vaultlocker_conf.assert_not_called()

    @patch.object(utils, 'install_mount_override')
    @patch.object(utils, 'uuid')
    @patch.object(utils, 'determine_block_device')
    def test_configure_local_ephemeral_storage_ip_set(self,
                                                      determine_block_device,
                                                      uuid,
                                                      install_mount_override):
        determine_block_device.return_value = '/dev/sdb'
        uuid.uuid4.return_value = 'test'

        mock_context = MagicMock()
        mock_context.complete = False
        mock_context.return_value = {}

        self.test_config.set('encrypt', False)
        self.test_config.set('instances-path', '/srv/instances')
        self.vaultlocker.VaultKVContext.return_value = mock_context
        self.is_block_device.return_value = True
        self.is_device_mounted.return_value = False

        utils.configure_local_ephemeral_storage()

        self.mkfs_xfs.assert_called_with(
            '/dev/sdb',
            force=True
        )
        self.check_call.assert_has_calls([
            call(['chown', '-R', 'nova:nova',
                  '/srv/instances']),
            call(['chmod', '-R', '0755',
                  '/srv/instances'])
        ])
        self.mount.assert_called_with(
            '/dev/sdb',
            '/srv/instances',
            filesystem='xfs')
        self.fstab_add.assert_called_with(
            '/dev/sdb',
            '/srv/instances',
            'xfs',
            options=None
        )
        install_mount_override.assert_called_with(
            '/srv/instances'
        )
        self.assertTrue(self.test_kv.get('storage-configured'))
        self.vaultlocker.write_vaultlocker_conf.assert_not_called()

    @patch.object(utils, 'install_mount_override')
    @patch.object(utils, 'filter_installed_packages')
    def test_configure_local_ephemeral_storage_done(self,
                                                    filter_installed_packages,
                                                    install_mount_override):
        filter_installed_packages.return_value = []
        self.test_kv.set('storage-configured', True)

        mock_context = MagicMock()
        mock_context.complete = True
        mock_context.return_value = 'test_context'

        self.test_config.set('encrypt', True)
        self.vaultlocker.VaultKVContext.return_value = mock_context

        utils.configure_local_ephemeral_storage()

        # NOTE: vaultlocker conf should always be re-written to
        #       pickup any changes to secret_id over time.
        self.vaultlocker.write_vaultlocker_conf.assert_called_with(
            'test_context',
            priority=80
        )
        self.is_block_device.assert_not_called()
        # NOTE: called to deal with charm upgrades
        install_mount_override.assert_called_with(
            '/var/lib/nova/instances'
        )

    @patch.object(utils.os.environ, 'get')
    def test_get_az_customize_with_env(self, os_environ_get_mock):
        self.test_config.set('customize-failure-domain', True)
        self.test_config.set('default-availability-zone', 'nova')

        def os_environ_get_side_effect(key):
            return {
                'JUJU_AVAILABILITY_ZONE': 'az1',
            }[key]
        os_environ_get_mock.side_effect = os_environ_get_side_effect
        az = utils.get_availability_zone()
        self.assertEqual('az1', az)

    @patch.object(utils.os.environ, 'get')
    def test_get_az_customize_without_env(self, os_environ_get_mock):
        self.test_config.set('customize-failure-domain', True)
        self.test_config.set('default-availability-zone', 'mynova')

        def os_environ_get_side_effect(key):
            return {
                'JUJU_AVAILABILITY_ZONE': '',
            }[key]
        os_environ_get_mock.side_effect = os_environ_get_side_effect
        az = utils.get_availability_zone()
        self.assertEqual('mynova', az)

    @patch.object(utils.os.environ, 'get')
    def test_get_az_no_customize_without_env(self, os_environ_get_mock):
        self.test_config.set('customize-failure-domain', False)
        self.test_config.set('default-availability-zone', 'nova')

        def os_environ_get_side_effect(key):
            return {
                'JUJU_AVAILABILITY_ZONE': '',
            }[key]
        os_environ_get_mock.side_effect = os_environ_get_side_effect
        az = utils.get_availability_zone()
        self.assertEqual('nova', az)

    @patch.object(utils.os.environ, 'get')
    def test_get_az_no_customize_with_env(self, os_environ_get_mock):
        self.test_config.set('customize-failure-domain', False)
        self.test_config.set('default-availability-zone', 'nova')

        def os_environ_get_side_effect(key):
            return {
                'JUJU_AVAILABILITY_ZONE': 'az1',
            }[key]
        os_environ_get_mock.side_effect = os_environ_get_side_effect
        az = utils.get_availability_zone()
        self.assertEqual('nova', az)

    @patch.object(utils, "libvirt_daemon")
    @patch.object(utils, "hook_name")
    @patch.object(utils, "get_subordinate_services")
    @patch.object(utils, 'nova_metadata_requirement')
    def test_services_to_pause_or_resume(
            self, _en_meta, _subordinate_services, _hook_name,
            _libvirt_daemon):
        _en_meta.return_value = (False, None)
        _subordinate_services.return_value = set(["ceilometer-agent-compute"])
        _libvirt_daemon.return_value = "libvirtd"

        self.os_release.return_value = 'victoria'
        self.relation_ids.return_value = []

        # WARNING(lourot): In the following test expectations, the order of
        # the services is important. Principal services have to come before
        # the subordinate services. See nova_compute_utils.services() for more
        # details.
        expected_last_service = "ceilometer-agent-compute"

        _hook_name.return_value = "config-changed"
        expected_service_set = set(["qemu-kvm", "nova-compute",
                                    "ceilometer-agent-compute"])
        actual_service_list = utils.services_to_pause_or_resume()
        self.assertEqual(expected_service_set, set(actual_service_list))
        self.assertEqual(expected_last_service, actual_service_list[-1])

        _hook_name.return_value = "post-series-upgrade"
        expected_service_set = set(["qemu-kvm", "nova-compute", "libvirtd",
                                    "ceilometer-agent-compute"])
        actual_service_list = utils.services_to_pause_or_resume()
        self.assertEqual(expected_service_set, set(actual_service_list))
        self.assertEqual(expected_last_service, actual_service_list[-1])

    @patch.object(utils, 'kv')
    def test_use_fqdn_hint(self, _kv):
        _kv().get.return_value = False
        self.assertEquals(utils.use_fqdn_hint(), False)
        _kv().get.return_value = True
        self.assertEquals(utils.use_fqdn_hint(), True)

    @patch.object(utils, 'render')
    def test_install_mount_override(self, render):
        utils.install_mount_override('/srv/test')
        render.assert_called_once_with(
            utils.MOUNT_DEPENDENCY_OVERRIDE,
            os.path.join(utils.NOVA_COMPUTE_OVERRIDE_DIR,
                         utils.MOUNT_DEPENDENCY_OVERRIDE),
            {'mount_point': 'srv-test'},
            perms=0o644,
        )
