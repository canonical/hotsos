#!/usr/bin/env python3
#
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

import json
import os
import subprocess
import sys
import traceback
import uuid

sys.path.append('hooks/')

_path = os.path.dirname(os.path.realpath(__file__))
_hooks = os.path.abspath(os.path.join(_path, '../hooks'))
_root = os.path.abspath(os.path.join(_path, '..'))


def _add_path(path):
    if path not in sys.path:
        sys.path.insert(1, path)


_add_path(_hooks)
_add_path(_root)


from charmhelpers.core.hookenv import (
    action_fail,
    action_get,
    action_set,
    function_fail,
    function_get,
    function_set,
    is_leader,
    log,
    relation_ids,
    relation_set,
)
from utils import (
    emit_corosync_conf,
    is_update_ring_requested,
    pause_unit,
    resume_unit,
    update_node_list,
)

import pcmk


def pause(args):
    """Pause the hacluster services.
    @raises Exception should the service fail to stop.
    """
    pause_unit()


def resume(args):
    """Resume the hacluster services.
    @raises Exception should the service fail to start."""
    resume_unit()


def status(args):
    """Show hacluster status."""
    try:
        health_status = pcmk.cluster_status(
            resources=bool(function_get("resources")),
            history=bool(function_get("history")))
        function_set({"result": json.dumps(health_status)})
    except subprocess.CalledProcessError as error:
        log("ERROR: Failed call to crm status. output: {}. return-code: {}"
            "".format(error.output, error.returncode))
        log(traceback.format_exc())
        function_set({"result": "failure"})
        function_fail("failed to get cluster health")


def cleanup(args):
    """Cleanup an/all hacluster resource(s).
        Optional arg "resource=res_xyz_abc" """
    resource_name = (action_get("resource")).lower()
    if resource_name == 'all':
        cmd = ['crm_resource', '-C']
    else:
        cmd = ['crm', 'resource', 'cleanup', resource_name]

    try:
        subprocess.check_call(cmd)
        action_set({'result': 'success'})
    except subprocess.CalledProcessError as e:
        log("ERROR: Failed call to crm resource cleanup for {}. "
            "output: {}. return-code: {}".format(resource_name, e.output,
                                                 e.returncode))
        log(traceback.format_exc())
        action_set({'result': 'failure'})
        action_fail("failed to cleanup crm resource "
                    "'{}'".format(resource_name))


def _trigger_corosync_update():
    # Trigger emit_corosync_conf() and corosync-cfgtool -R
    # for all the hanode peer units to run
    relid = relation_ids('hanode')
    if len(relid) < 1:
        action_fail('no peer ha nodes')
        return
    corosync_update_uuid = uuid.uuid1().hex
    reldata = {'trigger-corosync-update': corosync_update_uuid}
    relation_set(relation_id=relid[0],
                 relation_settings=reldata)

    # Trigger the same logic in the leader (no hanode-relation-changed
    # hook will be received by self)
    if (is_update_ring_requested(corosync_update_uuid) and
            emit_corosync_conf()):
        cmd = 'corosync-cfgtool -R'
        pcmk.commit(cmd)


def update_ring(args):
    """Update corosync.conf list of nodes (generally after unit removal)."""
    if not function_get('i-really-mean-it'):
        function_fail('i-really-mean-it is a required parameter')
        return

    if not is_leader():
        function_fail('only the Juju leader can run this action')
        return

    diff_nodes = update_node_list()
    log("Unexpected node(s) found and removed: {}"
        .format(",".join(list(diff_nodes))))
    if not diff_nodes:
        # No differences between discovered Pacemaker nodes and
        # Juju nodes (ie. no node removal)
        function_set({'result': 'No changes required.'})
        return

    # Notify the cluster
    _trigger_corosync_update()

    function_set(
        {"result":
            "Nodes removed: {}"
            .format(" ".join(list(diff_nodes)))})


def delete_node_from_ring(args):
    """Delete a node from the corosync ring."""

    node = function_get('node')
    if not node:
        function_fail('node is a required parameter')
        return

    if not is_leader():
        function_fail('only the Juju leader can run this action')
        return

    # Delete the node from the live corosync env
    try:
        pcmk.set_node_status_to_maintenance(node)
        pcmk.delete_node(node, failure_is_fatal=True)
    except subprocess.CalledProcessError as e:
        function_fail(
            "Removing {} from the cluster failed. {} output={}"
            .format(node, e, e.output))

    # Notify the cluster
    _trigger_corosync_update()

    function_set({'result': 'success'})


ACTIONS = {"pause": pause, "resume": resume,
           "status": status, "cleanup": cleanup,
           "delete-node-from-ring": delete_node_from_ring,
           "update-ring": update_ring}


def main(args):
    action_name = os.path.basename(args[0])
    try:
        action = ACTIONS[action_name]
    except KeyError:
        return "Action %s undefined" % action_name
    else:
        try:
            action(args)
        except Exception as e:
            action_fail(str(e))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
