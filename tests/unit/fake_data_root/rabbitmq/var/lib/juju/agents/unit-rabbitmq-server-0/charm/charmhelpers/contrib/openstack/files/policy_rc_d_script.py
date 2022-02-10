#!/usr/bin/env python3

"""This script is an implementation of policy-rc.d

For further information on policy-rc.d see *1

*1 https://people.debian.org/~hmh/invokerc.d-policyrc.d-specification.txt
"""
import collections
import glob
import os
import logging
import sys
import time
import uuid
import yaml


SystemPolicy = collections.namedtuple(
    'SystemPolicy',
    [
        'policy_requestor_name',
        'policy_requestor_type',
        'service',
        'blocked_actions'])

DEFAULT_POLICY_CONFIG_DIR = '/etc/policy-rc.d'
DEFAULT_POLICY_LOG_DIR = '/var/lib/policy-rc.d'


def read_policy_file(policy_file):
    """Return system policies from given file.

    :param file_name: Name of file to read.
    :type file_name: str
    :returns: Policy
    :rtype: List[SystemPolicy]
    """
    policies = []
    if os.path.exists(policy_file):
        with open(policy_file, 'r') as f:
            policy = yaml.safe_load(f)
        for service, actions in policy['blocked_actions'].items():
            service = service.replace('.service', '')
            policies.append(SystemPolicy(
                policy_requestor_name=policy['policy_requestor_name'],
                policy_requestor_type=policy['policy_requestor_type'],
                service=service,
                blocked_actions=actions))
    return policies


def get_policies(policy_config_dir):
    """Return all system policies in policy_config_dir.

    :param policy_config_dir: Name of file to read.
    :type policy_config_dir: str
    :returns: Policy
    :rtype: List[SystemPolicy]
    """
    _policy = []
    for f in glob.glob('{}/*.policy'.format(policy_config_dir)):
        _policy.extend(read_policy_file(f))
    return _policy


def record_blocked_action(service, action, blocking_policies, policy_log_dir):
    """Record that an action was requested but deniedl

    :param service: Service that was blocked
    :type service: str
    :param action: Action that was blocked.
    :type action: str
    :param blocking_policies: Policies that blocked the action on the service.
    :type blocking_policies: List[SystemPolicy]
    :param policy_log_dir: Directory to place the blocking action record.
    :type policy_log_dir: str
    """
    if not os.path.exists(policy_log_dir):
        os.mkdir(policy_log_dir)
    seconds = round(time.time())
    for policy in blocking_policies:
        if not os.path.exists(policy_log_dir):
            os.mkdir(policy_log_dir)
        file_name = '{}/{}-{}-{}.deferred'.format(
            policy_log_dir,
            policy.policy_requestor_type,
            policy.policy_requestor_name,
            uuid.uuid1())
        with open(file_name, 'w') as f:
            data = {
                'timestamp': seconds,
                'service': service,
                'action': action,
                'reason': 'Package update',
                'policy_requestor_type': policy.policy_requestor_type,
                'policy_requestor_name': policy.policy_requestor_name}
            yaml.dump(data, f)


def get_blocking_policies(service, action, policy_config_dir):
    """Record that an action was requested but deniedl

    :param service: Service that action is requested against.
    :type service: str
    :param action: Action that is requested.
    :type action: str
    :param policy_config_dir: Directory that stores policy files.
    :type policy_config_dir: str
    :returns: Policies
    :rtype: List[SystemPolicy]
    """
    service = service.replace('.service', '')
    blocking_policies = [
        policy
        for policy in get_policies(policy_config_dir)
        if policy.service == service and action in policy.blocked_actions]
    return blocking_policies


def process_action_request(service, action, policy_config_dir, policy_log_dir):
    """Take the requested action against service and check if it is permitted.

    :param service: Service that action is requested against.
    :type service: str
    :param action: Action that is requested.
    :type action: str
    :param policy_config_dir: Directory that stores policy files.
    :type policy_config_dir: str
    :param policy_log_dir: Directory that stores policy files.
    :type policy_log_dir: str
    :returns: Tuple of whether the action is permitted and explanation.
    :rtype: (boolean, str)
    """
    blocking_policies = get_blocking_policies(
        service,
        action,
        policy_config_dir)
    if blocking_policies:
        policy_msg = [
            '{} {}'.format(p.policy_requestor_type, p.policy_requestor_name)
            for p in sorted(blocking_policies)]
        message = '{} of {} blocked by {}'.format(
            action,
            service,
            ', '.join(policy_msg))
        record_blocked_action(
            service,
            action,
            blocking_policies,
            policy_log_dir)
        action_permitted = False
    else:
        message = "Permitting {} {}".format(service, action)
        action_permitted = True
    return action_permitted, message


def main():
    logging.basicConfig(
        filename='/var/log/policy-rc.d.log',
        level=logging.DEBUG,
        format='%(asctime)s %(message)s')

    service = sys.argv[1]
    action = sys.argv[2]

    permitted, message = process_action_request(
        service,
        action,
        DEFAULT_POLICY_CONFIG_DIR,
        DEFAULT_POLICY_LOG_DIR)
    logging.info(message)

    # https://people.debian.org/~hmh/invokerc.d-policyrc.d-specification.txt
    # Exit status codes:
    #  0 - action allowed
    #  1 - unknown action (therefore, undefined policy)
    # 100 - unknown initscript id
    # 101 - action forbidden by policy
    # 102 - subsystem error
    # 103 - syntax error
    # 104 - [reserved]
    # 105 - behaviour uncertain, policy undefined.
    # 106 - action not allowed. Use the returned fallback actions
    #       (which are implied to be "allowed") instead.

    if permitted:
        return 0
    else:
        return 101


if __name__ == "__main__":
    rc = main()
    sys.exit(rc)
