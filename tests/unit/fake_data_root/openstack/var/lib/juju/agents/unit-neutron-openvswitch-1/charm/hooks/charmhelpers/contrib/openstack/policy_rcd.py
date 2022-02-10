# Copyright 2021 Canonical Limited.
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

"""Module for managing policy-rc.d script and associated files.

This module manages the installation of /usr/sbin/policy-rc.d, the
policy files and the event files. When a package update occurs the
packaging system calls:

policy-rc.d [options] <initscript ID> <actions>

The return code of the script determines if the packaging system
will perform that action on the given service. The policy-rc.d
implementation installed by this module checks if an action is
permitted by checking policy files placed in /etc/policy-rc.d.
If a policy file exists which denies the requested action then
this is recorded in an event file which is placed in
/var/lib/policy-rc.d.
"""

import os
import shutil
import tempfile
import yaml

import charmhelpers.contrib.openstack.files as os_files
import charmhelpers.contrib.openstack.alternatives as alternatives
import charmhelpers.core.hookenv as hookenv
import charmhelpers.core.host as host

POLICY_HEADER = """# Managed by juju\n"""
POLICY_DEFERRED_EVENTS_DIR = '/var/lib/policy-rc.d'
POLICY_CONFIG_DIR = '/etc/policy-rc.d'


def get_policy_file_name():
    """Get the name of the policy file for this application.

    :returns: Policy file name
    :rtype: str
    """
    application_name = hookenv.service_name()
    return '{}/charm-{}.policy'.format(POLICY_CONFIG_DIR, application_name)


def read_default_policy_file():
    """Return the policy file.

    A policy is in the form:
        blocked_actions:
            neutron-dhcp-agent: [restart, stop, try-restart]
            neutron-l3-agent: [restart, stop, try-restart]
            neutron-metadata-agent: [restart, stop, try-restart]
            neutron-openvswitch-agent: [restart, stop, try-restart]
            openvswitch-switch: [restart, stop, try-restart]
            ovs-vswitchd: [restart, stop, try-restart]
            ovs-vswitchd-dpdk: [restart, stop, try-restart]
            ovsdb-server: [restart, stop, try-restart]
        policy_requestor_name: neutron-openvswitch
        policy_requestor_type: charm

    :returns: Policy
    :rtype: Dict[str, Union[str, Dict[str, List[str]]]
    """
    policy = {}
    policy_file = get_policy_file_name()
    if os.path.exists(policy_file):
        with open(policy_file, 'r') as f:
            policy = yaml.safe_load(f)
    return policy


def write_policy_file(policy_file, policy):
    """Write policy to disk.

    :param policy_file: Name of policy file
    :type policy_file: str
    :param policy: Policy
    :type policy: Dict[str, Union[str, Dict[str, List[str]]]]
    """
    with tempfile.NamedTemporaryFile('w', delete=False) as f:
        f.write(POLICY_HEADER)
        yaml.dump(policy, f)
        tmp_file_name = f.name
    shutil.move(tmp_file_name, policy_file)


def remove_policy_file():
    """Remove policy file."""
    try:
        os.remove(get_policy_file_name())
    except FileNotFoundError:
        pass


def install_policy_rcd():
    """Install policy-rc.d components."""
    source_file_dir = os.path.dirname(os.path.abspath(os_files.__file__))
    policy_rcd_exec = "/var/lib/charm/{}/policy-rc.d".format(
        hookenv.service_name())
    host.mkdir(os.path.dirname(policy_rcd_exec))
    shutil.copy2(
        '{}/policy_rc_d_script.py'.format(source_file_dir),
        policy_rcd_exec)
    # policy-rc.d must be installed via the alternatives system:
    # https://people.debian.org/~hmh/invokerc.d-policyrc.d-specification.txt
    if not os.path.exists('/usr/sbin/policy-rc.d'):
        alternatives.install_alternative(
            'policy-rc.d',
            '/usr/sbin/policy-rc.d',
            policy_rcd_exec)
    host.mkdir(POLICY_CONFIG_DIR)


def get_default_policy():
    """Return the default policy structure.

    :returns: Policy
    :rtype: Dict[str, Union[str, Dict[str, List[str]]]
    """
    policy = {
        'policy_requestor_name': hookenv.service_name(),
        'policy_requestor_type': 'charm',
        'blocked_actions': {}}
    return policy


def add_policy_block(service, blocked_actions):
    """Update a policy file with new list of actions.

    :param service: Service name
    :type service: str
    :param blocked_actions: Action to block
    :type blocked_actions: List[str]
    """
    policy = read_default_policy_file() or get_default_policy()
    policy_file = get_policy_file_name()
    if policy['blocked_actions'].get(service):
        policy['blocked_actions'][service].extend(blocked_actions)
    else:
        policy['blocked_actions'][service] = blocked_actions
    policy['blocked_actions'][service] = sorted(
        list(set(policy['blocked_actions'][service])))
    write_policy_file(policy_file, policy)


def remove_policy_block(service, unblocked_actions):
    """Remove list of actions from policy file.

    :param service: Service name
    :type service: str
    :param unblocked_actions: Action to unblock
    :type unblocked_actions: List[str]
    """
    policy_file = get_policy_file_name()
    policy = read_default_policy_file()
    for action in unblocked_actions:
        try:
            policy['blocked_actions'][service].remove(action)
        except (KeyError, ValueError):
            continue
    write_policy_file(policy_file, policy)
