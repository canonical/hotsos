#!/usr/local/sbin/charm-env python3
# Copyright 2019 Canonical Ltd
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

# Load modules from $CHARM_DIR/lib
_path = os.path.dirname(os.path.realpath(__file__))
_lib = os.path.abspath(os.path.join(_path, "../lib"))
_reactive = os.path.abspath(os.path.join(_path, "../reactive"))


def _add_path(path):
    if path not in sys.path:
        sys.path.insert(1, path)


_add_path(_lib)
_add_path(_reactive)

import charms_openstack.charm as charm
import charmhelpers.core as ch_core
import charms_openstack.bus
charms_openstack.bus.discover()


def stop_mysqlrouter(args):
    """Display cluster status

    Return cluster.status() as a JSON encoded dictionary

    :param args: sys.argv
    :type args: sys.argv
    :side effect: Calls instance.get_cluster_status
    :returns: This function is called for its side effect
    :rtype: None
    :action return: Dictionary with command output
    """
    with charm.provide_charm_instance() as instance:
        try:
            instance.stop_mysqlrouter()
            instance.assess_status()
            ch_core.hookenv.action_set({"outcome": "Success"})
        except subprocess.CalledProcessError as e:
            ch_core.hookenv.action_set({
                "output": e.output,
                "return-code": e.returncode,
                "traceback": traceback.format_exc()})
            ch_core.hookenv.action_fail("Stop MySQLRouter failed.")


def start_mysqlrouter(args):
    """Display cluster status

    Return cluster.status() as a JSON encoded dictionary

    :param args: sys.argv
    :type args: sys.argv
    :side effect: Calls instance.get_cluster_status
    :returns: This function is called for its side effect
    :rtype: None
    :action return: Dictionary with command output
    """
    with charm.provide_charm_instance() as instance:
        try:
            instance.start_mysqlrouter()
            instance.assess_status()
            ch_core.hookenv.action_set({"outcome": "Success"})
        except subprocess.CalledProcessError as e:
            ch_core.hookenv.action_set({
                "output": e.output,
                "return-code": e.returncode,
                "traceback": traceback.format_exc()})
            ch_core.hookenv.action_fail("Start MySQLRouter failed.")


def restart_mysqlrouter(args):
    """Display cluster status

    Return cluster.status() as a JSON encoded dictionary

    :param args: sys.argv
    :type args: sys.argv
    :side effect: Calls instance.get_cluster_status
    :returns: This function is called for its side effect
    :rtype: None
    :action return: Dictionary with command output
    """
    with charm.provide_charm_instance() as instance:
        try:
            instance.restart_mysqlrouter()
            instance.assess_status()
            ch_core.hookenv.action_set({"outcome": "Success"})
        except subprocess.CalledProcessError as e:
            ch_core.hookenv.action_set({
                "output": e.output,
                "return-code": e.returncode,
                "traceback": traceback.format_exc()})
            ch_core.hookenv.action_fail("Retart MySQLRouter failed.")


# A dictionary of all the defined actions to callables (which take
# parsed arguments).
ACTIONS = {"stop-mysqlrouter": stop_mysqlrouter,
           "start-mysqlrouter": start_mysqlrouter,
           "restart-mysqlrouter": restart_mysqlrouter}


def main(args):
    action_name = os.path.basename(args[0])
    try:
        action = ACTIONS[action_name]
    except KeyError:
        return "Action {} undefined".format(action_name)
    else:
        try:
            action(args)
        except Exception as e:
            ch_core.hookenv.action_set({
                "output": e.output.decode("UTF-8"),
                "return-code": e.returncode,
                "traceback": traceback.format_exc()})
            ch_core.hookenv.action_fail(
                "{} action failed.".format(action_name))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
