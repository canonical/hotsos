#!/usr/bin/env python3
#
# Copyright 2020-2021 Canonical Ltd
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

import json
import os
import sys
from enum import Enum

sys.path.append('lib')
sys.path.append('hooks')

import nova_compute_hooks
from nova_compute import cloud_utils
from charmhelpers.core.host import (
    service_pause,
    service_resume,
)
from charmhelpers.core.hookenv import (
    DEBUG,
    function_set,
    function_fail,
    INFO,
    log,
    status_get,
    status_set,
    WORKLOAD_STATES,
)


UNIT_REMOVED_MSG = 'Unit was removed from the cloud'


class ServiceState(Enum):
    """State of the nova-compute service in the cloud controller"""
    enabled = 0
    disabled = 1


def _set_service(state):
    """
    Set state of the nova-compute service in the nova-cloud-controller.

    Available states:
      - ServiceState.enabled: nova-scheduler can use this unit to run new VMs
      - ServiceState.disabled : nova-scheduler won't schedule new VMs on this
                                unit
    :type state: ServiceState
    """
    nova = cloud_utils.nova_client()
    hostname = cloud_utils.service_hostname()

    if state == ServiceState.disabled:
        log('Disabling nova-compute service on host {}'.format(hostname))
        nova.services.disable(hostname, 'nova-compute')
    elif state == ServiceState.enabled:
        log('Enabling nova-compute service on host {}'.format(hostname))
        nova.services.enable(hostname, 'nova-compute')
    else:
        raise RuntimeError('Unknown service state')


def disable():
    """Disable nova-scheduler from starting new VMs on this unit"""
    _set_service(ServiceState.disabled)


def enable():
    """Enable nova-scheduler to start new VMs on this unit"""
    _set_service(ServiceState.enabled)


def remove_from_cloud():
    """
    Implementation of 'remove-from-cloud' action.

    This action is preparation for clean removal of nova-compute unit from
    juju model. If this action succeeds , user can run `juju remove-unit`
    command.

    Steps performed by this action:
      - Checks that this nova-compute unit can be removed from the cloud
        - If not, action fails
      - Stops nova-compute system service
      - Unregisters nova-compute service from the nova cloud controller
    """
    nova = cloud_utils.nova_client()

    if cloud_utils.running_vms(nova) > 0:
        raise RuntimeError("This unit can not be removed from the "
                           "cloud because it's still running VMs. Please "
                           "remove these VMs or migrate them to another "
                           "nova-compute unit")
    nova_service_id = cloud_utils.nova_service_id(nova)

    log("Stopping nova-compute service", DEBUG)
    service_pause('nova-compute')
    log("Deleting nova service '{}'".format(nova_service_id), DEBUG)
    nova.services.delete(nova_service_id)

    status_set(WORKLOAD_STATES.BLOCKED, UNIT_REMOVED_MSG)
    function_set({'message': UNIT_REMOVED_MSG})


def register_to_cloud():
    """
    Implementation of `register-to-cloud` action.

    This action reverts `remove-from-cloud` action. It starts nova-comptue
    system service which will trigger its re-registration in the cloud.
    """
    log("Starting nova-compute service", DEBUG)
    service_resume('nova-compute')
    current_status = status_get()
    if current_status[0] == WORKLOAD_STATES.BLOCKED.value and \
            current_status[1] == UNIT_REMOVED_MSG:
        status_set(WORKLOAD_STATES.ACTIVE, 'Unit is ready')

    nova_compute_hooks.update_status()
    function_set({
        'command': 'openstack compute service list',
        'message': "Nova compute service started. It should get registered "
                   "with the cloud controller in a short time. Use the "
                   "'openstack' command to verify that it's registered."
    })


def instance_count():
    """Implementation of `instance-count` action."""
    nova = cloud_utils.nova_client()
    vm_count = cloud_utils.running_vms(nova)

    function_set({'instance-count': vm_count})


def list_computes():
    """Implementation of `list-compute-nodes` action."""
    nova = cloud_utils.nova_client()
    function_set({'node-name': cloud_utils.service_hostname()})
    computes = [service.to_dict()
                for service in nova.services.list(binary='nova-compute')]
    function_set({'compute-nodes': json.dumps(computes)})


def node_name():
    """Implementation of 'node-name' action."""
    function_set({'node-name': cloud_utils.service_hostname()})


ACTIONS = {
    'disable': disable,
    'enable': enable,
    'remove-from-cloud': remove_from_cloud,
    'register-to-cloud': register_to_cloud,
    'instance-count': instance_count,
    'list-compute-nodes': list_computes,
    'node-name': node_name,
}


def main(args):
    action_name = os.path.basename(args.pop(0))
    try:
        action = ACTIONS[action_name]
    except KeyError:
        s = "Action {} undefined".format(action_name)
        function_fail(s)
        return
    else:
        try:
            log("Running action '{}'.".format(action_name), INFO)
            action()
        except Exception as exc:
            function_fail("Action {} failed: {}".format(action_name, str(exc)))


if __name__ == '__main__':
    main(sys.argv)
