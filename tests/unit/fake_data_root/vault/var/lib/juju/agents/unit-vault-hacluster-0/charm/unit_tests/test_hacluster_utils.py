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

import contextlib
import json
from unittest import mock
import os
import re
import shutil
import subprocess
import tempfile
import unittest

import utils
import pcmk


def write_file(path, content, *args, **kwargs):
    with open(path, 'wt') as f:
        f.write(content)
        f.flush()


@mock.patch.object(utils, 'log', lambda *args, **kwargs: None)
@mock.patch.object(utils, 'write_file', write_file)
class UtilsTestCaseWriteTmp(unittest.TestCase):

    def setUp(self):
        self.tmpdir = tempfile.mkdtemp()
        utils.COROSYNC_CONF = os.path.join(self.tmpdir, 'corosync.conf')

    def tearDown(self):
        shutil.rmtree(self.tmpdir)

    @mock.patch.object(utils, 'get_ha_nodes', lambda *args: {'1': '10.0.0.1'})
    @mock.patch.object(utils, 'relation_get')
    @mock.patch.object(utils, 'related_units')
    @mock.patch.object(utils, 'relation_ids')
    @mock.patch.object(utils, 'get_network_address')
    @mock.patch.object(utils, 'config')
    def check_debug(self, enabled, mock_config, get_network_address,
                    relation_ids, related_units, relation_get):
        cfg = {'debug': enabled,
               'prefer-ipv6': False,
               'corosync_mcastport': '1234',
               'corosync_transport': 'udpu',
               'corosync_mcastaddr': 'corosync_mcastaddr'}

        def c(k):
            return cfg.get(k)

        mock_config.side_effect = c
        get_network_address.return_value = "127.0.0.1"
        relation_ids.return_value = ['foo:1']
        related_units.return_value = ['unit-machine-0']
        relation_get.return_value = 'iface'

        conf = utils.get_corosync_conf()

        if enabled:
            self.assertEqual(conf['debug'], enabled)
        else:
            self.assertFalse('debug' in conf)

        self.assertTrue(utils.emit_corosync_conf())

        with open(utils.COROSYNC_CONF, 'rt') as fd:
            content = fd.read()
            if enabled:
                pattern = 'debug: on\n'
            else:
                pattern = 'debug: off\n'

            matches = re.findall(pattern, content, re.M)
            self.assertEqual(len(matches), 2, str(matches))

    def test_debug_on(self):
        self.check_debug(True)

    def test_debug_off(self):
        self.check_debug(False)


class UtilsTestCase(unittest.TestCase):
    def _testdata(self, filename):
        return os.path.join(os.path.dirname(__file__),
                            'testdata',
                            filename)

    @mock.patch.object(utils, 'config')
    def test_get_transport(self, mock_config):
        mock_config.return_value = 'udp'
        self.assertEqual('udp', utils.get_transport())

        mock_config.return_value = 'udpu'
        self.assertEqual('udpu', utils.get_transport())

        mock_config.return_value = 'hafu'
        self.assertRaises(ValueError, utils.get_transport)

    def test_nulls(self):
        self.assertEqual(utils.nulls({'a': '', 'b': None, 'c': False}),
                         ['a', 'b'])

    @mock.patch.object(utils, 'local_unit', lambda *args: 'hanode/0')
    @mock.patch.object(utils, 'get_ipv6_addr')
    @mock.patch.object(utils, 'get_host_ip')
    @mock.patch.object(utils.utils, 'is_ipv6', lambda *args: None)
    @mock.patch.object(utils, 'get_corosync_id', lambda u: "%s-cid" % (u))
    @mock.patch.object(utils, 'peer_ips', lambda *args, **kwargs:
                       {'hanode/1': '10.0.0.2'})
    @mock.patch.object(utils, 'unit_get')
    @mock.patch.object(utils, 'config')
    def test_get_ha_nodes(self, mock_config, mock_unit_get, mock_get_host_ip,
                          mock_get_ipv6_addr):
        mock_get_host_ip.side_effect = lambda host: host

        def unit_get(key):
            return {'private-address': '10.0.0.1'}.get(key)

        mock_unit_get.side_effect = unit_get

        def config(key):
            return {'prefer-ipv6': False}.get(key)

        mock_config.side_effect = config
        nodes = utils.get_ha_nodes()
        self.assertEqual(nodes, {'hanode/0-cid': '10.0.0.1',
                                 'hanode/1-cid': '10.0.0.2'})

        self.assertTrue(mock_get_host_ip.called)
        self.assertFalse(mock_get_ipv6_addr.called)

    @mock.patch.object(utils, 'local_unit', lambda *args: 'hanode/0')
    @mock.patch.object(utils, 'get_ipv6_addr')
    @mock.patch.object(utils, 'get_host_ip')
    @mock.patch.object(utils.utils, 'is_ipv6')
    @mock.patch.object(utils, 'get_corosync_id', lambda u: "%s-cid" % (u))
    @mock.patch.object(utils, 'peer_ips', lambda *args, **kwargs:
                       {'hanode/1': '2001:db8:1::2'})
    @mock.patch.object(utils, 'unit_get')
    @mock.patch.object(utils, 'config')
    def test_get_ha_nodes_ipv6(self, mock_config, mock_unit_get, mock_is_ipv6,
                               mock_get_host_ip, mock_get_ipv6_addr):
        mock_get_ipv6_addr.return_value = '2001:db8:1::1'
        mock_get_host_ip.side_effect = lambda host: host

        def unit_get(key):
            return {'private-address': '10.0.0.1'}.get(key)

        mock_unit_get.side_effect = unit_get

        def config(key):
            return {'prefer-ipv6': True}.get(key)

        mock_config.side_effect = config
        nodes = utils.get_ha_nodes()
        self.assertEqual(nodes, {'hanode/0-cid': '2001:db8:1::1',
                                 'hanode/1-cid': '2001:db8:1::2'})

        self.assertFalse(mock_get_host_ip.called)
        self.assertTrue(mock_get_ipv6_addr.called)

    @mock.patch.object(utils, 'assert_charm_supports_dns_ha')
    @mock.patch.object(utils, 'config')
    def test_validate_dns_ha_valid(self, config,
                                   assert_charm_supports_dns_ha):
        cfg = {'maas_url': 'http://maas/MAAAS/',
               'maas_credentials': 'secret'}
        config.side_effect = lambda key: cfg.get(key)

        self.assertTrue(utils.validate_dns_ha())
        self.assertTrue(assert_charm_supports_dns_ha.called)

    @mock.patch.object(utils, 'assert_charm_supports_dns_ha')
    @mock.patch.object(utils, 'status_set')
    @mock.patch.object(utils, 'config')
    def test_validate_dns_ha_invalid(self, config, status_set,
                                     assert_charm_supports_dns_ha):
        cfg = {'maas_url': 'http://maas/MAAAS/',
               'maas_credentials': None}
        config.side_effect = lambda key: cfg.get(key)

        self.assertRaises(utils.MAASConfigIncomplete,
                          lambda: utils.validate_dns_ha())
        self.assertTrue(assert_charm_supports_dns_ha.called)
        status_set.assert_not_called()

    @mock.patch.object(utils, 'apt_install')
    @mock.patch.object(utils, 'apt_update')
    @mock.patch.object(utils, 'add_source')
    @mock.patch.object(utils, 'config')
    def test_setup_maas_api(self, config, add_source, apt_update, apt_install):
        cfg = {'maas_source': 'ppa:maas/stable',
               'maas_source_key': None}
        config.side_effect = lambda key: cfg.get(key)

        utils.setup_maas_api()
        add_source.assert_called_with(cfg['maas_source'],
                                      cfg['maas_source_key'])
        self.assertTrue(apt_install.called)

    @mock.patch('os.path.isfile')
    def test_ocf_file_exists(self, isfile_mock):
        RES_NAME = 'res_ceilometer_agent_central'
        resources = {RES_NAME: ('ocf:openstack:ceilometer-agent-central')}
        utils.ocf_file_exists(RES_NAME, resources)
        wish = '/usr/lib/ocf/resource.d/openstack/ceilometer-agent-central'
        isfile_mock.assert_called_once_with(wish)

    @mock.patch.object(subprocess, 'check_output')
    @mock.patch.object(subprocess, 'call')
    def test_kill_legacy_ocf_daemon_process(self, call_mock,
                                            check_output_mock):
        ps_output = b'''
          PID CMD
          6863 sshd: ubuntu@pts/7
          11109 /usr/bin/python /usr/bin/ceilometer-agent-central --config
        '''
        check_output_mock.return_value = ps_output
        utils.kill_legacy_ocf_daemon_process('res_ceilometer_agent_central')
        call_mock.assert_called_once_with(['sudo', 'kill', '-9', '11109'])

    @mock.patch.object(pcmk, 'wait_for_pcmk')
    def test_try_pcmk_wait(self, mock_wait_for_pcmk):
        # Returns OK
        mock_wait_for_pcmk.side_effect = None
        self.assertEqual(None, utils.try_pcmk_wait())

        # Raises Exception
        mock_wait_for_pcmk.side_effect = pcmk.ServicesNotUp
        with self.assertRaises(pcmk.ServicesNotUp):
            utils.try_pcmk_wait()

    @mock.patch.object(pcmk, 'wait_for_pcmk')
    @mock.patch.object(utils, 'service_running')
    def test_services_running(self, mock_service_running,
                              mock_wait_for_pcmk):
        # OS not running
        mock_service_running.return_value = False
        self.assertFalse(utils.services_running())

        # Functional not running
        mock_service_running.return_value = True
        mock_wait_for_pcmk.side_effect = pcmk.ServicesNotUp
        with self.assertRaises(pcmk.ServicesNotUp):
            utils.services_running()

        # All running
        mock_service_running.return_value = True
        mock_wait_for_pcmk.side_effect = None
        mock_wait_for_pcmk.return_value = True
        self.assertTrue(utils.services_running())

    @mock.patch.object(pcmk, 'wait_for_pcmk')
    @mock.patch.object(utils, 'restart_corosync')
    def test_validated_restart_corosync(self, mock_restart_corosync,
                                        mock_wait_for_pcmk):
        # Services are down
        mock_restart_corosync.mock_calls = []
        mock_restart_corosync.return_value = False
        with self.assertRaises(pcmk.ServicesNotUp):
            utils.validated_restart_corosync(retries=3)
        self.assertEqual(3, len(mock_restart_corosync.mock_calls))

        # Services are up
        mock_restart_corosync.mock_calls = []
        mock_restart_corosync.return_value = True
        utils.validated_restart_corosync(retries=10)
        self.assertEqual(1, len(mock_restart_corosync.mock_calls))

    @mock.patch.object(utils, 'is_unit_paused_set')
    @mock.patch.object(utils, 'services_running')
    @mock.patch.object(utils, 'service_start')
    @mock.patch.object(utils, 'service_stop')
    @mock.patch.object(utils, 'service_running')
    def test_restart_corosync(self, mock_service_running,
                              mock_service_stop, mock_service_start,
                              mock_services_running, mock_is_unit_paused_set):
        # PM up, services down
        mock_service_running.return_value = True
        mock_is_unit_paused_set.return_value = False
        mock_services_running.return_value = False
        self.assertFalse(utils.restart_corosync())
        mock_service_stop.assert_has_calls([mock.call('pacemaker'),
                                            mock.call('corosync')])
        mock_service_start.assert_has_calls([mock.call('corosync'),
                                            mock.call('pacemaker')])

        # PM already down, services down
        mock_service_running.return_value = False
        mock_is_unit_paused_set.return_value = False
        mock_services_running.return_value = False
        self.assertFalse(utils.restart_corosync())
        mock_service_stop.assert_has_calls([mock.call('corosync')])
        mock_service_start.assert_has_calls([mock.call('corosync'),
                                            mock.call('pacemaker')])

        # PM already down, services up
        mock_service_running.return_value = True
        mock_is_unit_paused_set.return_value = False
        mock_services_running.return_value = True
        self.assertTrue(utils.restart_corosync())
        mock_service_stop.assert_has_calls([mock.call('pacemaker'),
                                            mock.call('corosync')])
        mock_service_start.assert_has_calls([mock.call('corosync'),
                                            mock.call('pacemaker')])

    @mock.patch.object(subprocess, 'check_call')
    @mock.patch.object(utils.os, 'mkdir')
    @mock.patch.object(utils.os.path, 'exists')
    @mock.patch.object(utils, 'render_template')
    @mock.patch.object(utils, 'write_file')
    @mock.patch.object(utils, 'is_unit_paused_set')
    @mock.patch.object(utils, 'config')
    def test_emit_systemd_overrides_file(self, mock_config,
                                         mock_is_unit_paused_set,
                                         mock_write_file, mock_render_template,
                                         mock_path_exists,
                                         mock_mkdir, mock_check_call):

        # Normal values
        cfg = {'service_stop_timeout': 30,
               'service_start_timeout': 90}
        mock_config.side_effect = lambda key: cfg.get(key)

        mock_is_unit_paused_set.return_value = True
        mock_path_exists.return_value = True
        utils.emit_systemd_overrides_file()
        self.assertEqual(2, len(mock_write_file.mock_calls))
        mock_render_template.assert_has_calls(
            [mock.call('systemd-overrides.conf', cfg),
             mock.call('systemd-overrides.conf', cfg)])
        mock_check_call.assert_has_calls([mock.call(['systemctl',
                                                     'daemon-reload'])])
        mock_write_file.mock_calls = []
        mock_render_template.mock_calls = []
        mock_check_call.mock_calls = []

        # Disable timeout
        cfg = {'service_stop_timeout': -1,
               'service_start_timeout': -1}
        expected_cfg = {'service_stop_timeout': 'infinity',
                        'service_start_timeout': 'infinity'}
        mock_config.side_effect = lambda key: cfg.get(key)
        mock_is_unit_paused_set.return_value = True
        mock_path_exists.return_value = True
        utils.emit_systemd_overrides_file()
        self.assertEqual(2, len(mock_write_file.mock_calls))
        mock_render_template.assert_has_calls(
            [mock.call('systemd-overrides.conf', expected_cfg),
             mock.call('systemd-overrides.conf', expected_cfg)])
        mock_check_call.assert_has_calls([mock.call(['systemctl',
                                                     'daemon-reload'])])

    @mock.patch('pcmk.set_property')
    @mock.patch('pcmk.get_property')
    def test_maintenance_mode(self, mock_get_property, mock_set_property):
        # enable maintenance-mode
        mock_get_property.return_value = 'false\n'
        utils.maintenance_mode(True)
        mock_get_property.assert_called_with('maintenance-mode')
        mock_set_property.assert_called_with('maintenance-mode', 'true')
        mock_get_property.reset_mock()
        mock_set_property.reset_mock()
        mock_get_property.return_value = 'true\n'
        utils.maintenance_mode(True)
        mock_get_property.assert_called_with('maintenance-mode')
        mock_set_property.assert_not_called()

        # disable maintenance-mode
        mock_get_property.return_value = 'true\n'
        utils.maintenance_mode(False)
        mock_get_property.assert_called_with('maintenance-mode')
        mock_set_property.assert_called_with('maintenance-mode', 'false')
        mock_get_property.reset_mock()
        mock_set_property.reset_mock()
        mock_get_property.return_value = 'false\n'
        utils.maintenance_mode(False)
        mock_get_property.assert_called_with('maintenance-mode')
        mock_set_property.assert_not_called()

    @mock.patch('subprocess.check_call')
    def test_needs_maas_dns_migration(self, check_call):
        ret = utils.needs_maas_dns_migration()
        self.assertEqual(True, ret)

        check_call.side_effect = subprocess.CalledProcessError(1, '')
        ret = utils.needs_maas_dns_migration()
        self.assertEqual(False, ret)

    def test_get_ip_addr_from_resource_params(self):
        param_str = 'params fqdn="keystone.maas" ip_address="{}" '
        for addr in ("172.16.0.4", "2001:0db8:85a3:0000:0000:8a2e:0370:7334"):
            ip = utils.get_ip_addr_from_resource_params(param_str.format(addr))
            self.assertEqual(addr, ip)

        ip = utils.get_ip_addr_from_resource_params("no_ip_addr")
        self.assertEqual(None, ip)

    @mock.patch.object(utils, 'write_file')
    @mock.patch.object(utils, 'mkdir')
    def test_write_maas_dns_address(self, mkdir, write_file):
        utils.write_maas_dns_address("res_keystone_public_hostname",
                                     "172.16.0.1")
        mkdir.assert_called_once_with("/etc/maas_dns")
        write_file.assert_called_once_with(
            "/etc/maas_dns/res_keystone_public_hostname", content="172.16.0.1")

    @mock.patch.object(utils, 'relation_get')
    def test_parse_data_legacy(self, relation_get):
        _rel_data = {
            'testkey': repr({'test': 1})
        }
        relation_get.side_effect = lambda key, relid, unit: _rel_data.get(key)
        self.assertEqual(utils.parse_data('hacluster:1',
                                          'neutron-api/0',
                                          'testkey'),
                         {'test': 1})
        relation_get.assert_has_calls([
            mock.call('json_testkey', 'neutron-api/0', 'hacluster:1'),
            mock.call('testkey', 'neutron-api/0', 'hacluster:1'),
        ])

    @mock.patch('pcmk.commit')
    @mock.patch.object(utils, 'configure_pacemaker_remote_stonith_resource')
    def test_configure_stonith_no_maas(
            self,
            mock_cfg_pcmkr_rstonith_res,
            mock_commit):
        # Without MAAS this function will return no resource:
        mock_cfg_pcmkr_rstonith_res.return_value = []

        utils.configure_stonith()

        mock_commit.assert_called_once_with(
            'crm configure property stonith-enabled=false',
            failure_is_fatal=False)

    @mock.patch.object(utils, 'relation_get')
    def test_parse_data_json(self, relation_get):
        _rel_data = {
            'json_testkey': json.dumps({'test': 1}),
            'testkey': repr({'test': 1})
        }
        relation_get.side_effect = lambda key, relid, unit: _rel_data.get(key)
        self.assertEqual(utils.parse_data('hacluster:1',
                                          'neutron-api/0',
                                          'testkey'),
                         {'test': 1})
        # NOTE(jamespage): as json is the preferred format, the call for
        #                  testkey should not occur.
        relation_get.assert_has_calls([
            mock.call('json_testkey', 'neutron-api/0', 'hacluster:1'),
        ])

    @mock.patch.object(utils, 'render_template')
    @mock.patch.object(utils.os.path, 'isdir')
    @mock.patch.object(utils.os, 'mkdir')
    @mock.patch.object(utils, 'write_file')
    @mock.patch.object(utils, 'config')
    def test_emit_base_conf(self, config, write_file, mkdir, isdir,
                            render_template):
        cfg = {
            'corosync_key': 'Y29yb3N5bmNrZXkK',
            'pacemaker_key': 'cGFjZW1ha2Vya2V5Cg==',
        }
        config.side_effect = lambda x: cfg.get(x)
        isdir.return_value = False
        render = {
            'corosync': 'corosync etc default config',
            'hacluster.acl': 'hacluster acl file',
        }
        render_template.side_effect = lambda x, y: render[x]
        expect_write_calls = [
            mock.call(
                content='corosync etc default config',
                path='/etc/default/corosync'),
            mock.call(
                content='hacluster acl file',
                path='/etc/corosync/uidgid.d/hacluster'),
            mock.call(
                content=b'corosynckey\n',
                path='/etc/corosync/authkey',
                perms=256),
            mock.call(
                content=b'pacemakerkey\n',
                path='/etc/pacemaker/authkey',
                perms=288,
                group='haclient',
                owner='root')
        ]
        expect_render_calls = [
            mock.call(
                'corosync',
                {'corosync_enabled': 'yes'}),
            mock.call(
                'hacluster.acl',
                {})
        ]
        mkdir_calls = [
            mock.call('/etc/corosync/uidgid.d'),
            mock.call('/etc/pacemaker'),
        ]
        self.assertTrue(utils.emit_base_conf())
        write_file.assert_has_calls(expect_write_calls)
        render_template.assert_has_calls(expect_render_calls)
        mkdir.assert_has_calls(mkdir_calls)

    @mock.patch.object(utils, 'render_template')
    @mock.patch.object(utils.os.path, 'isdir')
    @mock.patch.object(utils.os, 'mkdir')
    @mock.patch.object(utils, 'write_file')
    @mock.patch.object(utils, 'config')
    def test_emit_base_conf_no_pcmkr_key(self, config, write_file, mkdir,
                                         isdir, render_template):
        cfg = {
            'corosync_key': 'Y29yb3N5bmNrZXkK',
        }
        config.side_effect = lambda x: cfg.get(x)
        isdir.return_value = False
        render = {
            'corosync': 'corosync etc default config',
            'hacluster.acl': 'hacluster acl file',
        }
        render_template.side_effect = lambda x, y: render[x]
        expect_write_calls = [
            mock.call(
                content='corosync etc default config',
                path='/etc/default/corosync'),
            mock.call(
                content='hacluster acl file',
                path='/etc/corosync/uidgid.d/hacluster'),
            mock.call(
                content=b'corosynckey\n',
                path='/etc/corosync/authkey',
                perms=256),
            mock.call(
                content=b'corosynckey\n',
                path='/etc/pacemaker/authkey',
                perms=288,
                group='haclient',
                owner='root')
        ]
        expect_render_calls = [
            mock.call(
                'corosync',
                {'corosync_enabled': 'yes'}),
            mock.call(
                'hacluster.acl',
                {})
        ]
        mkdir_calls = [
            mock.call('/etc/corosync/uidgid.d'),
            mock.call('/etc/pacemaker'),
        ]
        self.assertTrue(utils.emit_base_conf())
        write_file.assert_has_calls(expect_write_calls)
        render_template.assert_has_calls(expect_render_calls)
        mkdir.assert_has_calls(mkdir_calls)

    @mock.patch.object(utils, 'render_template')
    @mock.patch.object(utils.os.path, 'isdir')
    @mock.patch.object(utils.os, 'mkdir')
    @mock.patch.object(utils, 'write_file')
    @mock.patch.object(utils, 'config')
    def test_emit_base_conf_no_coro_key(self, config, write_file, mkdir,
                                        isdir, render_template):
        cfg = {
        }
        config.side_effect = lambda x: cfg.get(x)
        isdir.return_value = False
        render = {
            'corosync': 'corosync etc default config',
            'hacluster.acl': 'hacluster acl file',
        }
        render_template.side_effect = lambda x, y: render[x]
        expect_write_calls = [
            mock.call(
                content='corosync etc default config',
                path='/etc/default/corosync'),
            mock.call(
                content='hacluster acl file',
                path='/etc/corosync/uidgid.d/hacluster'),
        ]
        expect_render_calls = [
            mock.call(
                'corosync',
                {'corosync_enabled': 'yes'}),
            mock.call(
                'hacluster.acl',
                {})
        ]
        mkdir_calls = [
            mock.call('/etc/corosync/uidgid.d'),
            mock.call('/etc/pacemaker'),
        ]
        self.assertFalse(utils.emit_base_conf())
        write_file.assert_has_calls(expect_write_calls)
        render_template.assert_has_calls(expect_render_calls)
        mkdir.assert_has_calls(mkdir_calls)

    @mock.patch.object(utils, 'relation_get')
    @mock.patch.object(utils, 'related_units')
    @mock.patch.object(utils, 'relation_ids')
    def test_need_resources_on_remotes_all_false(self, relation_ids,
                                                 related_units, relation_get):
        rdata = {
            'pacemaker-remote:49': {
                'pacemaker-remote/0': {'enable-resources': "false"},
                'pacemaker-remote/1': {'enable-resources': "false"},
                'pacemaker-remote/2': {'enable-resources': "false"}}}

        relation_ids.side_effect = lambda x: rdata.keys()
        related_units.side_effect = lambda x: rdata[x].keys()
        relation_get.side_effect = lambda x, y, z: rdata[z][y].get(x)
        self.assertFalse(utils.need_resources_on_remotes())

    @mock.patch.object(utils, 'relation_get')
    @mock.patch.object(utils, 'related_units')
    @mock.patch.object(utils, 'relation_ids')
    def test_need_resources_on_remotes_all_true(self, relation_ids,
                                                related_units,
                                                relation_get):
        rdata = {
            'pacemaker-remote:49': {
                'pacemaker-remote/0': {'enable-resources': "true"},
                'pacemaker-remote/1': {'enable-resources': "true"},
                'pacemaker-remote/2': {'enable-resources': "true"}}}

        relation_ids.side_effect = lambda x: rdata.keys()
        related_units.side_effect = lambda x: rdata[x].keys()
        relation_get.side_effect = lambda x, y, z: rdata[z][y].get(x)
        self.assertTrue(utils.need_resources_on_remotes())

    @mock.patch.object(utils, 'relation_get')
    @mock.patch.object(utils, 'related_units')
    @mock.patch.object(utils, 'relation_ids')
    def test_need_resources_on_remotes_mix(self, relation_ids, related_units,
                                           relation_get):
        rdata = {
            'pacemaker-remote:49': {
                'pacemaker-remote/0': {'enable-resources': "true"},
                'pacemaker-remote/1': {'enable-resources': "false"},
                'pacemaker-remote/2': {'enable-resources': "true"}}}

        relation_ids.side_effect = lambda x: rdata.keys()
        related_units.side_effect = lambda x: rdata[x].keys()
        relation_get.side_effect = lambda x, y, z: rdata[z][y].get(x)
        with self.assertRaises(ValueError):
            self.assertTrue(utils.need_resources_on_remotes())

    @mock.patch.object(utils, 'relation_get')
    @mock.patch.object(utils, 'related_units')
    @mock.patch.object(utils, 'relation_ids')
    def test_need_resources_on_remotes_missing(self, relation_ids,
                                               related_units,
                                               relation_get):
        rdata = {
            'pacemaker-remote:49': {
                'pacemaker-remote/0': {},
                'pacemaker-remote/1': {},
                'pacemaker-remote/2': {}}}

        relation_ids.side_effect = lambda x: rdata.keys()
        related_units.side_effect = lambda x: rdata[x].keys()
        relation_get.side_effect = lambda x, y, z: rdata[z][y].get(x, None)
        with self.assertRaises(ValueError):
            self.assertTrue(utils.need_resources_on_remotes())

    @mock.patch.object(utils, 'need_resources_on_remotes')
    @mock.patch('pcmk.commit')
    def test_set_cluster_symmetry_true(self, commit,
                                       need_resources_on_remotes):
        need_resources_on_remotes.return_value = True
        utils.set_cluster_symmetry()
        commit.assert_called_once_with(
            'crm configure property symmetric-cluster=true',
            failure_is_fatal=True)

    @mock.patch.object(utils, 'need_resources_on_remotes')
    @mock.patch('pcmk.commit')
    def test_set_cluster_symmetry_false(self, commit,
                                        need_resources_on_remotes):
        need_resources_on_remotes.return_value = False
        utils.set_cluster_symmetry()
        commit.assert_called_once_with(
            'crm configure property symmetric-cluster=false',
            failure_is_fatal=True)

    @mock.patch.object(utils, 'need_resources_on_remotes')
    @mock.patch('pcmk.commit')
    def test_set_cluster_symmetry_unknown(self, commit,
                                          need_resources_on_remotes):
        need_resources_on_remotes.side_effect = ValueError()
        utils.set_cluster_symmetry()
        self.assertFalse(commit.called)

    @mock.patch('pcmk.crm_update_location')
    def test_add_score_location_rule(self, crm_update_location):
        # Check no update required
        utils.add_score_location_rule('res1', 'juju-lxd-0', 0)
        crm_update_location.assert_called_once_with(
            'loc-res1-juju-lxd-0',
            'res1',
            0,
            'juju-lxd-0')

    @mock.patch('pcmk.commit')
    @mock.patch('pcmk.crm_opt_exists')
    @mock.patch('pcmk.list_nodes')
    def test_add_location_rules_for_local_nodes(self, list_nodes,
                                                crm_opt_exists, commit):
        existing_resources = ['loc-res1-node1']
        list_nodes.return_value = ['node1', 'node2']
        crm_opt_exists.side_effect = lambda x: x in existing_resources
        utils.add_location_rules_for_local_nodes('res1')
        commit.assert_called_once_with(
            'crm -w -F configure location loc-res1-node2 res1 0: node2',
            failure_is_fatal=True)

    @mock.patch.object(utils, 'add_score_location_rule')
    @mock.patch('pcmk.list_nodes')
    def test_add_location_rules_for_pacemaker_remotes(self, list_nodes,
                                                      add_score_location_rule):
        list_nodes.return_value = ['node1', 'node2', 'node3']
        utils.add_location_rules_for_pacemaker_remotes([
            'res1',
            'res2',
            'res3',
            'res4',
            'res5'])
        expect = [
            mock.call('res1', 'node1', 200),
            mock.call('res1', 'node2', 0),
            mock.call('res1', 'node3', 0),
            mock.call('res2', 'node1', 0),
            mock.call('res2', 'node2', 200),
            mock.call('res2', 'node3', 0),
            mock.call('res3', 'node1', 0),
            mock.call('res3', 'node2', 0),
            mock.call('res3', 'node3', 200),
            mock.call('res4', 'node1', 200),
            mock.call('res4', 'node2', 0),
            mock.call('res4', 'node3', 0),
            mock.call('res5', 'node1', 0),
            mock.call('res5', 'node2', 200),
            mock.call('res5', 'node3', 0)]
        add_score_location_rule.assert_has_calls(expect)

    @mock.patch('pcmk.is_resource_present')
    @mock.patch('pcmk.commit')
    def test_configure_pacemaker_remote(self, commit, is_resource_present):
        is_resource_present.return_value = False
        self.assertEqual(
            utils.configure_pacemaker_remote(
                'juju-aa0ba5-zaza-ed2ce6f303f0-10',
                '10.0.0.10'),
            'juju-aa0ba5-zaza-ed2ce6f303f0-10')
        commit.assert_called_once_with(
            'crm configure primitive juju-aa0ba5-zaza-ed2ce6f303f0-10 '
            'ocf:pacemaker:remote params '
            'server=10.0.0.10 '
            'reconnect_interval=60 op monitor interval=30s',
            failure_is_fatal=True)

    @mock.patch('pcmk.is_resource_present')
    @mock.patch('pcmk.commit')
    def test_configure_pacemaker_remote_fqdn(self, commit,
                                             is_resource_present):
        is_resource_present.return_value = False
        self.assertEqual(
            utils.configure_pacemaker_remote(
                'juju-aa0ba5-zaza-ed2ce6f303f0-10.maas',
                '10.0.0.10'),
            'juju-aa0ba5-zaza-ed2ce6f303f0-10.maas')
        commit.assert_called_once_with(
            'crm configure primitive juju-aa0ba5-zaza-ed2ce6f303f0-10.maas '
            'ocf:pacemaker:remote params '
            'server=10.0.0.10 '
            'reconnect_interval=60 op monitor interval=30s',
            failure_is_fatal=True)

    @mock.patch('pcmk.is_resource_present')
    @mock.patch('pcmk.commit')
    def test_configure_pacemaker_remote_duplicate(self, commit,
                                                  is_resource_present):
        is_resource_present.return_value = True
        self.assertEqual(
            utils.configure_pacemaker_remote(
                'juju-aa0ba5-zaza-ed2ce6f303f0-10.maas',
                '10.0.0.10'),
            'juju-aa0ba5-zaza-ed2ce6f303f0-10.maas')
        self.assertFalse(commit.called)

    @mock.patch('pcmk.commit')
    def test_cleanup_remote_nodes(self, commit):
        commit.return_value = 0
        utils.cleanup_remote_nodes(['res-node1', 'res-node2'])
        commit_calls = [
            mock.call(
                'crm resource cleanup res-node1',
                failure_is_fatal=False),
            mock.call(
                'crm resource cleanup res-node2',
                failure_is_fatal=False)]
        commit.assert_has_calls(commit_calls)

    @mock.patch.object(utils, 'relation_get')
    @mock.patch.object(utils, 'related_units')
    @mock.patch.object(utils, 'relation_ids')
    @mock.patch.object(utils, 'add_location_rules_for_local_nodes')
    @mock.patch.object(utils, 'configure_pacemaker_remote')
    @mock.patch.object(utils, 'configure_maas_stonith_resource')
    @mock.patch.object(utils, 'cleanup_remote_nodes')
    def test_configure_pacemaker_remote_resources(
            self,
            cleanup_remote_nodes,
            configure_maas_stonith_resource,
            configure_pacemaker_remote,
            add_location_rules_for_local_nodes,
            relation_ids,
            related_units,
            relation_get):
        rdata = {
            'pacemaker-remote:49': {
                'pacemaker-remote/0': {
                    'remote-hostname': '"node1"',
                    'remote-ip': '"10.0.0.10"',
                    'stonith-hostname': '"st-node1"'},
                'pacemaker-remote/1': {
                    'remote-ip': '"10.0.0.11"',
                    'remote-hostname': '"node2"'},
                'pacemaker-remote/2': {
                    'stonith-hostname': '"st-node3"'}}}
        relation_ids.side_effect = lambda x: rdata.keys()
        related_units.side_effect = lambda x: sorted(rdata[x].keys())
        relation_get.side_effect = lambda x, y, z: rdata[z][y].get(x, None)
        configure_pacemaker_remote.side_effect = \
            lambda x, y: 'res-{}'.format(x)
        utils.configure_pacemaker_remote_resources()
        remote_calls = [
            mock.call('node1', '10.0.0.10'),
            mock.call('node2', '10.0.0.11')]
        configure_pacemaker_remote.assert_has_calls(
            remote_calls,
            any_order=True)
        cleanup_remote_nodes.assert_called_once_with(
            ['res-node1', 'res-node2'])

    @mock.patch.object(utils, 'config')
    @mock.patch.object(utils, 'remove_legacy_maas_stonith_resources')
    @mock.patch('pcmk.commit')
    @mock.patch('pcmk.is_resource_present')
    def test_configure_maas_stonith_resource(self, is_resource_present,
                                             commit, remove_legacy, config):
        cfg = {
            'maas_url': 'http://maas/2.0',
            'maas_credentials': 'apikey'}
        is_resource_present.return_value = False
        config.side_effect = lambda x: cfg.get(x)
        utils.configure_maas_stonith_resource(['node1'])
        cmd = (
            "crm configure primitive st-maas "
            "stonith:external/maas "
            "params url='http://maas/2.0' apikey='apikey' "
            "hostnames='node1' "
            "op monitor interval=25 start-delay=25 "
            "timeout=25")
        commit_calls = [
            mock.call(cmd, failure_is_fatal=True),
        ]
        commit.assert_has_calls(commit_calls)

    @mock.patch.object(utils, 'remove_legacy_maas_stonith_resources')
    @mock.patch('pcmk.commit')
    @mock.patch('pcmk.is_resource_present')
    def test_configure_null_stonith_resource(self, is_resource_present,
                                             commit, remove_legacy):
        is_resource_present.return_value = False
        utils.configure_null_stonith_resource(['node1'])
        cmd = (
            "crm configure primitive st-null "
            "stonith:null "
            "params hostlist='node1' "
            "op monitor interval=25 start-delay=25 "
            "timeout=25")
        commit_calls = [
            mock.call(cmd, failure_is_fatal=True),
        ]
        commit.assert_has_calls(commit_calls)

    @mock.patch.object(utils, 'config')
    @mock.patch.object(utils, 'remove_legacy_maas_stonith_resources')
    @mock.patch('pcmk.commit')
    @mock.patch('pcmk.is_resource_present')
    @mock.patch('pcmk.crm_update_resource')
    def test_configure_maas_stonith_resource_duplicate(self,
                                                       crm_update_resource,
                                                       is_resource_present,
                                                       commit, remove_legacy,
                                                       config):
        cfg = {
            'maas_url': 'http://maas/2.0',
            'maas_credentials': 'apikey'}
        is_resource_present.return_value = True
        config.side_effect = lambda x: cfg.get(x)
        utils.configure_maas_stonith_resource(['node1'])
        crm_update_resource.assert_called_once_with(
            'st-maas',
            'stonith:external/maas',
            ("params url='http://maas/2.0' apikey='apikey' hostnames='node1' "
             "op monitor interval=25 start-delay=25 timeout=25"))

    @mock.patch.object(utils, 'config')
    @mock.patch('pcmk.commit')
    @mock.patch('pcmk.is_resource_present')
    def test_configure_maas_stonith_resource_no_url(self,
                                                    is_resource_present,
                                                    commit, config):
        cfg = {
            'maas_credentials': 'apikey'}
        is_resource_present.return_value = False
        config.side_effect = lambda x: cfg.get(x)
        with self.assertRaises(ValueError):
            utils.configure_maas_stonith_resource('node1')

    @mock.patch.object(utils, 'unit_get')
    @mock.patch.object(utils, 'get_ipv6_addr')
    @mock.patch.object(utils, 'relation_get')
    @mock.patch.object(utils, 'related_units')
    @mock.patch.object(utils, 'relation_ids')
    @mock.patch.object(utils, 'config')
    def test_get_node_flags(self, config, relation_ids, related_units,
                            relation_get, get_ipv6_addr, unit_get):
        cfg = {}
        config.side_effect = lambda x: cfg.get(x)
        unit_get.return_value = '10.0.0.41'
        relation_ids.return_value = ['relid1']
        related_units.return_value = ['unit1', 'unit2', 'unit3']
        rdata = {
            'unit1': {
                'random_flag': True,
                'private-address': '10.0.0.10'},
            'unit2': {
                'random_flag': True,
                'private-address': '10.0.0.34'},
            'unit3': {
                'random_flag': True,
                'private-address': '10.0.0.16'}}
        relation_get.side_effect = lambda v, rid, unit: rdata[unit].get(v)
        rget_calls = [
            mock.call('random_flag', rid='relid1', unit='unit1'),
            mock.call('private-address', rid='relid1', unit='unit1'),
            mock.call('random_flag', rid='relid1', unit='unit2'),
            mock.call('private-address', rid='relid1', unit='unit2'),
            mock.call('random_flag', rid='relid1', unit='unit3'),
            mock.call('private-address', rid='relid1', unit='unit3')]
        self.assertSequenceEqual(
            utils.get_node_flags('random_flag'),
            ['10.0.0.10', '10.0.0.16', '10.0.0.34', '10.0.0.41'])
        relation_get.assert_has_calls(rget_calls)

    @mock.patch.object(utils, 'get_node_flags')
    def test_get_cluster_nodes(self, get_node_flags):
        utils.get_cluster_nodes()
        get_node_flags.assert_called_once_with('ready')

    @mock.patch.object(utils, 'get_node_flags')
    def test_get_member_ready_nodes(self, get_node_flags):
        utils.get_member_ready_nodes()
        get_node_flags.assert_called_once_with('member_ready')

    @mock.patch('pcmk.commit')
    @mock.patch('pcmk.list_nodes')
    @mock.patch.object(utils, 'add_location_rules_for_local_nodes')
    @mock.patch.object(utils, 'need_resources_on_remotes')
    def test_configure_resources_on_remotes(self, need_resources_on_remotes,
                                            add_location_rules_for_local_nodes,
                                            list_nodes, commit):
        list_nodes.return_value = ['node1', 'node2', 'node3']
        need_resources_on_remotes.return_value = False
        clones = {
            'cl_res_masakari_haproxy': u'res_masakari_haproxy'}
        resources = {
            'res_masakari_1e39e82_vip': u'ocf:heartbeat:IPaddr2',
            'res_masakari_flump': u'ocf:heartbeat:IPaddr2',
            'res_masakari_haproxy': u'lsb:haproxy'}
        groups = {
            'grp_masakari_vips': 'res_masakari_1e39e82_vip'}
        utils.configure_resources_on_remotes(
            resources=resources,
            clones=clones,
            groups=groups)
        add_loc_calls = [
            mock.call('cl_res_masakari_haproxy'),
            mock.call('res_masakari_flump'),
            mock.call('grp_masakari_vips')]
        add_location_rules_for_local_nodes.assert_has_calls(
            add_loc_calls,
            any_order=True)
        commit.assert_called_once_with(
            'crm_resource --resource cl_res_masakari_haproxy '
            '--set-parameter clone-max '
            '--meta --parameter-value 3',
            failure_is_fatal=True)

    @mock.patch('pcmk.commit')
    @mock.patch('pcmk.list_nodes')
    @mock.patch.object(utils, 'add_location_rules_for_local_nodes')
    @mock.patch.object(utils, 'need_resources_on_remotes')
    def test_configure_resources_on_remotes_true(
            self,
            need_resources_on_remotes,
            add_location_rules_for_local_nodes,
            list_nodes,
            commit):
        list_nodes.return_value = ['node1', 'node2', 'node3']
        need_resources_on_remotes.return_value = True
        clones = {
            'cl_res_masakari_haproxy': u'res_masakari_haproxy'}
        resources = {
            'res_masakari_1e39e82_vip': u'ocf:heartbeat:IPaddr2',
            'res_masakari_flump': u'ocf:heartbeat:IPaddr2',
            'res_masakari_haproxy': u'lsb:haproxy'}
        groups = {
            'grp_masakari_vips': 'res_masakari_1e39e82_vip'}
        utils.configure_resources_on_remotes(
            resources=resources,
            clones=clones,
            groups=groups)
        self.assertFalse(commit.called)

    @mock.patch('pcmk.commit')
    @mock.patch('pcmk.list_nodes')
    @mock.patch.object(utils, 'add_location_rules_for_local_nodes')
    @mock.patch.object(utils, 'need_resources_on_remotes')
    def test_configure_resources_on_remotes_unknown(
            self,
            need_resources_on_remotes,
            add_location_rules_for_local_nodes,
            list_nodes,
            commit):
        list_nodes.return_value = ['node1', 'node2', 'node3']
        need_resources_on_remotes.side_effect = ValueError
        clones = {
            'cl_res_masakari_haproxy': u'res_masakari_haproxy'}
        resources = {
            'res_masakari_1e39e82_vip': u'ocf:heartbeat:IPaddr2',
            'res_masakari_flump': u'ocf:heartbeat:IPaddr2',
            'res_masakari_haproxy': u'lsb:haproxy'}
        groups = {
            'grp_masakari_vips': 'res_masakari_1e39e82_vip'}
        utils.configure_resources_on_remotes(
            resources=resources,
            clones=clones,
            groups=groups)
        self.assertFalse(commit.called)

    @mock.patch('pcmk.commit')
    def test_configure_global_cluster(self, mock_commit):
        utils.configure_cluster_global(240, 120)
        mock_commit.has_calls([
            mock.call('crm configure property no-quorum-policy=stop'),
            mock.call('crm configure rsc_defaults $id="rsc-options" '
                      'resource-stickiness="100" failure-timeout=240'),
            mock.call('crm configure property cluster-recheck-interval=120')
        ])

    class MockHookData(object):
        class MockDB(object):

            def __init__(self):
                self.kv = {}

            def set(self, key, value):
                self.kv[key] = value

            def get(self, key):
                return self.kv.get(key)

        def __init__(self):
            self.kv = self.MockDB()

        @contextlib.contextmanager
        def __call__(self):
            yield [self.kv]

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_val, exc_tb):
            return

    @mock.patch.object(utils.unitdata, 'HookData')
    def test_set_waiting_unit_series_upgrade(self, HookData):
        hook_data = self.MockHookData()
        HookData.return_value = hook_data
        utils.set_waiting_unit_series_upgrade()
        self.assertTrue(hook_data.kv.get('waiting-unit-series-upgrade'))

    @mock.patch.object(utils.unitdata, 'HookData')
    def test_clear_waiting_unit_series_upgrade(self, HookData):
        hook_data = self.MockHookData()
        HookData.return_value = hook_data
        utils.set_waiting_unit_series_upgrade()
        self.assertTrue(hook_data.kv.get('waiting-unit-series-upgrade'))
        utils.clear_waiting_unit_series_upgrade()
        self.assertFalse(hook_data.kv.get('waiting-unit-series-upgrade'))

    @mock.patch.object(utils.unitdata, 'HookData')
    def test_is_waiting_unit_series_upgrade_set(self, hookdata):
        hook_data = self.MockHookData()
        hookdata.return_value = hook_data
        # false if key is absent
        self.assertFalse(utils.is_waiting_unit_series_upgrade_set())

        # True if waiting-unit-upgrade het been set
        utils.set_waiting_unit_series_upgrade()
        self.assertTrue(utils.is_waiting_unit_series_upgrade_set())

        # False if waiting-unit-upgrade has been cleared
        utils.clear_waiting_unit_series_upgrade()
        self.assertFalse(utils.is_waiting_unit_series_upgrade_set())

    @mock.patch.object(utils, 'relation_get')
    @mock.patch.object(utils, 'related_units')
    def test_get_series_upgrade_notifications(self, related_units,
                                              relation_get):
        related_units.return_value = ['unit1', 'unit2']
        rdata = {
            'unit1': {
                'series_upgrade_of_unit1': 'trusty'},
            'unit2': {}}
        relation_get.side_effect = lambda rid, unit: rdata[unit]
        self.assertEqual(
            utils.get_series_upgrade_notifications('rid1'),
            {'unit1': 'trusty'})

    @mock.patch.object(utils, 'service_stop')
    @mock.patch.object(utils, 'service_running')
    @mock.patch.object(utils, 'disable_lsb_services')
    def test_disable_ha_services(self, disable_lsb_services, service_running,
                                 service_stop):
        disable_calls = [
            mock.call('corosync'),
            mock.call('pacemaker')
        ]
        stop_calls = [
            mock.call('corosync'),
            mock.call('pacemaker')
        ]
        service_running.return_value = True
        utils.disable_ha_services()
        disable_lsb_services.assert_has_calls(disable_calls)
        service_stop.assert_has_calls(stop_calls)

    @mock.patch.object(utils, 'service_start')
    @mock.patch.object(utils, 'service_running')
    @mock.patch.object(utils, 'enable_lsb_services')
    def test_enable_ha_services(self, enable_lsb_services, service_running,
                                service_start):
        enable_calls = [
            mock.call('pacemaker'),
            mock.call('corosync')
        ]
        start_calls = [
            mock.call('pacemaker'),
            mock.call('corosync')
        ]
        service_running.return_value = False
        utils.enable_ha_services()
        enable_lsb_services.assert_has_calls(enable_calls)
        service_start.assert_has_calls(start_calls)

    @mock.patch.object(utils, 'local_unit')
    def test_get_series_upgrade_key(self, local_unit):
        local_unit.return_value = 'nova-cloud-controller/2'
        self.assertEqual(
            utils.get_series_upgrade_key(),
            'series_upgrade_of_nova_cloud_controller_2'
        )

    @mock.patch.object(utils, 'relation_set')
    @mock.patch.object(utils, 'relation_ids')
    @mock.patch.object(utils, 'local_unit')
    @mock.patch.object(utils, 'lsb_release')
    def test_notify_peers_of_series_upgrade(self, lsb_release, local_unit,
                                            relation_ids, relation_set):
        lsb_release.return_value = {
            'DISTRIB_CODENAME': 'trusty'}
        local_unit.return_value = 'nova-compute/2'
        relation_ids.return_value = ['rid1']
        utils.notify_peers_of_series_upgrade()
        relation_set.assert_called_once_with(
            relation_id='rid1',
            relation_settings={'series_upgrade_of_nova_compute_2': 'trusty'})

    @mock.patch.object(utils, 'relation_set')
    @mock.patch.object(utils, 'relation_ids')
    @mock.patch.object(utils, 'local_unit')
    def test_clear_series_upgrade_notification(self, local_unit, relation_ids,
                                               relation_set):
        local_unit.return_value = 'nova-compute/2'
        relation_ids.return_value = ['rid1']
        utils.clear_series_upgrade_notification()
        relation_set.assert_called_once_with(
            relation_id='rid1',
            relation_settings={'series_upgrade_of_nova_compute_2': None})

    @mock.patch('pcmk.crm_maas_stonith_resource_list')
    @mock.patch('pcmk.commit')
    def test_remove_legacy_maas_stonith_resources(self, mock_commit,
                                                  mock_resource_list):
        mock_resource_list.return_value = ['st-maas-abcd', 'st-maas-1234']
        utils.remove_legacy_maas_stonith_resources()
        commit_calls = [
            mock.call('crm -w -F resource stop st-maas-abcd'),
            mock.call('crm -w -F configure delete st-maas-abcd'),
            mock.call('crm -w -F resource stop st-maas-1234'),
            mock.call('crm -w -F configure delete st-maas-1234')]
        mock_commit.assert_has_calls(commit_calls)

    @mock.patch.object(utils, 'leader_set')
    def test_set_stonith_configured(self, leader_set):
        utils.set_stonith_configured(True)
        leader_set.assert_called_once_with(
            {'stonith-configured': True})

    @mock.patch.object(utils, 'leader_get')
    def test_is_stonith_configured(self, leader_get):
        leader_get.return_value = 'True'
        self.assertTrue(
            utils.is_stonith_configured())
        leader_get.return_value = 'False'
        self.assertFalse(
            utils.is_stonith_configured())
        leader_get.return_value = ''
        self.assertFalse(
            utils.is_stonith_configured())

    @mock.patch('pcmk.commit')
    def test_enable_stonith(self, commit):
        utils.enable_stonith()
        commit.assert_called_once_with(
            'crm configure property stonith-enabled=true',
            failure_is_fatal=True)

    @mock.patch('pcmk.commit')
    def test_disable_stonith(self, commit):
        utils.disable_stonith()
        commit.assert_called_once_with(
            'crm configure property stonith-enabled=false',
            failure_is_fatal=True)

    @mock.patch('subprocess.check_output')
    def test_node_is_dc(self, mock_subprocess):
        with open(self._testdata('test_crm_mon.xml'), 'r') as fd:
            mock_subprocess.return_value = "".join(
                fd.readlines()).encode("utf-8")

        self.assertTrue(utils.node_is_dc('juju-2eebcf-0'))

    @mock.patch.object(utils.unitdata, 'HookData')
    def test_is_update_ring_requested(self, HookData):
        hook_data = self.MockHookData()
        HookData.return_value = hook_data
        self.assertTrue(
            utils.is_update_ring_requested('random-uuid-generated')
        )
        self.assertEquals(
            hook_data.kv.get('corosync-update-uuid'),
            'random-uuid-generated',
        )
        # No change in uuid means no new request has been issued
        self.assertFalse(
            utils.is_update_ring_requested('random-uuid-generated')
        )

    @mock.patch('pcmk.commit')
    @mock.patch.object(utils, 'emit_corosync_conf')
    @mock.patch.object(utils, 'is_update_ring_requested')
    @mock.patch.object(utils, 'relation_get')
    def test_trigger_corosync_update_from_leader(self, mock_relation_get,
                                                 mock_is_update_ring_req,
                                                 mock_emit_corosync_conf,
                                                 mock_commit):
        # corosync-update-uuid is set and has changed:
        mock_relation_get.return_value = 'random-uuid-generated'
        mock_is_update_ring_req.return_value = True

        mock_emit_corosync_conf.return_value = True
        self.assertTrue(
            utils.trigger_corosync_update_from_leader(
                'hacluster/0',
                'hanode:0',
            ),
        )
        mock_commit.assert_has_calls([mock.call('corosync-cfgtool -R')])

        # corosync-update-uuid isn't set:
        mock_relation_get.return_value = None
        self.assertFalse(
            utils.trigger_corosync_update_from_leader(
                'hacluster/0',
                'hanode:0',
            ),
        )

    @mock.patch.object(utils, 'get_hostname')
    @mock.patch.object(utils, 'relation_get')
    @mock.patch.object(utils, 'related_units')
    @mock.patch.object(utils, 'relation_ids')
    def test_get_hanode_hostnames(
            self, _relation_ids, _related_units, _relation_get, _get_hostname):
        _data = {
            "node/1": {"hostname": "beta"},
            "node/3": {"hostname": "alpha"},
        }

        def _rel_data(_param, unit, rid):
            return _data[unit][_param]

        _relation_ids.return_value = ["hanode:1"]
        _related_units.return_value = ["node/1", "node/3"]
        _relation_get.side_effect = _rel_data
        _get_hostname.return_value = "gamma"
        _expected = ["alpha", "beta", "gamma"]

        self.assertEqual(
            utils.get_hanode_hostnames(),
            _expected)

    @mock.patch.object(utils, 'get_hanode_hostnames')
    @mock.patch.object(utils, 'pcmk')
    def test_update_node_list(self, _pcmk, _get_hanode_hostnames):
        _pcmk.list_nodes.return_value = ["zeta", "beta", "psi"]
        _get_hanode_hostnames.return_value = ["alpha", "beta", "gamma"]
        _expected = set(["zeta", "psi"])

        self.assertEqual(
            utils.update_node_list(),
            _expected)

        _pcmk.set_node_status_to_maintenance.assert_has_calls(
            [mock.call('zeta'),
             mock.call('psi')],
            any_order=True)
        _pcmk.delete_node.assert_has_calls(
            [mock.call('zeta'),
             mock.call('psi')],
            any_order=True)

        # Raise RemoveCorosyncNodeFailed
        _pcmk.delete_node.side_effect = subprocess.CalledProcessError(
            127, "fake crm command")
        with self.assertRaises(utils.RemoveCorosyncNodeFailed):
            utils.update_node_list()
