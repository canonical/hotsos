#!/usr/bin/env python3
#
# Copyright 2021 Canonical Ltd
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
import sys

sys.path.append('hooks/')

import charmhelpers.contrib.openstack.deferred_events as deferred_events
import charmhelpers.contrib.openstack.utils as os_utils
from charmhelpers.core.hookenv import (
    action_get,
    action_fail,
)
import neutron_ovs_hooks
from neutron_ovs_utils import (
    assess_status,
    pause_unit_helper,
    resume_unit_helper,
    register_configs,
)


def pause(args):
    """Pause the neutron-openvswitch services.
    @raises Exception should the service fail to stop.
    """
    pause_unit_helper(register_configs(),
                      exclude_services=['openvswitch-switch'])


def resume(args):
    """Resume the neutron-openvswitch services.
    @raises Exception should the service fail to start."""
    resume_unit_helper(register_configs(),
                       exclude_services=['openvswitch-switch'])


def restart(args):
    """Restart services.

    :param args: Unused
    :type args: List[str]
    """
    deferred_only = action_get("deferred-only")
    services = action_get("services").split()
    # Check input
    if deferred_only and services:
        action_fail("Cannot set deferred-only and services")
        return
    if not (deferred_only or services):
        action_fail("Please specify deferred-only or services")
        return
    if action_get('run-hooks'):
        _run_deferred_hooks()
    if deferred_only:
        os_utils.restart_services_action(deferred_only=True)
    else:
        os_utils.restart_services_action(services=services)
    assess_status(register_configs())


def _run_deferred_hooks():
    """Run supported deferred hooks as needed.

    Run supported deferred hooks as needed. If support for deferring a new
    hook is added to the charm then this method will need updating.
    """
    if not deferred_events.is_restart_permitted():
        deferred_hooks = deferred_events.get_deferred_hooks()
        if deferred_hooks and 'config-changed' in deferred_hooks:
            neutron_ovs_hooks.config_changed(check_deferred_restarts=False)
            deferred_events.clear_deferred_hook('config-changed')


def run_deferred_hooks(args):
    """Run deferred hooks.

    :param args: Unused
    :type args: List[str]
    """
    _run_deferred_hooks()
    os_utils.restart_services_action(deferred_only=True)
    assess_status(register_configs())


def show_deferred_events(args):
    """Show the deferred events.

    :param args: Unused
    :type args: List[str]
    """
    os_utils.show_deferred_events_action_helper()


# A dictionary of all the defined actions to callables (which take
# parsed arguments).
ACTIONS = {"pause": pause, "resume": resume, "restart-services": restart,
           "show-deferred-events": show_deferred_events,
           "run-deferred-hooks": run_deferred_hooks}


def main(args):
    action_name = os.path.basename(args[0])
    try:
        action = ACTIONS[action_name]
    except KeyError:
        s = "Action {} undefined".format(action_name)
        action_fail(s)
        return s
    else:
        try:
            action(args)
        except Exception as e:
            action_fail("Action {} failed: {}".format(action_name, str(e)))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
