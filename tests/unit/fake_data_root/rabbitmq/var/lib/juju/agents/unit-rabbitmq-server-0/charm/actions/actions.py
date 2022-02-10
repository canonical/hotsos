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
import re
from collections import OrderedDict
from subprocess import check_output, CalledProcessError, PIPE
import sys


_path = os.path.dirname(os.path.realpath(__file__))
_root = os.path.abspath(os.path.join(_path, '..'))
_hooks = os.path.abspath(os.path.join(_path, '../hooks'))


def _add_path(path):
    if path not in sys.path:
        sys.path.insert(1, path)


_add_path(_root)
_add_path(_hooks)

import charmhelpers.contrib.openstack.deferred_events as deferred_events
import charmhelpers.contrib.openstack.utils as os_utils

from charmhelpers.core.host import (
    service_start,
    service_stop,
)

from charmhelpers.core.hookenv import (
    action_fail,
    action_set,
    action_get,
    is_leader,
    leader_set,
    log,
    INFO,
    ERROR,
)

from charmhelpers.core.host import (
    cmp_pkgrevno,
)

import rabbitmq_server_relations

from hooks.rabbit_utils import (
    ConfigRenderer,
    CONFIG_FILES,
    pause_unit_helper,
    resume_unit_helper,
    assess_status,
    list_vhosts,
    vhost_queue_info,
    rabbitmq_version_newer_or_equal,
)


def pause(args):
    """Pause the RabbitMQ services.
    @raises Exception should the service fail to stop.
    """
    pause_unit_helper(ConfigRenderer(CONFIG_FILES()))


def resume(args):
    """Resume the RabbitMQ services.
    @raises Exception should the service fail to start."""
    resume_unit_helper(ConfigRenderer(CONFIG_FILES()))


def cluster_status(args):
    """Return the output of 'rabbitmqctl cluster_status'."""
    try:
        if rabbitmq_version_newer_or_equal('3.7'):
            clusterstat = check_output(['rabbitmqctl', 'cluster_status',
                                        '--formatter', 'json'],
                                       universal_newlines=True)

            clusterstat = json.loads(clusterstat)
            action_set({'output': json.dumps(clusterstat, indent=4)})
        else:
            clusterstat = check_output(['rabbitmqctl', 'cluster_status'],
                                       universal_newlines=True)
            action_set({'output': clusterstat})
    except CalledProcessError as e:
        action_set({'output': e.output})
        action_fail('Failed to run rabbitmqctl cluster_status')
    except Exception:
        raise


def check_queues(args):
    """Check for queues with greater than N messages.
    Return those queues to the user."""
    queue_depth = (action_get('queue-depth'))
    vhost = (action_get('vhost'))
    # rabbitmqctl's output contains lines we don't want, such as
    # 'Listing queues ..' and '...done.', which may vary by release.
    # Actual queue results *should* always look like 'test\t0'
    queue_pattern = re.compile(r"^(.*)\t([0-9]+$)")
    try:
        queue_lines = check_output(
            ['rabbitmqctl', 'list_queues', '-q', '-p', vhost]
        ).decode('utf-8').splitlines()
        filtered = filter(
            None,  # filter out empty records
            map(lambda line: queue_pattern.findall(line), queue_lines))
        queues = [(queue, int(size)) for [[queue, size]] in filtered]
        result = {queue: size for queue, size in queues if size >= queue_depth}
        action_set({'output': result, 'outcome': 'Success'})
    except CalledProcessError as e:
        action_set({'output': e.output})
        action_fail('Failed to run rabbitmqctl list_queues')


def complete_cluster_series_upgrade(args):
    """ Complete the series upgrade process

    After all nodes have been upgraded, this action is run to inform the whole
    cluster the upgrade is done. Config files will be re-rendered with each
    peer in the wsrep_cluster_address config.
    """
    if is_leader():
        # Unset cluster_series_upgrading
        leader_set(cluster_series_upgrading="")
    assess_status(ConfigRenderer(CONFIG_FILES()))


def forget_cluster_node(args):
    """Remove previously departed node from cluster."""
    node = (action_get('node'))
    if cmp_pkgrevno('rabbitmq-server', '3.0.0') < 0:
        action_fail(
            'rabbitmq-server version < 3.0.0, '
            'forget_cluster_node not supported.')
        return
    try:
        output = check_output(
            ['rabbitmqctl', 'forget_cluster_node', node],
            stderr=PIPE)
        action_set({'output': output.decode('utf-8'), 'outcome': 'Success'})
    except CalledProcessError as e:
        action_set({'output': e.stderr})
        if e.returncode == 2:
            action_fail(
                "Unable to remove node '{}' from cluster. It is either still "
                "running or already removed. (Output: '{}')"
                .format(node, e.stderr))
        else:
            action_fail('Failed running rabbitmqctl forget_cluster_node')


def list_unconsumed_queues(args):
    """List queues which are unconsumed in RabbitMQ"""
    log("Listing unconsumed queues...", level=INFO)
    count = 0
    for vhost in list_vhosts():
        try:
            queue_info_dict = vhost_queue_info(vhost)
        except CalledProcessError as e:
            # if no queues, just raises an exception
            action_set({'output': e.output,
                        'return-code': e.returncode})
            action_fail("Failed to query RabbitMQ vhost {} queues"
                        "".format(vhost))
            return False

        for queue in queue_info_dict:
            if queue['consumers'] == 0:
                vhostqueue = ''
                value = ''
                try:
                    vhostqueue = "unconsumed-queues.{}".format(count)
                    value = OrderedDict((
                        ('vhost', vhost),
                        ('name', queue['name']),
                        ('messages', queue['messages']),
                    ))
                    action_set({vhostqueue: json.dumps(value)})
                except Exception as e:
                    log('{}, vhostqueue={}, value={}'.format(
                        e, vhostqueue, value), level=ERROR)
                count += 1

    log("{} unconsumed queue(s) found".format(count), level=INFO)
    action_set({'unconsumed-queue-count': count})


def force_boot(args):
    """Set the force_boot flag and start RabbitMQ broker"""
    try:
        service_stop('rabbitmq-server')
    except CalledProcessError as e:
        action_set({'output': e.output})
        action_fail('Failed to stop rabbitmqctl service')
        return False

    try:
        force_boot = check_output(['rabbitmqctl', 'force_boot'],
                                  universal_newlines=True)
        action_set({'output': force_boot})
    except CalledProcessError as e:
        action_set({'output': e.output})
        action_fail('Failed to run rabbitmqctl force_boot')
        return False

    try:
        service_start('rabbitmq-server')
    except CalledProcessError as e:
        action_set({'output': e.output})
        action_fail('Failed to start rabbitmqctl service after force_boot')
        return False


def restart(args):
    """Restart services.

    :param args: Unused
    :type args: List[str]
    """
    deferred_only = action_get("deferred-only")
    svcs = action_get("services").split()
    # Check input
    if deferred_only and svcs:
        action_fail("Cannot set deferred-only and services")
        return
    if not (deferred_only or svcs):
        action_fail("Please specify deferred-only or services")
        return
    if action_get('run-hooks'):
        _run_deferred_hooks()
    if deferred_only:
        os_utils.restart_services_action(deferred_only=True)
    else:
        os_utils.restart_services_action(services=svcs)
    assess_status(ConfigRenderer(CONFIG_FILES()))


def _run_deferred_hooks():
    """Run supported deferred hooks as needed.

    Run supported deferred hooks as needed. If support for deferring a new
    hook is added to the charm then this method will need updating.
    """
    if not deferred_events.is_restart_permitted():
        if 'config-changed' in deferred_events.get_deferred_hooks():
            log("Running hook config-changed", level=INFO)
            rabbitmq_server_relations.config_changed(
                check_deferred_restarts=False)
            deferred_events.clear_deferred_hook('config-changed')
        if 'amqp-relation-changed' in deferred_events.get_deferred_hooks():
            log("Running hook amqp-relation-changed", level=INFO)
            # update_clients cycles through amqp relations running
            # amqp-relation-changed hook.
            rabbitmq_server_relations.update_clients(
                check_deferred_restarts=False)
            deferred_events.clear_deferred_hook('amqp-relation-changed')
    log("Remaining hooks: {}".format(
        deferred_events.get_deferred_hooks()),
        level=INFO)


def run_deferred_hooks(args):
    """Run deferred hooks.

    :param args: Unused
    :type args: List[str]
    """
    _run_deferred_hooks()
    os_utils.restart_services_action(deferred_only=True)
    assess_status(ConfigRenderer(CONFIG_FILES()))


def show_deferred_events(args):
    """Show the deferred events.

    :param args: Unused
    :type args: List[str]
    """
    os_utils.show_deferred_events_action_helper()


# A dictionary of all the defined actions to callables (which take
# parsed arguments).
ACTIONS = {
    "pause": pause,
    "resume": resume,
    "cluster-status": cluster_status,
    "check-queues": check_queues,
    "complete-cluster-series-upgrade": complete_cluster_series_upgrade,
    "forget-cluster-node": forget_cluster_node,
    "list-unconsumed-queues": list_unconsumed_queues,
    "force-boot": force_boot,
    "restart-services": restart,
    "run-deferred-hooks": run_deferred_hooks,
    "show-deferred-events": show_deferred_events,
}


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
