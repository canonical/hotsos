#!/usr/bin/env python3
#
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

import os
import subprocess
import sys
import traceback

sys.path.append('hooks/')

import charmhelpers.core as ch_core
import charmhelpers.contrib.openstack.utils as ch_openstack_utils
import charmhelpers.contrib.network.ovs as ch_ovs
import charmhelpers.contrib.network.ovs.ovsdb as ch_ovsdb


class BaseDocException(Exception):
    """Use docstring as default message for exception."""

    def __init__(self, message=None):
        self.message = message or self.__doc__

    def __repr__(self):
        return self.message

    def __str__(self):
        return self.message


class UnitNotPaused(BaseDocException):
    """Action requires unit to be paused but it was not paused."""
    pass


class MandatoryConfigurationNotSet(BaseDocException):
    """Action requires certain configuration to be set to operate correctly."""
    pass


def remove_patch_ports(bridge):
    """Remove patch ports from both ends starting with named bridge.

    :param bridge: Name of bridge to look for patch ports to remove.
    :type bridge: str
    """
    # NOTE: We need to consume all output from the `patch_ports_on_bridge`
    # generator prior to removing anything otherwise it will raise an error.
    for patch in list(ch_ovs.patch_ports_on_bridge(bridge)):
        ch_ovs.del_bridge_port(
            patch.this_end.bridge,
            patch.this_end.port,
            linkdown=False)
        ch_ovs.del_bridge_port(
            patch.other_end.bridge,
            patch.other_end.port,
            linkdown=False)


def remove_per_bridge_controllers():
    """Remove per bridge controllers."""
    bridges = ch_ovsdb.SimpleOVSDB('ovs-vsctl').bridge
    for bridge in bridges:
        if bridge['controller']:
            bridges.clear(str(bridge['_uuid']), 'controller')


def neutron_ipset_cleanup():
    """Perform Neutron ipset cleanup."""
    subprocess.check_call(
        (
            'neutron-ipset-cleanup',
            '--config-file=/etc/neutron/neutron.conf',
            '--config-file=/etc/neutron/plugins/ml2/openvswitch_agent.ini',
        ))


def neutron_netns_cleanup():
    """Perform Neutron netns cleanup."""
    # FIXME: remove once package dependencies have been backported LP: #1881852
    subprocess.check_call(('apt', '-y', 'install', 'net-tools'))
    _tmp_filters = '/etc/neutron/rootwrap.d/charm-n-ovs.filters'
    with open(_tmp_filters, 'w') as fp:
        fp.write(
            '[Filters]\nneutron.cmd.netns_cleanup: CommandFilter, ip, root\n')
    subprocess.check_call(
        (
            'neutron-netns-cleanup',
            '--force',
            *[
                # Existence of these files depend on our configuration.
                '--config-file={}'.format(cfg) for cfg in (
                    '/etc/neutron/neutron.conf',
                    '/etc/neutron/l3_agent.ini',
                    '/etc/neutron/fwaas_driver.ini',
                    '/etc/neutron/dhcp_agent.ini',
                ) if os.path.exists(cfg)]
        ))
    os.unlink(_tmp_filters)


def cleanup(args):
    """Clean up after Neutron agents."""
    # Check that prerequisites for operation are met
    if not ch_openstack_utils.is_unit_paused_set():
        raise UnitNotPaused()
    if ch_core.hookenv.config('firewall-driver') != 'openvswitch':
        raise MandatoryConfigurationNotSet(
            'Action requires configuration option `firewall-driver` to be set '
            'to "openvswitch" for succesfull operation.')
    if not ch_core.hookenv.action_get('i-really-mean-it'):
        raise MandatoryConfigurationNotSet(
            'Action requires the `i-really-mean-it` parameter to be set to '
            '"true".')

    # The names used for the integration- and tunnel-bridge are
    # configurable, but this configuration is not exposed in the charm.
    #
    # Assume default names are used.
    remove_patch_ports('br-int')
    ch_ovs.del_bridge('br-tun')

    # The Neutron Open vSwitch agent configures each Open vSwitch bridge to
    # establish an active OVSDB connection back to the Neutron Agent.
    #
    # Remove these
    remove_per_bridge_controllers()

    # Remove namespaces set up by Neutron
    neutron_netns_cleanup()

    # Remove ipsets set up by Neutron
    neutron_ipset_cleanup()


# A dictionary of all the defined actions to callables (which take
# parsed arguments).
ACTIONS = {'cleanup': cleanup}


def main(args):
    action_name = os.path.basename(args[0])
    try:
        action = ACTIONS[action_name]
    except KeyError:
        msg = 'Action "{}" undefined'.format(action_name)
        ch_core.hookenv.action_fail(msg)
        return msg
    else:
        try:
            action(args)
        except Exception as e:
            msg = 'Action "{}" failed: "{}"'.format(action_name, str(e))
            ch_core.hookenv.log(
                '{} "{}"'.format(msg, traceback.format_exc()),
                level=ch_core.hookenv.ERROR)
            ch_core.hookenv.action_fail(msg)


if __name__ == "__main__":
    sys.exit(main(sys.argv))
