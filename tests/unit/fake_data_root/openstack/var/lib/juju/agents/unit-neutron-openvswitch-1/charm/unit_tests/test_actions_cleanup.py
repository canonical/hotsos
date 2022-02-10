# Copyright 2020 Canonical Ltd
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

import test_utils

with mock.patch('neutron_ovs_utils.register_configs') as configs:
    configs.return_value = 'test-config'
    import cleanup as actions


class CleanupTestCase(test_utils.CharmTestCase):

    def setUp(self):
        super(CleanupTestCase, self).setUp(
            actions, [
                'ch_core',
                'ch_openstack_utils',
                'ch_ovs',
                'neutron_ipset_cleanup',
                'neutron_netns_cleanup',
                'remove_patch_ports',
                'remove_per_bridge_controllers',
                'subprocess',
            ])

    def test_cleanup(self):
        self.ch_openstack_utils.is_unit_paused_set.return_value = False
        with self.assertRaises(actions.UnitNotPaused):
            actions.cleanup([])
        self.ch_openstack_utils.is_unit_paused_set.return_value = True
        with self.assertRaises(actions.MandatoryConfigurationNotSet):
            actions.cleanup([])
        self.ch_core.hookenv.config.return_value = 'openvswitch'
        self.ch_core.hookenv.action_get.return_value = False
        with self.assertRaises(actions.MandatoryConfigurationNotSet):
            actions.cleanup([])
        self.ch_core.hookenv.action_get.return_value = True
        actions.cleanup([])
        self.remove_patch_ports.assert_called_once_with('br-int')
        self.ch_ovs.del_bridge.assert_called_once_with('br-tun')
        self.remove_per_bridge_controllers.assert_called_once_with()
        self.neutron_netns_cleanup.assert_called_once_with()
        self.neutron_ipset_cleanup.assert_called_once_with()


class HelperTestCase(test_utils.CharmTestCase):

    def setUp(self):
        super(HelperTestCase, self).setUp(
            actions, [
                'ch_ovsdb',
            ])

    @mock.patch.object(actions.ch_ovs, 'del_bridge_port')
    @mock.patch.object(actions.ch_ovs, 'patch_ports_on_bridge')
    def test_remove_patch_ports(
            self, _patch_ports_on_bridge, _del_bridge_port):
        _patch_ports_on_bridge.return_value = [actions.ch_ovs.Patch(
            this_end=actions.ch_ovs.PatchPort(
                bridge='this-end-bridge',
                port='this-end-port'),
            other_end=actions.ch_ovs.PatchPort(
                bridge='other-end-bridge',
                port='other-end-port')),
        ]
        actions.remove_patch_ports('fake-bridge')
        _patch_ports_on_bridge.assert_called_once_with(
            'fake-bridge')
        _del_bridge_port.assert_has_calls([
            mock.call('this-end-bridge', 'this-end-port', linkdown=False),
            mock.call('other-end-bridge', 'other-end-port', linkdown=False),
        ])

    def test_remove_per_bridge_controllers(self):
        bridge = mock.MagicMock()
        bridge.__getitem__.return_value = 'fake-uuid'
        ovsdb = mock.MagicMock()
        ovsdb.bridge.__iter__.return_value = [bridge]
        self.ch_ovsdb.SimpleOVSDB.return_value = ovsdb
        actions.remove_per_bridge_controllers()
        ovsdb.bridge.clear.assert_called_once_with('fake-uuid', 'controller')

    @mock.patch.object(actions.subprocess, 'check_call')
    def test_neutron_ipset_cleanup(self, _check_call):
        actions.neutron_ipset_cleanup()
        _check_call.assert_called_once_with(
            (
                'neutron-ipset-cleanup',
                '--config-file=/etc/neutron/neutron.conf',
                '--config-file=/etc/neutron/plugins/ml2/openvswitch_agent.ini',
            ))

    @mock.patch.object(actions.os.path, 'exists')
    @mock.patch.object(actions.os, 'unlink')
    @mock.patch.object(actions.subprocess, 'check_call')
    def test_neutron_netns_cleanup(self, _check_call, _unlink, _exists):
        _exists.return_value = True
        with test_utils.patch_open() as (_open, _file):
            actions.neutron_netns_cleanup()
            _open.assert_called_once_with(
                '/etc/neutron/rootwrap.d/charm-n-ovs.filters', 'w')
            _file.write.assert_called_once_with(
                '[Filters]\n'
                'neutron.cmd.netns_cleanup: CommandFilter, ip, root\n')
            _check_call.assert_has_calls([
                # FIXME: remove once package deps have been backported
                mock.call(('apt', '-y', 'install', 'net-tools')),
                mock.call(
                    (
                        'neutron-netns-cleanup',
                        '--force',
                        '--config-file=/etc/neutron/neutron.conf',
                        '--config-file=/etc/neutron/l3_agent.ini',
                        '--config-file=/etc/neutron/fwaas_driver.ini',
                        '--config-file=/etc/neutron/dhcp_agent.ini',
                    )),
            ])
            _unlink.assert_called_once_with(
                '/etc/neutron/rootwrap.d/charm-n-ovs.filters')
            # Confirm behaviour when a config does not exist
            _exists.reset_mock()
            _exists.side_effect = [True, True, True, False]
            _check_call.reset_mock()
            actions.neutron_netns_cleanup()
            _check_call.assert_has_calls([
                # FIXME: remove once package deps have been backported
                mock.call(('apt', '-y', 'install', 'net-tools')),
                mock.call(
                    (
                        'neutron-netns-cleanup',
                        '--force',
                        '--config-file=/etc/neutron/neutron.conf',
                        '--config-file=/etc/neutron/l3_agent.ini',
                        '--config-file=/etc/neutron/fwaas_driver.ini',
                    )),
            ])


class MainTestCase(test_utils.CharmTestCase):

    def setUp(self):
        super(MainTestCase, self).setUp(actions, [
            'ch_core'
        ])

    def test_invokes_action(self):
        dummy_calls = []

        def dummy_action(args):
            dummy_calls.append(True)

        with mock.patch.dict(actions.ACTIONS, {'foo': dummy_action}):
            actions.main(['foo'])
        self.assertEqual(dummy_calls, [True])

    def test_unknown_action(self):
        """Unknown actions aren't a traceback."""
        exit_string = actions.main(['foo'])
        self.assertEqual('Action "foo" undefined', exit_string)

    def test_failing_action(self):
        """Actions which traceback trigger action_fail() calls."""
        dummy_calls = []

        self.ch_core.hookenv.action_fail.side_effect = dummy_calls.append

        def dummy_action(args):
            raise ValueError('uh oh')

        with mock.patch.dict(actions.ACTIONS, {'foo': dummy_action}):
            actions.main(['foo'])
        self.assertEqual(dummy_calls, ['Action "foo" failed: "uh oh"'])
