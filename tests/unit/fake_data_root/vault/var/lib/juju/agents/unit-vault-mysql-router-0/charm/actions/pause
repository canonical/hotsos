#!/usr/bin/env python3
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

import os
import sys

# Load modules from $CHARM_DIR/lib
sys.path.append('lib')

from charms.layer import basic
basic.bootstrap_charm_deps()

import charmhelpers.core.hookenv as hookenv
import charmhelpers.core as ch_core
import charms_openstack.bus
import charms_openstack.charm

charms_openstack.bus.discover()


def pause_action(*args):
    """Run the pause action."""
    with charms_openstack.charm.provide_charm_instance() as charm_instance:
        charm_instance.pause()
        # Run _assess_status rather than assess_status so the call is not
        # deferred.
        charm_instance._assess_status()


def resume_action(*args):
    """Run the resume action."""
    with charms_openstack.charm.provide_charm_instance() as charm_instance:
        charm_instance.resume()
        # Run _assess_status rather than assess_status so the call is not
        # deferred.
        charm_instance._assess_status()


def restart_services(*args):
    """Run the resume action."""
    with charms_openstack.charm.provide_charm_instance() as charm_instance:
        charm_instance.restart_services()


# Actions to function mapping, to allow for illegal python action names that
# can map to a python function.
ACTIONS = {
    "pause": pause_action,
    "resume": resume_action,
    "restart-services": restart_services,
}


def main(args):
    # Manually trigger any register atstart events to ensure all endpoints
    # are correctly setup, Bug #1916008.
    ch_core.hookenv._run_atstart()
    action_name = os.path.basename(args[0])
    try:
        action = ACTIONS[action_name]
    except KeyError:
        return "Action %s undefined" % action_name
    else:
        try:
            action(args)
        except Exception as e:
            hookenv.action_fail(str(e))
    ch_core.hookenv._run_atexit()


if __name__ == "__main__":
    sys.exit(main(sys.argv))
