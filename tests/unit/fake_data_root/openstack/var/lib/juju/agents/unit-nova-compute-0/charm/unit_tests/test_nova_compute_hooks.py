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

import importlib
import json

from unittest.mock import (
    ANY,
    call,
    patch,
    MagicMock
)

from nova_compute_hooks import update_nrpe_config

from test_utils import CharmTestCase

with patch('charmhelpers.contrib.hardening.harden.harden') as mock_dec:
    mock_dec.side_effect = (lambda *dargs, **dkwargs: lambda f:
                            lambda *args, **kwargs: f(*args, **kwargs))
    with patch("nova_compute_utils.restart_map"):
        with patch("nova_compute_utils.register_configs"):
            import nova_compute_hooks as hooks
            importlib.reload(hooks)


TO_PATCH = [
    # charmhelpers.core.hookenv
    'Hooks',
    'config',
    'local_unit',
    'log',
    'is_relation_made',
    'relation_get',
    'relation_ids',
    'relation_set',
    'service_name',
    'related_units',
    'remote_service_name',
    # charmhelpers.core.host
    'apt_install',
    'apt_purge',
    'apt_update',
    'filter_installed_packages',
    'restart_on_change',
    'service_restart',
    'is_container',
    'service_running',
    'service_start',
    'mkdir',
    # charmhelpers.contrib.openstack.utils
    'configure_installation_source',
    'openstack_upgrade_available',
    # charmhelpers.contrib.network.ip
    'get_relation_ip',
    # nova_compute_context
    'nova_metadata_requirement',
    # nova_compute_utils
    # 'PACKAGES',
    'create_libvirt_secret',
    'restart_map',
    'determine_packages',
    'import_authorized_keys',
    'import_keystone_ca_cert',
    'initialize_ssh_keys',
    'migration_enabled',
    'do_openstack_upgrade',
    'public_ssh_key',
    'register_configs',
    'disable_shell',
    'enable_shell',
    'update_nrpe_config',
    'network_manager',
    'libvirt_daemon',
    'configure_local_ephemeral_storage',
    'fix_path_ownership',
    'update_all_configs',
    # misc_utils
    'ensure_ceph_keyring',
    'execd_preinstall',
    'assert_libvirt_rbd_imagebackend_allowed',
    'remove_libvirt_network',
    # socket
    'gethostname',
    'create_sysctl',
    'install_hugepages',
    'uuid',
    # unitdata
    'unitdata',
    # templating
    'render',
    'remove_old_packages',
    'services',
    'send_application_name',
]


class NovaComputeRelationsTests(CharmTestCase):

    def setUp(self):
        super(NovaComputeRelationsTests, self).setUp(hooks,
                                                     TO_PATCH)
        self.config.side_effect = self.test_config.get
        self.filter_installed_packages.side_effect = \
            MagicMock(side_effect=lambda pkgs: pkgs)
        self.gethostname.return_value = 'testserver'
        self.get_relation_ip.return_value = '10.0.0.50'
        self.is_container.return_value = False

    @patch.object(hooks, 'kv')
    @patch.object(hooks, 'os_release')
    def test_install_hook(self, _os_release, _kv):
        repo = 'cloud:precise-grizzly'
        self.test_config.set('openstack-origin', repo)
        self.determine_packages.return_value = ['foo', 'bar']
        _os_release.return_value = 'rocky'
        hooks.install()
        self.configure_installation_source.assert_called_with(repo)
        self.assertTrue(self.apt_update.called)
        self.apt_install.assert_called_with(['foo', 'bar'], fatal=True)
        self.assertTrue(self.execd_preinstall.called)
        _os_release.return_value = 'stein'
        kv = MagicMock()
        _kv.return_value = kv
        hooks.install()
        kv.set.assert_called_once_with(hooks.USE_FQDN_KEY, True)
        kv.flush.assert_called_once_with()

    @patch.object(hooks, 'ceph_changed')
    @patch.object(hooks, 'neutron_plugin_joined')
    def test_config_changed_with_upgrade(self, neutron_plugin_joined,
                                         ceph_changed):
        self.openstack_upgrade_available.return_value = True
        self.service_running.return_value = True

        def rel_ids(x):
            return {'neutron-plugin': ['rid1'],
                    'ceph': ['ceph:0']}.get(x, [])
        self.relation_ids.side_effect = rel_ids
        self.related_units.return_value = ['ceph/0']
        self.migration_enabled.return_value = False
        hooks.config_changed()
        self.assertTrue(self.do_openstack_upgrade.called)
        neutron_plugin_joined.assert_called_with('rid1', remote_restart=True)
        ceph_changed.assert_called_with(rid='ceph:0', unit='ceph/0')
        self.configure_local_ephemeral_storage.assert_called_once_with()
        self.service_start.assert_not_called()

    def test_config_changed_with_openstack_upgrade_action(self):
        self.openstack_upgrade_available.return_value = True
        self.test_config.set('action-managed-upgrade', True)
        self.migration_enabled.return_value = False
        self.service_running.return_value = True

        hooks.config_changed()
        self.assertFalse(self.do_openstack_upgrade.called)
        self.service_start.assert_not_called()

    @patch.object(hooks, 'neutron_plugin_joined')
    @patch.object(hooks, 'compute_joined')
    def test_config_changed_with_migration(self, compute_joined,
                                           neutron_plugin_joined):
        self.migration_enabled.return_value = True
        self.test_config.set('migration-auth-type', 'ssh')
        self.relation_ids.return_value = [
            'cloud-compute:0',
            'cloud-compute:1'
        ]
        self.service_running.return_value = True
        hooks.config_changed()
        ex = [
            call('cloud-compute:0'),
            call('cloud-compute:1'),
        ]
        self.assertEqual(ex, compute_joined.call_args_list)
        self.assertTrue(self.initialize_ssh_keys.called)
        self.service_start.assert_not_called()

    @patch.object(hooks, 'neutron_plugin_joined')
    @patch.object(hooks, 'compute_joined')
    def test_config_changed_with_resize(self, compute_joined,
                                        neutron_plugin_joined):
        self.test_config.set('enable-resize', True)
        self.migration_enabled.return_value = False
        self.relation_ids.return_value = [
            'cloud-compute:0',
            'cloud-compute:1'
        ]
        self.service_running.return_value = True
        hooks.config_changed()
        ex = [
            call('cloud-compute:0'),
            call('cloud-compute:1'),
        ]
        self.assertEqual(ex, compute_joined.call_args_list)
        self.initialize_ssh_keys.assert_called_with(user='nova')
        self.enable_shell.assert_called_with(user='nova')
        self.service_start.assert_not_called()

    @patch.object(hooks, 'neutron_plugin_joined')
    @patch.object(hooks, 'compute_joined')
    def test_config_changed_without_resize(self, compute_joined,
                                           neutron_plugin_joined):
        self.test_config.set('enable-resize', False)
        self.migration_enabled.return_value = False
        self.relation_ids.return_value = [
            'cloud-compute:0',
            'cloud-compute:1'
        ]
        self.service_running.return_value = True
        hooks.config_changed()
        ex = [
            call('cloud-compute:0'),
            call('cloud-compute:1'),
        ]
        self.assertEqual(ex, compute_joined.call_args_list)
        self.disable_shell.assert_called_with(user='nova')
        self.service_start.assert_not_called()

    @patch.object(hooks, 'compute_joined')
    def test_config_changed_no_upgrade_no_migration(self, compute_joined):
        self.openstack_upgrade_available.return_value = False
        self.migration_enabled.return_value = False
        self.service_running.return_value = True
        hooks.config_changed()
        self.assertFalse(self.do_openstack_upgrade.called)
        self.assertFalse(compute_joined.called)
        self.service_start.assert_not_called()

    @patch.object(hooks, 'compute_joined')
    def test_config_changed_with_sysctl(self, compute_joined):
        self.migration_enabled.return_value = False
        self.service_running.return_value = True
        self.test_config.set(
            'sysctl',
            '{foo : bar}'
        )
        hooks.config_changed()
        self.create_sysctl.assert_called_with(
            '{foo : bar}',
            '/etc/sysctl.d/50-nova-compute.conf',
            ignore=True)

    @patch.object(hooks, 'compute_joined')
    def test_config_changed_with_sysctl_in_container(self, compute_joined):
        self.migration_enabled.return_value = False
        self.is_container.return_value = True
        self.service_running.return_value = True
        self.test_config.set(
            'sysctl',
            '{foo : bar}'
        )
        hooks.config_changed()
        self.create_sysctl.assert_not_called()
        self.service_start.assert_not_called()

    @patch.object(hooks, 'compute_joined')
    def test_config_changed_no_nrpe(self, compute_joined):
        self.openstack_upgrade_available.return_value = False
        self.migration_enabled.return_value = False
        self.is_relation_made.return_value = False
        self.service_running.return_value = True
        hooks.config_changed()
        self.assertFalse(self.update_nrpe_config.called)
        self.service_start.assert_not_called()

    @patch.object(hooks, 'compute_joined')
    def test_config_changed_nrpe(self, compute_joined):
        self.openstack_upgrade_available.return_value = False
        self.migration_enabled.return_value = False
        self.is_relation_made.return_value = True
        self.service_running.return_value = True
        hooks.config_changed()
        self.assertTrue(self.update_nrpe_config.called)
        self.service_start.assert_not_called()

    @patch.object(hooks, 'compute_joined')
    def test_config_changed_invalid_migration(self, compute_joined):
        self.migration_enabled.return_value = True
        self.service_running.return_value = True
        self.test_config.set('migration-auth-type', 'none')
        with self.assertRaises(Exception) as context:
            hooks.config_changed()
            self.assertEqual(
                context.exception.message,
                'Invalid migration-auth-type')
        self.service_start.assert_not_called()

    @patch.object(hooks, 'compute_joined')
    def test_config_changed_use_multipath_false(self,
                                                compute_joined):
        self.service_running.return_value = True
        self.test_config.set('use-multipath', False)
        hooks.config_changed()
        self.assertEqual(self.filter_installed_packages.call_count, 0)
        self.service_start.assert_not_called()

    @patch.object(hooks, 'compute_joined')
    def test_config_changed_use_multipath_true(self,
                                               compute_joined):
        self.test_config.set('use-multipath', True)
        self.filter_installed_packages.return_value = []
        self.service_running.return_value = True
        hooks.config_changed()
        self.assertEqual(self.filter_installed_packages.call_count, 1)
        self.apt_install.assert_called_with(hooks.MULTIPATH_PACKAGES,
                                            fatal=True)
        self.service_start.assert_not_called()

    @patch.object(hooks, 'compute_joined')
    def test_config_changed_iscsid_not_running(self,
                                               compute_joined):
        self.service_running.return_value = False
        hooks.config_changed()
        self.service_start.assert_called_once_with('iscsid')

    @patch('os.path.exists')
    @patch.object(hooks, 'compute_joined')
    def test_config_changed_instances_path(self,
                                           compute_joined,
                                           exists):
        self.service_running.return_value = True
        self.test_config.set('instances-path', '/srv/instances')
        exists.return_value = False
        hooks.config_changed()
        exists.assert_called_once_with('/srv/instances')
        self.mkdir.assert_called_once_with(
            path='/srv/instances',
            owner='nova', group='nova',
            perms=0o775
        )
        self.service_start.assert_not_called()
        self.fix_path_ownership.assert_called_once_with(
            '/srv/instances',
            user='nova'
        )

    @patch('nova_compute_hooks.nrpe')
    @patch('nova_compute_hooks.services')
    @patch('charmhelpers.core.hookenv')
    def test_nrpe_services_no_qemu_kvm(self, hookenv, services, nrpe):
        '''
        The qemu-kvm service is not monitored by NRPE, since it's one-shot.
        '''
        services.return_value = ['libvirtd', 'qemu-kvm', 'libvirt-bin']
        update_nrpe_config()
        nrpe.add_init_service_checks.assert_called_with(
            ANY, ['libvirtd', 'libvirt-bin'], ANY)

    def test_amqp_joined(self):
        hooks.amqp_joined()
        self.relation_set.assert_called_with(
            username='nova', vhost='openstack',
            relation_id=None)

    @patch.object(hooks, 'CONFIGS')
    def test_amqp_changed_missing_relation_data(self, configs):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = []
        hooks.amqp_changed()
        self.log.assert_called_with(
            'amqp relation incomplete. Peer not ready?'
        )

    def _amqp_test(self, configs, neutron=False):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = ['amqp']
        configs.write = MagicMock()
        hooks.amqp_changed()

    @patch.object(hooks, 'CONFIGS')
    def test_amqp_changed_with_data_no_neutron(self, configs):
        self._amqp_test(configs)
        self.assertEqual([call('/etc/nova/nova.conf')],
                         configs.write.call_args_list)

    @patch.object(hooks, 'CONFIGS')
    def test_image_service_missing_relation_data(self, configs):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = []
        hooks.image_service_changed()
        self.log.assert_called_with(
            'image-service relation incomplete. Peer not ready?'
        )

    @patch.object(hooks, 'CONFIGS')
    def test_image_service_with_relation_data(self, configs):
        configs.complete_contexts = MagicMock()
        configs.write = MagicMock()
        configs.complete_contexts.return_value = ['image-service']
        hooks.image_service_changed()
        configs.write.assert_called_with('/etc/nova/nova.conf')

    @patch.object(hooks, 'get_availability_zone')
    def test_compute_joined_no_migration_no_resize(self, mock_az):
        mock_az.return_value = ''
        self.migration_enabled.return_value = False
        hooks.compute_joined()
        self.assertFalse(self.relation_set.called)

    @patch.object(hooks, 'get_availability_zone')
    def test_compute_joined_with_juju_az(self, mock_az):
        self.migration_enabled.return_value = False
        mock_az.return_value = 'az1'
        hooks.compute_joined('cloud-compute:2')
        self.relation_set.assert_called_with(**{
            'relation_id': 'cloud-compute:2',
            'availability_zone': 'az1',
        })

    def test_compute_joined_with_ssh_migration(self):
        self.migration_enabled.return_value = True
        self.test_config.set('migration-auth-type', 'ssh')
        self.public_ssh_key.return_value = 'foo'
        hooks.compute_joined()
        self.relation_set.assert_called_with(**{
            'relation_id': None,
            'ssh_public_key': 'foo',
            'migration_auth_type': 'ssh',
            'hostname': 'testserver',
            'private-address': '10.0.0.50',
        })
        hooks.compute_joined(rid='cloud-compute:2')
        self.relation_set.assert_called_with(**{
            'relation_id': 'cloud-compute:2',
            'ssh_public_key': 'foo',
            'migration_auth_type': 'ssh',
            'hostname': 'testserver',
            'private-address': '10.0.0.50',
        })
        self.get_relation_ip.assert_called_with(
            'migration', cidr_network=None
        )

    def test_compute_joined_with_resize(self):
        self.migration_enabled.return_value = False
        self.test_config.set('enable-resize', True)
        self.public_ssh_key.return_value = 'bar'
        hooks.compute_joined()
        self.relation_set.assert_called_with(**{
            'relation_id': None,
            'nova_ssh_public_key': 'bar',
            'hostname': 'testserver',
            'private-address': '10.0.0.50',
        })
        hooks.compute_joined(rid='cloud-compute:2')
        self.relation_set.assert_called_with(**{
            'relation_id': 'cloud-compute:2',
            'nova_ssh_public_key': 'bar',
            'hostname': 'testserver',
            'private-address': '10.0.0.50',
        })
        self.get_relation_ip.assert_called_with(
            'migration', cidr_network=None
        )

    def test_compute_changed(self):
        hooks.compute_changed()
        self.assertTrue(self.import_keystone_ca_cert.called)
        self.import_authorized_keys.assert_has_calls([
            call(),
            call(user='nova', prefix='nova'),
        ])
        self.update_all_configs.assert_called()

    def test_compute_changed_nonstandard_authorized_keys_path(self):
        self.migration_enabled.return_value = False
        self.test_config.set('enable-resize', True)
        hooks.compute_changed()
        self.import_authorized_keys.assert_called_with(
            user='nova',
            prefix='nova',
        )

    def test_nova_ceilometer_relation_changed(self):
        hooks.nova_ceilometer_relation_changed()
        self.update_all_configs.assert_called()

    def test_ceph_joined(self):
        self.libvirt_daemon.return_value = 'libvirt-bin'
        hooks.ceph_joined()
        self.apt_install.assert_called_with(['ceph-common'], fatal=True)
        self.service_restart.assert_called_with('libvirt-bin')
        self.libvirt_daemon.assert_called()
        self.send_application_name.assert_called_once_with()

    @patch.object(hooks, 'CONFIGS')
    def test_ceph_changed_missing_relation_data(self, configs):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = []
        hooks.ceph_changed()
        self.log.assert_called_with(
            'ceph relation incomplete. Peer not ready?'
        )

    @patch.object(hooks, 'CONFIGS')
    def test_ceph_changed_no_keyring(self, configs):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = ['ceph']
        self.ensure_ceph_keyring.return_value = False
        hooks.ceph_changed()
        self.log.assert_called_with(
            'Could not create ceph keyring: peer not ready?'
        )

    @patch.object(hooks, '_handle_ceph_request')
    @patch.object(hooks, 'create_libvirt_secret')
    @patch('nova_compute_context.service_name')
    @patch.object(hooks, 'CONFIGS')
    def test_ceph_changed_with_key_and_relation_data(self, configs,
                                                     service_name,
                                                     create_libvirt_secret,
                                                     _handle_ceph_request):
        configs.complete_contexts = MagicMock()
        configs.complete_contexts.return_value = ['ceph']
        self.ensure_ceph_keyring.return_value = True
        configs.write = MagicMock()
        service_name.return_value = 'nova-compute'
        key = {'data': 'key'}
        self.relation_get.return_value = key

        hooks.ceph_changed()
        ex = [
            call('/var/lib/charm/nova-compute/ceph.conf'),
            call('/etc/ceph/secret.xml'),
            call('/etc/nova/nova.conf'),
        ]
        self.assertEqual(ex, configs.write.call_args_list)
        create_libvirt_secret.assert_called_once_with(
            secret_file='/etc/ceph/secret.xml', key=key,
            secret_uuid=hooks.CEPH_SECRET_UUID)
        # confirm exception is caught
        _handle_ceph_request.side_effect = ValueError
        hooks.ceph_changed()
        self.log.assert_called_once()

    @patch.object(hooks, 'get_ceph_request')
    @patch.object(hooks, 'get_request_states')
    def test__handle_ceph_request_send_request(
            self, get_request_states, get_ceph_request):
        request = hooks.CephBrokerRq()
        get_ceph_request.return_value = request
        get_request_states.return_value = {
            'ceph:43': {'complete': False, 'sent': False}
        }
        self.relation_ids.return_value = ['ceph:43']
        hooks._handle_ceph_request()

        get_ceph_request.assert_called_once_with()
        get_request_states.assert_called_once_with(request, relation='ceph')
        self.relation_set.assert_called_once_with(
            relation_id='ceph:43', broker_req=request.request)

    @patch.object(hooks, 'get_ceph_request')
    @patch.object(hooks, 'get_request_states')
    def test__handle_ceph_request_already_sent(
            self, get_request_states, get_ceph_request):
        request = hooks.CephBrokerRq()
        get_ceph_request.return_value = request
        get_request_states.return_value = {
            'ceph:43': {'complete': False, 'sent': True}
        }
        hooks._handle_ceph_request()

        get_ceph_request.assert_called_once_with()
        get_request_states.assert_called_once_with(request, relation='ceph')
        self.relation_set.assert_not_called()

    @patch.object(hooks, 'is_broker_action_done')
    @patch.object(hooks, 'get_ceph_request')
    @patch.object(hooks, 'get_request_states')
    @patch.object(hooks, '_get_broker_rid_unit_for_previous_request')
    def test__handle_ceph_request_complete_no_broker(
            self, _get_broker_rid_unit_for_previous_request,
            get_request_states, get_ceph_request, is_broker_action_done):
        request = hooks.CephBrokerRq()
        get_ceph_request.return_value = request
        get_request_states.return_value = {
            'ceph:43': {'complete': True, 'sent': True}
        }
        _get_broker_rid_unit_for_previous_request.return_value = None, None
        hooks._handle_ceph_request()

        is_broker_action_done.assert_not_called()
        get_ceph_request.assert_called_once_with()
        get_request_states.assert_called_once_with(request, relation='ceph')

    @patch.object(hooks, 'service_restart')
    @patch.object(hooks, 'mark_broker_action_done')
    @patch.object(hooks, 'is_broker_action_done')
    @patch.object(hooks, 'get_ceph_request')
    @patch.object(hooks, 'get_request_states')
    @patch.object(hooks, '_get_broker_rid_unit_for_previous_request')
    def test__handle_ceph_request_complete_not_action_done(
            self, _get_broker_rid_unit_for_previous_request,
            get_request_states, get_ceph_request, is_broker_action_done,
            mark_broker_action_done, service_restart):
        request = hooks.CephBrokerRq()
        get_ceph_request.return_value = request
        get_request_states.return_value = {
            'ceph:43': {'complete': True, 'sent': True}
        }
        _get_broker_rid_unit_for_previous_request.return_value = 'ceph:43',\
                                                                 'ceph-mon/0'
        is_broker_action_done.return_value = False
        hooks._handle_ceph_request()

        mark_broker_action_done.assert_called_once_with(
            'nova_compute_restart', 'ceph:43', 'ceph-mon/0')
        service_restart.assert_called_once_with('nova-compute')
        is_broker_action_done.assert_called_once_with(
            'nova_compute_restart', 'ceph:43', 'ceph-mon/0')
        get_ceph_request.assert_called_once_with()
        get_request_states.assert_called_once_with(request, relation='ceph')

    @patch.object(hooks, 'service_restart')
    @patch.object(hooks, 'is_broker_action_done')
    @patch.object(hooks, 'get_ceph_request')
    @patch.object(hooks, 'get_request_states')
    @patch.object(hooks, '_get_broker_rid_unit_for_previous_request')
    def test__handle_ceph_request_complete_no_restart(
            self, _get_broker_rid_unit_for_previous_request,
            get_request_states, get_ceph_request, is_broker_action_done,
            service_restart):
        request = hooks.CephBrokerRq()
        get_ceph_request.return_value = request
        get_request_states.return_value = {
            'ceph:43': {'complete': True, 'sent': True}
        }
        _get_broker_rid_unit_for_previous_request.return_value = 'ceph:43',\
                                                                 'ceph-mon/0'
        is_broker_action_done.return_value = True
        hooks._handle_ceph_request()

        service_restart.assert_not_called()
        is_broker_action_done.assert_called_once_with(
            'nova_compute_restart', 'ceph:43', 'ceph-mon/0')
        get_ceph_request.assert_called_once_with()
        get_request_states.assert_called_once_with(request, relation='ceph')

    @patch.object(hooks, 'get_broker_rsp_key')
    @patch.object(hooks, 'get_previous_request')
    def test__get_broker_rid_unit_for_previous_request(
            self, get_previous_request, get_broker_rsp_key):
        request = hooks.CephBrokerRq()
        get_broker_rsp_key.return_value = "my_key"
        get_previous_request.return_value = request
        self.relation_ids.return_value = ['ceph:43']
        self.related_units.return_value = ['ceph-mon/0', 'ceph-mon/1']
        self.relation_get.side_effect = [{}, {
            'my_key': '{"api-version": 1, "ops": [], '
                      '"request-id": "' + request.request_id + '"}'
        }]
        rid, unit = hooks._get_broker_rid_unit_for_previous_request()
        get_previous_request.assert_called_once_with('ceph:43')
        get_broker_rsp_key.assert_called_once_with()
        self.relation_get.assert_has_calls = [
            call(rid='ceph:43', unit='ceph-mon/0'),
            call(rid='ceph:43', unit='ceph-mon/1')
        ]
        self.assertEqual('ceph-mon/1', unit)
        self.assertEqual('ceph:43', rid)

    @patch.object(hooks, 'get_broker_rsp_key')
    @patch.object(hooks, 'get_previous_request')
    def test__get_broker_rid_unit_for_previous_request_not_found(
            self, get_previous_request, get_broker_rsp_key):
        request = hooks.CephBrokerRq()
        get_broker_rsp_key.return_value = "my_key"
        get_previous_request.return_value = request
        self.relation_ids.return_value = ['ceph:43']
        self.related_units.return_value = ['ceph-mon/0', 'ceph-mon/1']
        self.relation_get.side_effect = [{}, {}]
        rid, unit = hooks._get_broker_rid_unit_for_previous_request()
        get_previous_request.assert_called_once_with('ceph:43')
        get_broker_rsp_key.assert_called_once_with()
        self.relation_get.assert_has_calls = [
            call(rid='ceph:43', unit='ceph-mon/0'),
            call(rid='ceph:43', unit='ceph-mon/1')
        ]
        self.assertIsNone(unit)
        self.assertIsNone(rid)

    @patch.object(hooks.ch_context, 'CephBlueStoreCompressionContext')
    @patch('charmhelpers.contrib.storage.linux.ceph.CephBrokerRq'
           '.add_op_request_access_to_group')
    @patch('charmhelpers.contrib.storage.linux.ceph.CephBrokerRq'
           '.add_op_create_pool')
    @patch('uuid.uuid1')
    def test_get_ceph_request(self, uuid1, mock_create_pool,
                              mock_request_access,
                              mock_bluestore_compression):
        self.assert_libvirt_rbd_imagebackend_allowed.return_value = True
        self.test_config.set('rbd-pool', 'nova')
        self.test_config.set('ceph-osd-replication-count', 3)
        self.test_config.set('ceph-pool-weight', 28)
        uuid1.return_value = 'my_uuid'
        expected = hooks.CephBrokerRq(request_id="my_uuid")
        result = hooks.get_ceph_request()
        mock_create_pool.assert_not_called()
        mock_request_access.assert_not_called()
        self.assertEqual(expected, result)

    @patch.object(hooks.ch_context, 'CephBlueStoreCompressionContext')
    @patch('charmhelpers.contrib.storage.linux.ceph.CephBrokerRq'
           '.add_op_request_access_to_group')
    @patch('charmhelpers.contrib.storage.linux.ceph.CephBrokerRq'
           '.add_op_create_replicated_pool')
    @patch('uuid.uuid1')
    def test_get_ceph_request_rbd(self, uuid1, mock_create_pool,
                                  mock_request_access,
                                  mock_bluestore_compression):
        self.assert_libvirt_rbd_imagebackend_allowed.return_value = True
        self.test_config.set('rbd-pool', 'nova')
        self.test_config.set('ceph-osd-replication-count', 3)
        self.test_config.set('ceph-pool-weight', 28)
        self.test_config.set('libvirt-image-backend', 'rbd')
        uuid1.return_value = 'my_uuid'
        expected = hooks.CephBrokerRq(request_id="my_uuid")
        result = hooks.get_ceph_request()
        mock_create_pool.assert_called_with(name='nova', replica_count=3,
                                            weight=28,
                                            group='vms', app_name='rbd')
        mock_request_access.assert_not_called()
        self.assertEqual(expected, result)
        # confirm operation with bluestore compression
        mock_create_pool.reset_mock()
        mock_bluestore_compression().get_kwargs.return_value = {
            'compression_mode': 'fake',
        }
        hooks.get_ceph_request()
        mock_create_pool.assert_called_once_with(name='nova', replica_count=3,
                                                 weight=28, group='vms',
                                                 app_name='rbd',
                                                 compression_mode='fake')

    @patch.object(hooks.ch_context, 'CephBlueStoreCompressionContext')
    @patch('charmhelpers.contrib.storage.linux.ceph.CephBrokerRq'
           '.add_op_create_erasure_pool')
    @patch('charmhelpers.contrib.storage.linux.ceph.CephBrokerRq'
           '.add_op_create_erasure_profile')
    @patch('charmhelpers.contrib.storage.linux.ceph.CephBrokerRq'
           '.add_op_request_access_to_group')
    @patch('charmhelpers.contrib.storage.linux.ceph.CephBrokerRq'
           '.add_op_create_pool')
    @patch('uuid.uuid1')
    def test_get_ceph_request_rbd_ec(self, uuid1, mock_create_pool,
                                     mock_request_access,
                                     mock_create_erasure_profile,
                                     mock_create_erasure_pool,
                                     mock_bluestore_compression):
        self.assert_libvirt_rbd_imagebackend_allowed.return_value = True
        self.test_config.set('rbd-pool', 'nova')
        self.test_config.set('ceph-osd-replication-count', 3)
        self.test_config.set('ceph-pool-weight', 28)
        self.test_config.set('libvirt-image-backend', 'rbd')
        self.test_config.set('pool-type', 'erasure-coded')
        self.test_config.set('ec-profile-plugin', 'shec')
        self.test_config.set('ec-profile-k', 6)
        self.test_config.set('ec-profile-m', 2)
        self.test_config.set('ec-profile-durability-estimator', 2)
        uuid1.return_value = 'my_uuid'
        expected = hooks.CephBrokerRq(request_id="my_uuid")
        result = hooks.get_ceph_request()
        mock_create_pool.assert_called_with(
            name='nova-metadata',
            replica_count=3,
            weight=0.28,
            group='vms',
            app_name='rbd'
        )
        mock_create_erasure_profile.assert_called_with(
            name='nova-profile',
            k=6, m=2,
            lrc_locality=None,
            lrc_crush_locality=None,
            shec_durability_estimator=2,
            clay_helper_chunks=None,
            clay_scalar_mds=None,
            device_class=None,
            erasure_type='shec',
            erasure_technique=None
        )
        mock_create_erasure_pool.assert_called_with(
            name='nova',
            erasure_profile='nova-profile',
            weight=27.72,
            group='vms',
            app_name='rbd',
            allow_ec_overwrites=True
        )
        mock_request_access.assert_not_called()
        self.assertEqual(expected, result)
        # confirm operation with bluestore compression
        mock_create_erasure_pool.reset_mock()
        mock_bluestore_compression().get_kwargs.return_value = {
            'compression_mode': 'fake',
        }
        hooks.get_ceph_request()
        mock_create_erasure_pool.assert_called_with(
            name='nova',
            erasure_profile='nova-profile',
            weight=27.72,
            group='vms',
            app_name='rbd',
            allow_ec_overwrites=True,
            compression_mode='fake',
        )

    @patch.object(hooks.ch_context, 'CephBlueStoreCompressionContext')
    @patch('charmhelpers.contrib.storage.linux.ceph.CephBrokerRq'
           '.add_op_request_access_to_group')
    @patch('charmhelpers.contrib.storage.linux.ceph.CephBrokerRq'
           '.add_op_create_replicated_pool')
    @patch('uuid.uuid1')
    def test_get_ceph_request_perms(self, uuid1, mock_create_pool,
                                    mock_request_access,
                                    mock_bluestore_compression):
        self.assert_libvirt_rbd_imagebackend_allowed.return_value = True
        self.test_config.set('rbd-pool', 'nova')
        self.test_config.set('ceph-osd-replication-count', 3)
        self.test_config.set('ceph-pool-weight', 28)
        self.test_config.set('libvirt-image-backend', 'rbd')
        self.test_config.set('restrict-ceph-pools', True)
        uuid1.return_value = 'my_uuid'
        expected = hooks.CephBrokerRq(request_id="my_uuid")
        result = hooks.get_ceph_request()
        mock_create_pool.assert_called_with(name='nova', replica_count=3,
                                            weight=28,
                                            group='vms', app_name='rbd')
        mock_request_access.assert_has_calls([
            call(name='volumes',
                 object_prefix_permissions={'class-read': ['rbd_children']},
                 permission='rwx'),
            call(name='images',
                 object_prefix_permissions={'class-read': ['rbd_children']},
                 permission='rwx'),
            call(name='vms',
                 object_prefix_permissions={'class-read': ['rbd_children']},
                 permission='rwx'),
        ])
        self.assertEqual(expected, result)
        # confirm operation with bluestore compression
        mock_create_pool.reset_mock()
        mock_bluestore_compression().get_kwargs.return_value = {
            'compression_mode': 'fake',
        }
        hooks.get_ceph_request()
        mock_create_pool.assert_called_once_with(name='nova', replica_count=3,
                                                 weight=28, group='vms',
                                                 app_name='rbd',
                                                 compression_mode='fake')

    @patch.object(hooks, 'service_restart_handler')
    @patch.object(hooks, 'CONFIGS')
    def test_neutron_plugin_changed(self, configs,
                                    service_restart_handler):
        self.nova_metadata_requirement.return_value = (True,
                                                       'sharedsecret')
        hooks.neutron_plugin_changed()
        self.assertTrue(self.apt_update.called)
        self.apt_install.assert_called_with(['nova-api-metadata'],
                                            fatal=True)
        configs.write.assert_called_with('/etc/nova/nova.conf')
        service_restart_handler.assert_called_with(
            default_service='nova-compute')

    @patch.object(hooks, 'service_restart_handler')
    @patch.object(hooks, 'CONFIGS')
    def test_neutron_plugin_changed_nometa(self, configs,
                                           service_restart_handler):
        self.nova_metadata_requirement.return_value = (False, None)
        hooks.neutron_plugin_changed()
        self.apt_purge.assert_called_with('nova-api-metadata',
                                          fatal=True)
        configs.write.assert_called_with('/etc/nova/nova.conf')
        service_restart_handler.assert_called_with(
            default_service='nova-compute')

    @patch.object(hooks, 'service_restart_handler')
    @patch.object(hooks, 'CONFIGS')
    def test_neutron_plugin_changed_meta(self, configs,
                                         service_restart_handler):
        self.nova_metadata_requirement.return_value = (True, None)
        hooks.neutron_plugin_changed()
        self.apt_install.assert_called_with(['nova-api-metadata'],
                                            fatal=True)
        configs.write.assert_called_with('/etc/nova/nova.conf')
        service_restart_handler.assert_called_with(
            default_service='nova-compute')

    @patch.object(hooks, 'get_hugepage_number')
    def test_neutron_plugin_joined_relid(self, get_hugepage_number):
        get_hugepage_number.return_value = None
        hooks.neutron_plugin_joined(relid='relid23')
        expect_rel_settings = {
            'hugepage_number': None,
            'default_availability_zone': 'nova',
        }
        self.relation_set.assert_called_with(
            relation_id='relid23',
            **expect_rel_settings
        )

    @patch('os.environ.get')
    @patch.object(hooks, 'get_hugepage_number')
    def test_neutron_plugin_joined_relid_juju_az(self,
                                                 get_hugepage_number,
                                                 mock_env_get):
        self.test_config.set('customize-failure-domain', True)

        def environ_get_side_effect(key):
            return {
                'JUJU_AVAILABILITY_ZONE': 'az1',
            }[key]
        mock_env_get.side_effect = environ_get_side_effect
        get_hugepage_number.return_value = None
        hooks.neutron_plugin_joined(relid='relid23')
        expect_rel_settings = {
            'hugepage_number': None,
            'default_availability_zone': 'az1',
        }
        self.relation_set.assert_called_with(
            relation_id='relid23',
            **expect_rel_settings
        )

    @patch.object(hooks, 'get_hugepage_number')
    def test_neutron_plugin_joined_huge(self, get_hugepage_number):
        get_hugepage_number.return_value = 12
        hooks.neutron_plugin_joined()
        expect_rel_settings = {
            'hugepage_number': 12,
            'default_availability_zone': 'nova',
        }
        self.relation_set.assert_called_with(
            relation_id=None,
            **expect_rel_settings
        )

    @patch.object(hooks, 'get_hugepage_number')
    def test_neutron_plugin_joined_remote_restart(self, get_hugepage_number):
        get_hugepage_number.return_value = None
        self.uuid.uuid4.return_value = 'e030b959-7207'
        hooks.neutron_plugin_joined(remote_restart=True)
        expect_rel_settings = {
            'hugepage_number': None,
            'restart-trigger': 'e030b959-7207',
            'default_availability_zone': 'nova',
        }
        self.relation_set.assert_called_with(
            relation_id=None,
            **expect_rel_settings
        )

    @patch.object(hooks, 'is_unit_paused_set')
    def test_service_restart_handler(self,
                                     is_unit_paused_set):
        self.relation_get.return_value = None
        mock_kv = MagicMock()
        mock_kv.get.return_value = None
        self.unitdata.kv.return_value = mock_kv

        hooks.service_restart_handler(default_service='foorbar')

        self.relation_get.assert_called_with(
            attribute='restart-nonce',
            unit=None,
            rid=None
        )
        is_unit_paused_set.assert_not_called()

    @patch.object(hooks, 'is_unit_paused_set')
    def test_service_restart_handler_with_service(self,
                                                  is_unit_paused_set):
        self.relation_get.side_effect = ['nonce', 'foobar-service']
        mock_kv = MagicMock()
        mock_kv.get.return_value = None
        self.unitdata.kv.return_value = mock_kv
        is_unit_paused_set.return_value = False

        hooks.service_restart_handler()

        self.relation_get.assert_has_calls([
            call(attribute='restart-nonce',
                 unit=None,
                 rid=None),
            call(attribute='remote-service',
                 unit=None,
                 rid=None),
        ])
        self.service_restart.assert_called_with('foobar-service')
        mock_kv.set.assert_called_with('restart-nonce',
                                       'nonce')
        self.assertTrue(mock_kv.flush.called)

    @patch.object(hooks, 'is_unit_paused_set')
    def test_service_restart_handler_when_paused(self,
                                                 is_unit_paused_set):
        self.relation_get.side_effect = ['nonce', 'foobar-service']
        mock_kv = MagicMock()
        mock_kv.get.return_value = None
        self.unitdata.kv.return_value = mock_kv
        is_unit_paused_set.return_value = True

        hooks.service_restart_handler()

        self.relation_get.assert_has_calls([
            call(attribute='restart-nonce',
                 unit=None,
                 rid=None),
        ])
        self.service_restart.assert_not_called()
        mock_kv.set.assert_called_with('restart-nonce',
                                       'nonce')
        self.assertTrue(mock_kv.flush.called)

    def test_ceph_access_incomplete(self):
        self.relation_get.return_value = None
        self.test_config.set('virt-type', 'kvm')
        hooks.ceph_access()
        self.relation_get.assert_has_calls([
            call('key', None, None),
            call('secret-uuid', None, None),
        ])
        self.render.assert_not_called()
        self.create_libvirt_secret.assert_not_called()

    def test_ceph_access_lxd_no_replication_device(self):
        self.relation_get.side_effect = [None, 'mykey', 'uuid2']
        self.remote_service_name.return_value = 'cinder-ceph'
        self.test_config.set('virt-type', 'lxd')
        hooks.ceph_access()
        self.relation_get.assert_has_calls([
            call('key', None, None),
            call('secret-uuid', None, None),
        ])
        self.render.assert_not_called()
        self.create_libvirt_secret.assert_not_called()
        self.ensure_ceph_keyring.assert_called_with(
            service='cinder-ceph',
            user='nova',
            group='nova',
            key='mykey'
        )

    def test_ceph_access_complete_no_replication_device(self):
        self.relation_get.side_effect = [None, 'mykey', 'uuid2']
        self.remote_service_name.return_value = 'cinder-ceph'
        self.test_config.set('virt-type', 'kvm')
        hooks.ceph_access()
        self.relation_get.assert_has_calls([
            call('key', None, None),
            call('secret-uuid', None, None),
        ])
        self.render.assert_called_with(
            'secret.xml',
            '/etc/ceph/secret-cinder-ceph.xml',
            context={'ceph_secret_uuid': 'uuid2',
                     'service_name': 'cinder-ceph'}
        )
        self.create_libvirt_secret.assert_called_with(
            secret_file='/etc/ceph/secret-cinder-ceph.xml',
            secret_uuid='uuid2',
            key='mykey',
        )
        self.ensure_ceph_keyring.assert_called_with(
            service='cinder-ceph',
            user='nova',
            group='nova',
            key='mykey'
        )

    def test_ceph_access_complete_with_replication_device(self):
        keyrings = [
            {
                'name': 'cinder-ceph',
                'key': 'ceph-key',
                'secret-uuid': 'ceph-secret-uuid'
            },
            {
                'name': 'ceph-replication-device',
                'key': 'replication-device-key',
                'secret-uuid': 'replication-device-secret-uuid'
            }]
        self.relation_get.side_effect = [json.dumps(keyrings)]
        self.remote_service_name.return_value = 'cinder-ceph'
        self.test_config.set('virt-type', 'kvm')
        hooks.ceph_access()
        self.relation_get.assert_called_once_with('keyrings')
        self.render.assert_has_calls([
            call('secret.xml', '/etc/ceph/secret-cinder-ceph.xml',
                 context={'ceph_secret_uuid': 'ceph-secret-uuid',
                          'service_name': 'cinder-ceph'}),
            call('secret.xml', '/etc/ceph/secret-ceph-replication-device.xml',
                 context={'ceph_secret_uuid': 'replication-device-secret-uuid',
                          'service_name': 'ceph-replication-device'}),
        ])
        self.create_libvirt_secret.assert_has_calls([
            call(secret_file='/etc/ceph/secret-cinder-ceph.xml',
                 secret_uuid='ceph-secret-uuid',
                 key='ceph-key'),
            call(secret_file='/etc/ceph/secret-ceph-replication-device.xml',
                 secret_uuid='replication-device-secret-uuid',
                 key='replication-device-key')
        ])
        self.ensure_ceph_keyring.assert_has_calls([
            call(service='cinder-ceph',
                 user='nova',
                 group='nova',
                 key='ceph-key'),
            call(service='ceph-replication-device',
                 user='nova',
                 group='nova',
                 key='replication-device-key')
        ])

    def test_secrets_storage_relation_joined(self):
        self.get_relation_ip.return_value = '10.23.1.2'
        self.gethostname.return_value = 'testhost'
        hooks.secrets_storage_joined()
        self.get_relation_ip.assert_called_with('secrets-storage')
        self.relation_set.assert_called_with(
            relation_id=None,
            secret_backend='charm-vaultlocker',
            isolated=True,
            access_address='10.23.1.2',
            hostname='testhost'
        )
        self.gethostname.assert_called_once_with()

    def test_secrets_storage_relation_changed(self,):
        self.relation_get.return_value = None
        hooks.secrets_storage_changed()
        self.configure_local_ephemeral_storage.assert_called_once_with()

    def test_cloud_credentials_joined(self):
        self.local_unit.return_value = 'nova-compute-cell1/2'
        hooks.cloud_credentials_joined()
        self.relation_set.assert_called_with(username='nova_compute_cell1')

    @patch.object(hooks, 'CONFIGS')
    def test_cloud_credentials_changed(self, mock_CONFIGS):
        hooks.cloud_credentials_changed()
        mock_CONFIGS.write.assert_called_with('/etc/nova/nova.conf')

    @patch.object(hooks.grp, 'getgrnam')
    def test_upgrade_charm(self, getgrnam):
        grp_mock = MagicMock()
        grp_mock.gr_gid = None
        getgrnam.return_value = grp_mock
        self.remove_old_packages.return_value = False
        hooks.upgrade_charm()
        self.remove_old_packages.assert_called_once_with()
        self.assertFalse(self.service_restart.called)

    @patch.object(hooks.grp, 'getgrnam')
    def test_upgrade_charm_purge(self, getgrnam):
        grp_mock = MagicMock()
        grp_mock.gr_gid = None
        getgrnam.return_value = grp_mock
        self.remove_old_packages.return_value = True
        self.services.return_value = ['nova-compute']
        hooks.upgrade_charm()
        self.remove_old_packages.assert_called_once_with()
        self.service_restart.assert_called_once_with('nova-compute')
