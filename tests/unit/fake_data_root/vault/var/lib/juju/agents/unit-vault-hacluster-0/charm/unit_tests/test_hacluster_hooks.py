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

from unittest import mock
import os
import shutil
import sys
import tempfile
import unittest
import test_utils
import pcmk

mock_apt = mock.MagicMock()
sys.modules['apt_pkg'] = mock_apt
import hooks
import utils


@mock.patch.object(hooks, 'log', lambda *args, **kwargs: None)
@mock.patch('utils.COROSYNC_CONF', os.path.join(tempfile.mkdtemp(),
                                                'corosync.conf'))
class TestCorosyncConf(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        self.tmpfile = tempfile.NamedTemporaryFile(delete=False)
        os.environ['UNIT_STATE_DB'] = ':memory:'

    def tearDown(self):
        shutil.rmtree(self.tmpdir)
        os.remove(self.tmpfile.name)

    @mock.patch.object(pcmk.unitdata, 'kv')
    @mock.patch.object(hooks, 'remote_unit')
    @mock.patch.object(hooks, 'relation_type')
    @mock.patch.object(hooks, 'trigger_corosync_update_from_leader')
    @mock.patch.object(hooks, 'is_stonith_configured')
    @mock.patch.object(hooks, 'configure_peer_stonith_resource')
    @mock.patch.object(hooks, 'get_member_ready_nodes')
    @mock.patch.object(hooks, 'configure_resources_on_remotes')
    @mock.patch.object(hooks, 'configure_pacemaker_remote_stonith_resource')
    @mock.patch.object(hooks, 'configure_pacemaker_remote_resources')
    @mock.patch.object(hooks, 'set_cluster_symmetry')
    @mock.patch.object(hooks, 'write_maas_dns_address')
    @mock.patch('pcmk.wait_for_pcmk')
    @mock.patch('pcmk.crm_opt_exists')
    @mock.patch.object(hooks, 'is_leader')
    @mock.patch.object(hooks, 'configure_corosync')
    @mock.patch.object(hooks, 'configure_cluster_global')
    @mock.patch.object(hooks, 'configure_monitor_host')
    @mock.patch.object(hooks, 'configure_stonith')
    @mock.patch.object(hooks, 'related_units')
    @mock.patch.object(hooks, 'get_cluster_nodes')
    @mock.patch.object(hooks, 'relation_set')
    @mock.patch.object(hooks, 'relation_ids')
    @mock.patch.object(hooks, 'get_corosync_conf')
    @mock.patch('pcmk.commit')
    @mock.patch.object(hooks, 'config')
    @mock.patch.object(hooks, 'parse_data')
    def test_ha_relation_changed(self, parse_data, config, commit,
                                 get_corosync_conf, relation_ids, relation_set,
                                 get_cluster_nodes, related_units,
                                 configure_stonith, configure_monitor_host,
                                 configure_cluster_global, configure_corosync,
                                 is_leader, crm_opt_exists,
                                 wait_for_pcmk, write_maas_dns_address,
                                 set_cluster_symmetry,
                                 configure_pacemaker_remote_resources,
                                 configure_pacemaker_remote_stonith_resource,
                                 configure_resources_on_remotes,
                                 get_member_ready_nodes,
                                 configure_peer_stonith_resource,
                                 is_stonith_configured,
                                 trigger_corosync_update_from_leader,
                                 relation_type, remote_unit, mock_kv):

        def fake_crm_opt_exists(res_name):
            # res_ubuntu will take the "update resource" route
            # res_nova_eth0_vip will take the delete resource route
            return res_name in ["res_ubuntu", "res_nova_eth0_vip"]

        db = test_utils.FakeKvStore()
        mock_kv.return_value = db
        crm_opt_exists.side_effect = fake_crm_opt_exists
        commit.return_value = 0
        is_stonith_configured.return_value = False
        is_leader.return_value = True
        related_units.return_value = ['ha/0', 'ha/1', 'ha/2']
        get_cluster_nodes.return_value = ['10.0.3.2', '10.0.3.3', '10.0.3.4']
        get_member_ready_nodes.return_value = ['10.0.3.2', '10.0.3.3',
                                               '10.0.3.4']
        relation_ids.return_value = ['hanode:1']
        get_corosync_conf.return_value = True
        cfg = {'debug': False,
               'prefer-ipv6': False,
               'corosync_transport': 'udpu',
               'corosync_mcastaddr': 'corosync_mcastaddr',
               'cluster_count': 3,
               'failure_timeout': 180,
               'cluster_recheck_interval': 60}
        trigger_corosync_update_from_leader.return_value = False
        relation_type.return_value = "hanode"
        remote_unit.return_value = "hacluster/0"

        config.side_effect = lambda key: cfg.get(key)

        rel_get_data = {'locations': {'loc_foo': 'bar rule inf: meh eq 1'},
                        'clones': {'cl_foo': 'res_foo meta interleave=true'},
                        'groups': {'grp_foo': 'res_foo'},
                        'colocations': {'co_foo': 'inf: grp_foo cl_foo'},
                        'resources': {'res_foo': 'ocf:heartbeat:IPaddr2',
                                      'res_bar': 'ocf:heartbear:IPv6addr',
                                      'res_ubuntu': 'IPaddr2'},
                        'resource_params': {'res_foo': 'params bar',
                                            'res_ubuntu': 'params ubuntu=42'},
                        'ms': {'ms_foo': 'res_foo meta notify=true'},
                        'orders': {'foo_after': 'inf: res_foo ms_foo'},
                        'delete_resources': ['res_nova_eth0_vip']}

        def fake_parse_data(relid, unit, key):
            return rel_get_data.get(key, {})

        parse_data.side_effect = fake_parse_data

        with mock.patch.object(tempfile, "NamedTemporaryFile",
                               side_effect=lambda: self.tmpfile):
            hooks.ha_relation_changed()

        relation_set.assert_any_call(relation_id='hanode:1', ready=True)
        configure_stonith.assert_called_with()
        configure_monitor_host.assert_called_with()
        configure_cluster_global.assert_called_with(180, 60)
        configure_corosync.assert_called_with()
        set_cluster_symmetry.assert_called_with()
        configure_pacemaker_remote_resources.assert_called_with()
        write_maas_dns_address.assert_not_called()

        # verify deletion of resources.
        crm_opt_exists.assert_any_call('res_nova_eth0_vip')
        commit.assert_any_call('crm resource cleanup res_nova_eth0_vip')
        commit.assert_any_call('crm -w -F resource stop res_nova_eth0_vip')
        commit.assert_any_call('crm -w -F configure delete res_nova_eth0_vip')

        for kw, key in [('location', 'locations'),
                        ('clone', 'clones'),
                        ('group', 'groups'),
                        ('colocation', 'colocations'),
                        ('primitive', 'resources'),
                        ('ms', 'ms'),
                        ('order', 'orders')]:
            for name, params in rel_get_data[key].items():
                if name == "res_ubuntu":
                    commit.assert_any_call(
                        'crm configure load update %s' % self.tmpfile.name)

                elif name in rel_get_data['resource_params']:
                    res_params = rel_get_data['resource_params'][name]
                    commit.assert_any_call(
                        'crm -w -F configure %s %s %s %s' % (kw, name, params,
                                                             res_params))
                else:
                    commit.assert_any_call(
                        'crm -w -F configure %s %s %s' % (kw, name, params))

    @mock.patch.object(hooks, 'remote_unit')
    @mock.patch.object(hooks, 'relation_type')
    @mock.patch.object(hooks, 'trigger_corosync_update_from_leader')
    @mock.patch.object(hooks, 'is_stonith_configured')
    @mock.patch.object(hooks, 'configure_peer_stonith_resource')
    @mock.patch.object(hooks, 'get_member_ready_nodes')
    @mock.patch.object(hooks, 'configure_resources_on_remotes')
    @mock.patch.object(hooks, 'configure_pacemaker_remote_stonith_resource')
    @mock.patch.object(hooks, 'configure_pacemaker_remote_resources')
    @mock.patch.object(hooks, 'set_cluster_symmetry')
    @mock.patch.object(hooks, 'write_maas_dns_address')
    @mock.patch.object(hooks, 'setup_maas_api')
    @mock.patch.object(hooks, 'validate_dns_ha')
    @mock.patch('pcmk.wait_for_pcmk')
    @mock.patch('pcmk.crm_opt_exists')
    @mock.patch.object(hooks, 'is_leader')
    @mock.patch.object(hooks, 'configure_corosync')
    @mock.patch.object(hooks, 'configure_cluster_global')
    @mock.patch.object(hooks, 'configure_monitor_host')
    @mock.patch.object(hooks, 'configure_stonith')
    @mock.patch.object(hooks, 'related_units')
    @mock.patch.object(hooks, 'get_cluster_nodes')
    @mock.patch.object(hooks, 'relation_set')
    @mock.patch.object(hooks, 'relation_ids')
    @mock.patch.object(hooks, 'get_corosync_conf')
    @mock.patch('pcmk.commit')
    @mock.patch.object(hooks, 'config')
    @mock.patch.object(hooks, 'parse_data')
    def test_ha_relation_changed_dns_ha(
            self, parse_data, config, commit, get_corosync_conf, relation_ids,
            relation_set, get_cluster_nodes, related_units, configure_stonith,
            configure_monitor_host, configure_cluster_global,
            configure_corosync, is_leader, crm_opt_exists, wait_for_pcmk,
            validate_dns_ha, setup_maas_api, write_maas_dns_addr,
            set_cluster_symmetry, configure_pacemaker_remote_resources,
            configure_pacemaker_remote_stonith_resource,
            configure_resources_on_remotes, get_member_ready_nodes,
            configure_peer_stonith_resource,
            is_stonith_configured,
            trigger_corosync_update_from_leader,
            relation_type, remote_unit):
        is_stonith_configured.return_value = False
        validate_dns_ha.return_value = True
        crm_opt_exists.return_value = False
        is_leader.return_value = True
        related_units.return_value = ['ha/0', 'ha/1', 'ha/2']
        get_cluster_nodes.return_value = ['10.0.3.2', '10.0.3.3', '10.0.3.4']
        get_member_ready_nodes.return_value = ['10.0.3.2', '10.0.3.3',
                                               '10.0.3.4']
        relation_ids.return_value = ['ha:1']
        get_corosync_conf.return_value = True
        cfg = {'debug': False,
               'prefer-ipv6': False,
               'corosync_transport': 'udpu',
               'corosync_mcastaddr': 'corosync_mcastaddr',
               'cluster_count': 3,
               'maas_url': 'http://maas/MAAAS/',
               'maas_credentials': 'secret'}
        trigger_corosync_update_from_leader.return_value = False
        relation_type.return_value = "hanode"
        remote_unit.return_value = "hacluster/0"

        config.side_effect = lambda key: cfg.get(key)

        rel_get_data = {'locations': {'loc_foo': 'bar rule inf: meh eq 1'},
                        'clones': {'cl_foo': 'res_foo meta interleave=true'},
                        'groups': {'grp_foo': 'res_foo'},
                        'colocations': {'co_foo': 'inf: grp_foo cl_foo'},
                        'resources': {'res_foo_hostname': 'ocf:maas:dns'},
                        'resource_params': {
                            'res_foo_hostname': 'params bar '
                                                'ip_address="172.16.0.1"'},
                        'ms': {'ms_foo': 'res_foo meta notify=true'},
                        'orders': {'foo_after': 'inf: res_foo ms_foo'}}

        def fake_parse_data(relid, unit, key):
            return rel_get_data.get(key, {})

        parse_data.side_effect = fake_parse_data

        hooks.ha_relation_changed()
        self.assertTrue(validate_dns_ha.called)
        self.assertTrue(setup_maas_api.called)
        write_maas_dns_addr.assert_called_with('res_foo_hostname',
                                               '172.16.0.1')
        # Validate maas_credentials and maas_url are added to params
        commit.assert_any_call(
            'crm -w -F configure primitive res_foo_hostname ocf:maas:dns '
            'params bar ip_address="172.16.0.1" maas_url="http://maas/MAAAS/" '
            'maas_credentials="secret"')

    @mock.patch.object(hooks, 'remote_unit')
    @mock.patch.object(hooks, 'relation_type')
    @mock.patch.object(hooks, 'trigger_corosync_update_from_leader')
    @mock.patch.object(hooks, 'setup_maas_api')
    @mock.patch.object(hooks, 'validate_dns_ha')
    @mock.patch('pcmk.wait_for_pcmk')
    @mock.patch('pcmk.crm_opt_exists')
    @mock.patch.object(hooks, 'is_leader')
    @mock.patch.object(hooks, 'configure_corosync')
    @mock.patch.object(hooks, 'configure_cluster_global')
    @mock.patch.object(hooks, 'configure_monitor_host')
    @mock.patch.object(hooks, 'configure_stonith')
    @mock.patch.object(hooks, 'related_units')
    @mock.patch.object(hooks, 'get_cluster_nodes')
    @mock.patch.object(hooks, 'relation_set')
    @mock.patch.object(hooks, 'relation_ids')
    @mock.patch.object(hooks, 'get_corosync_conf')
    @mock.patch('pcmk.commit')
    @mock.patch.object(hooks, 'config')
    @mock.patch.object(hooks, 'parse_data')
    def test_ha_relation_changed_dns_ha_missing(
            self, parse_data, config, commit, get_corosync_conf, relation_ids,
            relation_set, get_cluster_nodes, related_units, configure_stonith,
            configure_monitor_host, configure_cluster_global,
            configure_corosync, is_leader, crm_opt_exists,
            wait_for_pcmk, validate_dns_ha, setup_maas_api,
            trigger_corosync_update_from_leader,
            relation_type, remote_unit):

        def fake_validate():
            raise utils.MAASConfigIncomplete('DNS HA invalid config')

        validate_dns_ha.side_effect = fake_validate
        crm_opt_exists.return_value = False
        is_leader.return_value = True
        related_units.return_value = ['ha/0', 'ha/1', 'ha/2']
        get_cluster_nodes.return_value = ['10.0.3.2', '10.0.3.3', '10.0.3.4']
        relation_ids.return_value = ['ha:1']
        get_corosync_conf.return_value = True
        cfg = {'debug': False,
               'prefer-ipv6': False,
               'corosync_transport': 'udpu',
               'corosync_mcastaddr': 'corosync_mcastaddr',
               'cluster_count': 3,
               'maas_url': 'http://maas/MAAAS/',
               'maas_credentials': None}
        trigger_corosync_update_from_leader.return_value = False
        relation_type.return_value = "hanode"
        remote_unit.return_value = "hacluster/0"

        config.side_effect = lambda key: cfg.get(key)

        rel_get_data = {'locations': {'loc_foo': 'bar rule inf: meh eq 1'},
                        'clones': {'cl_foo': 'res_foo meta interleave=true'},
                        'groups': {'grp_foo': 'res_foo'},
                        'colocations': {'co_foo': 'inf: grp_foo cl_foo'},
                        'resources': {'res_foo_hostname': 'ocf:maas:dns'},
                        'resource_params': {'res_foo_hostname': 'params bar'},
                        'ms': {'ms_foo': 'res_foo meta notify=true'},
                        'orders': {'foo_after': 'inf: res_foo ms_foo'}}

        def fake_parse_data(relid, unit, key):
            return rel_get_data.get(key, {})

        parse_data.side_effect = fake_parse_data
        with mock.patch.object(hooks, 'status_set') as mock_status_set:
            hooks.ha_relation_changed()
            mock_status_set.assert_called_with('blocked',
                                               'DNS HA invalid config')

    @mock.patch.object(hooks, 'remote_unit')
    @mock.patch.object(hooks, 'relation_type')
    @mock.patch.object(hooks, 'trigger_corosync_update_from_leader')
    @mock.patch.object(hooks, 'get_cluster_nodes')
    @mock.patch.object(hooks, 'relation_set')
    @mock.patch.object(hooks, 'relation_ids')
    @mock.patch.object(hooks, 'get_corosync_conf')
    @mock.patch.object(hooks, 'config')
    def test_ha_relation_changed_pacemaker_remote(
            self, config, get_corosync_conf, relation_ids, relation_set,
            get_cluster_nodes, trigger_corosync_update_from_leader,
            relation_type, remote_unit):
        """Test pacemaker-remote-relation-changed.

        Validates that ha_relation_changed() doesn't call
        trigger_corosync_update_from_leader() when called from the
        pacemaker-remote-relation-changed hook. See lp:1920124
        """
        cfg = {'cluster_count': 3}
        config.side_effect = lambda key: cfg.get(key)

        # 2 out of 3 so that the function under test finishes early:
        get_cluster_nodes.return_value = ['10.0.3.2', '10.0.3.3']

        relation_ids.return_value = ['hanode:1']
        get_corosync_conf.return_value = True
        relation_type.return_value = 'pacemaker-remote'
        remote_unit.return_value = 'pacemaker-remote/0'

        hooks.ha_relation_changed()

        relation_set.assert_any_call(relation_id='hanode:1', ready=True)
        trigger_corosync_update_from_leader.assert_not_called()


class TestHooks(test_utils.CharmTestCase):
    TO_PATCH = [
        'config',
        'enable_lsb_services'
    ]

    def setUp(self):
        super(TestHooks, self).setUp(hooks, self.TO_PATCH)
        self.config.side_effect = self.test_config.get

    @mock.patch.object(hooks, 'filter_installed_packages')
    @mock.patch.object(hooks, 'setup_ocf_files')
    @mock.patch.object(hooks, 'apt_install')
    @mock.patch.object(hooks, 'status_set')
    @mock.patch.object(hooks, 'lsb_release')
    def test_install_xenial(self, lsb_release, status_set, apt_install,
                            setup_ocf_files, filter_installed_packages):
        lsb_release.return_value = {
            'DISTRIB_CODENAME': 'xenial'}
        filter_installed_packages.side_effect = lambda x: x
        expected_pkgs = [
            'crmsh', 'corosync', 'pacemaker', 'python3-netaddr', 'ipmitool',
            'libmonitoring-plugin-perl', 'python3-requests-oauthlib']
        hooks.install()
        status_set.assert_called_once_with(
            'maintenance',
            'Installing apt packages')
        filter_installed_packages.assert_called_once_with(expected_pkgs)
        apt_install.assert_called_once_with(expected_pkgs, fatal=True)
        setup_ocf_files.assert_called_once_with()

    @mock.patch.object(hooks, 'filter_installed_packages')
    @mock.patch.object(hooks, 'setup_ocf_files')
    @mock.patch.object(hooks, 'apt_install')
    @mock.patch.object(hooks, 'status_set')
    @mock.patch.object(hooks, 'lsb_release')
    def test_install_bionic(self, lsb_release, status_set, apt_install,
                            setup_ocf_files, filter_installed_packages):
        lsb_release.return_value = {
            'DISTRIB_CODENAME': 'bionic'}
        filter_installed_packages.side_effect = lambda x: x
        expected_pkgs = [
            'crmsh', 'corosync', 'pacemaker', 'python3-netaddr', 'ipmitool',
            'libmonitoring-plugin-perl', 'python3-requests-oauthlib',
            'python3-libmaas']
        hooks.install()
        status_set.assert_called_once_with(
            'maintenance',
            'Installing apt packages')
        filter_installed_packages.assert_called_once_with(expected_pkgs)
        apt_install.assert_called_once_with(expected_pkgs, fatal=True)
        setup_ocf_files.assert_called_once_with()

    @mock.patch('pcmk.set_property')
    @mock.patch.object(hooks, 'is_stonith_configured')
    @mock.patch.object(hooks, 'configure_stonith')
    @mock.patch.object(hooks, 'relation_ids')
    @mock.patch.object(hooks, 'hanode_relation_joined')
    @mock.patch.object(hooks, 'maintenance_mode')
    @mock.patch.object(hooks, 'is_leader')
    @mock.patch.object(hooks, 'update_nrpe_config')
    @mock.patch.object(hooks, 'assess_status_helper')
    @mock.patch('pcmk.commit')
    @mock.patch('pcmk.wait_for_pcmk')
    @mock.patch.object(hooks, 'configure_corosync')
    @mock.patch('os.mkdir')
    @mock.patch('utils.config')
    @mock.patch('utils.rsync')
    @mock.patch('utils.mkdir')
    def test_config_changed(self, mock_mkdir, mock_rsync, mock_config,
                            mock_os_mkdir, mock_configure_corosync,
                            mock_wait_for_pcmk, mock_pcmk_commit,
                            mock_assess_status_helper,
                            mock_update_nrpe_config, mock_is_leader,
                            mock_maintenance_mode,
                            mock_hanode_relation_joined,
                            mock_relation_ids,
                            mock_configure_stonith,
                            mock_is_stonith_configured,
                            mock_set_property):

        mock_is_stonith_configured.return_value = False
        mock_config.side_effect = self.test_config.get
        mock_relation_ids.return_value = ['hanode:1']
        mock_is_leader.return_value = True
        mock_assess_status_helper.return_value = ('active', 'mockmessage')
        hooks.config_changed()
        mock_maintenance_mode.assert_not_called()
        mock_relation_ids.assert_called_with('hanode')
        mock_hanode_relation_joined.assert_called_once_with('hanode:1')
        mock_set_property.assert_called_with('no-quorum-policy', 'stop')

        # enable maintenance
        self.test_config.set_previous('maintenance-mode', False)
        self.test_config.set('maintenance-mode', True)
        hooks.config_changed()
        mock_maintenance_mode.assert_called_with(True)

        # disable maintenance
        self.test_config.set_previous('maintenance-mode', True)
        self.test_config.set('maintenance-mode', False)
        hooks.config_changed()
        mock_maintenance_mode.assert_called_with(False)

        # set no-quorum-policy to ignore
        self.test_config.set('no_quorum_policy', 'ignore')
        hooks.config_changed()
        mock_set_property.assert_called_with('no-quorum-policy', 'ignore')

    @mock.patch.object(hooks, 'needs_maas_dns_migration')
    @mock.patch.object(hooks, 'relation_ids')
    def test_migrate_maas_dns_no_migration(self, relation_ids,
                                           needs_maas_dns_migration):
        needs_maas_dns_migration.return_value = False
        hooks.migrate_maas_dns()
        relation_ids.assert_not_called()

    @mock.patch.object(hooks, 'needs_maas_dns_migration')
    @mock.patch.object(hooks, 'write_maas_dns_address')
    @mock.patch.object(hooks, 'relation_ids')
    @mock.patch.object(hooks, 'related_units')
    @mock.patch.object(hooks, 'parse_data')
    def test_migrate_maas_dns_(self, parse_data, related_units, relation_ids,
                               write_maas_dns_address,
                               needs_maas_dns_migration):
        needs_maas_dns_migration.return_value = True
        related_units.return_value = 'keystone/0'
        relation_ids.return_value = 'ha:4'

        def mock_parse_data(relid, unit, key):
            if key == 'resources':
                return {'res_keystone_public_hostname': 'ocf:maas:dns'}
            elif key == 'resource_params':
                return {'res_keystone_public_hostname':
                        'params fqdn="keystone.maas" ip_address="172.16.0.1"'}
            else:
                raise KeyError("unexpected key {}".format(key))

        parse_data.side_effect = mock_parse_data
        hooks.migrate_maas_dns()
        write_maas_dns_address.assert_called_with(
            "res_keystone_public_hostname", "172.16.0.1")

    @mock.patch.object(hooks, 'get_hostname')
    @mock.patch.object(hooks, 'get_relation_ip')
    @mock.patch.object(hooks, 'relation_set')
    def test_hanode_relation_joined(self,
                                    mock_relation_set,
                                    mock_get_relation_ip,
                                    mock_get_hostname):
        mock_get_hostname.return_value = 'juju-c2419e-0-lxd-1'
        mock_get_relation_ip.return_value = '10.10.10.2'
        hooks.hanode_relation_joined('hanode:1')
        mock_get_relation_ip.assert_called_once_with('hanode')
        mock_relation_set.assert_called_once_with(
            relation_id='hanode:1',
            relation_settings={
                'private-address': '10.10.10.2',
                'hostname': 'juju-c2419e-0-lxd-1'})

    @mock.patch.object(hooks, 'ha_relation_changed')
    @mock.patch.object(hooks, 'is_waiting_unit_series_upgrade_set')
    @mock.patch.object(hooks, 'set_waiting_unit_series_upgrade')
    @mock.patch.object(hooks, 'disable_ha_services')
    @mock.patch.object(hooks, 'get_series_upgrade_notifications')
    @mock.patch.object(hooks, 'lsb_release')
    def test_hanode_relation_changed(self, lsb_release,
                                     get_series_upgrade_notifications,
                                     disable_ha_services,
                                     set_waiting_unit_series_upgrade,
                                     is_waiting_unit_series_upgrade_set,
                                     ha_relation_changed):
        lsb_release.return_value = {
            'DISTRIB_CODENAME': 'trusty'}
        get_series_upgrade_notifications.return_value = {
            'unit1': 'xenial'}
        is_waiting_unit_series_upgrade_set.return_value = True
        hooks.hanode_relation_changed()
        disable_ha_services.assert_called_once_with()
        set_waiting_unit_series_upgrade.assert_called_once_with()
        self.assertFalse(ha_relation_changed.called)

    @mock.patch.object(hooks, 'ha_relation_changed')
    @mock.patch.object(hooks, 'is_waiting_unit_series_upgrade_set')
    @mock.patch.object(hooks, 'set_waiting_unit_series_upgrade')
    @mock.patch.object(hooks, 'disable_ha_services')
    @mock.patch.object(hooks, 'get_series_upgrade_notifications')
    @mock.patch.object(hooks, 'lsb_release')
    def test_hanode_relation_changed_no_up(self, lsb_release,
                                           get_series_upgrade_notifications,
                                           disable_ha_services,
                                           set_waiting_unit_series_upgrade,
                                           is_waiting_unit_series_upgrade_set,
                                           ha_relation_changed):
        lsb_release.return_value = {
            'DISTRIB_CODENAME': 'trusty'}
        get_series_upgrade_notifications.return_value = {}
        is_waiting_unit_series_upgrade_set.return_value = False
        hooks.hanode_relation_changed()
        ha_relation_changed.assert_called_once_with()

    @mock.patch.object(hooks, 'apt_mark')
    @mock.patch.object(hooks, 'is_waiting_unit_series_upgrade_set')
    @mock.patch.object(hooks, 'set_unit_upgrading')
    @mock.patch.object(hooks, 'is_unit_paused_set')
    @mock.patch.object(hooks, 'pause_unit')
    @mock.patch.object(hooks, 'notify_peers_of_series_upgrade')
    def test_series_upgrade_prepare(self, notify_peers_of_series_upgrade,
                                    pause_unit, is_unit_paused_set,
                                    set_unit_upgrading,
                                    is_waiting_unit_series_upgrade_set,
                                    apt_mark):
        is_unit_paused_set.return_value = False
        is_waiting_unit_series_upgrade_set.return_value = False
        hooks.series_upgrade_prepare()
        set_unit_upgrading.assert_called_once_with()
        pause_unit.assert_called_once_with()
        notify_peers_of_series_upgrade.assert_called_once_with()
        apt_mark.assert_called_once_with('crmsh', 'manual')

    @mock.patch.object(hooks, 'clear_unit_paused')
    @mock.patch.object(hooks, 'clear_unit_upgrading')
    @mock.patch.object(hooks, 'config_changed')
    @mock.patch.object(hooks, 'enable_ha_services')
    @mock.patch.object(hooks, 'resume_unit')
    @mock.patch.object(hooks, 'clear_series_upgrade_notification')
    @mock.patch.object(hooks, 'clear_waiting_unit_series_upgrade')
    def test_series_upgrade_complete(self, clear_waiting_unit_series_upgrade,
                                     clear_series_upgrade_notification,
                                     resume_unit, enable_ha_services,
                                     config_changed, clear_unit_upgrading,
                                     clear_unit_paused):
        hooks.series_upgrade_complete()
        clear_waiting_unit_series_upgrade.assert_called_once_with()
        clear_series_upgrade_notification.assert_called_once_with()
        resume_unit.assert_called_once_with()
        enable_ha_services.assert_called_once_with()
        config_changed.assert_called_once_with()
        clear_unit_upgrading.assert_called_once_with()
        clear_unit_paused.assert_called_once_with()

    @mock.patch.object(hooks, 'get_pcmkr_key')
    @mock.patch.object(hooks, 'relation_ids')
    @mock.patch.object(hooks, 'relation_set')
    def test_send_auth_key(self, relation_set, relation_ids, get_pcmkr_key):
        relation_ids.return_value = ['relid1']
        get_pcmkr_key.return_value = 'pcmkrkey'
        hooks.send_auth_key()
        relation_set.assert_called_once_with(
            relation_id='relid1',
            **{'pacemaker-key': 'pcmkrkey'})

    @mock.patch.object(hooks, 'get_distrib_codename')
    @mock.patch.object(hooks, 'apt_install')
    @mock.patch('hooks.nrpe', autospec=True)
    @mock.patch('hooks.os')
    @mock.patch('hooks.glob')
    @mock.patch.object(hooks, 'status_set')
    @mock.patch.object(hooks, 'config')
    def test_update_nrpe_config(self, config, status_set, mock_glob, mock_os,
                                nrpe, apt_install, mock_distrib_codename):

        cfg = {'failed_actions_threshold': 0,
               'res_failcount_warn': 0,
               'res_failcount_crit': 5}
        config.side_effect = lambda key: cfg.get(key)

        mock_distrib_codename.side_effect = ['bionic', 'eoan', 'focal']
        ring_check_expected = iter([True, False, False])

        # Set up valid values to try for 'failed_actions_alert_type'
        alert_type_params = ["IGNore", "warning", "CRITICAL"]
        for alert_type in alert_type_params:
            cfg['failed_actions_alert_type'] = alert_type
            nrpe.get_nagios_hostname.return_value = 'localhost'
            nrpe.get_nagios_unit_name.return_value = 'nagios/1'
            mock_nrpe_setup = mock.MagicMock()
            nrpe.NRPE.return_value = mock_nrpe_setup

            hooks.update_nrpe_config()

            nrpe.NRPE.assert_called_once_with(hostname='localhost')
            apt_install.assert_called_once_with('python-dbus')

            check_crm_cmd = ('check_crm -s --failedactions={} '
                             '--failcount-warn={} --failcount-crit={}'.format(
                                 cfg['failed_actions_alert_type'].lower(),
                                 cfg['res_failcount_warn'],
                                 cfg['res_failcount_crit']))

            if next(ring_check_expected):
                mock_nrpe_setup.add_check.assert_any_call(
                    shortname='corosync_rings',
                    description='Check Corosync rings nagios/1',
                    check_cmd='check_corosync_rings')
            else:
                mock_nrpe_setup.remove_check.assert_any_call(
                    shortname='corosync_rings',
                    description='Check Corosync rings nagios/1',
                    check_cmd='check_corosync_rings')
            mock_nrpe_setup.add_check.assert_any_call(
                shortname='crm_status',
                description='Check crm status nagios/1',
                check_cmd=check_crm_cmd)

            mock_nrpe_setup.add_check.assert_any_call(
                shortname='corosync_proc',
                description='Check Corosync process nagios/1',
                check_cmd='check_procs -c 1:1 -C corosync')
            mock_nrpe_setup.add_check.assert_any_call(
                shortname='pacemakerd_proc',
                description='Check Pacemakerd process nagios/1',
                check_cmd='check_procs -c 1:1 -C pacemakerd')
            mock_nrpe_setup.write.assert_called_once()

            nrpe.reset_mock()
            apt_install.reset_mock()

        # Check unsupported case for failed_actions_alert_type
        cfg['failed_actions_alert_type'] = 'unsupported'
        cfg['failed_actions_threshold'] = 1
        hooks.update_nrpe_config()
        valid_alerts = ['ignore', 'warning', 'critical']
        status_set.assert_called_once_with('blocked',
                                           'The value of option '
                                           'failed_actions_alert_type must be '
                                           'among {}'.format(valid_alerts))
        status_set.reset_mock()

        # Check unsupported case for failed_actions_threshold
        cfg['failed_actions_alert_type'] = 'ignore'
        cfg['failed_actions_threshold'] = -5
        hooks.update_nrpe_config()
        status_set.assert_called_once_with('blocked',
                                           'The value of option failed_'
                                           'actions_threshold must be a '
                                           'positive integer')
