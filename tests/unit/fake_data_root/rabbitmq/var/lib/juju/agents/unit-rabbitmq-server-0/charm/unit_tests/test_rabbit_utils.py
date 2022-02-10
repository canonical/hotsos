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

import collections
from functools import wraps
import json
from unittest import mock
import os
import sys
import tempfile
from datetime import timedelta

from unit_tests.test_utils import CharmTestCase

with mock.patch('charmhelpers.core.hookenv.cached') as cached:
    def passthrough(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            return func(*args, **kwargs)
        wrapper._wrapped = func
        return wrapper
    cached.side_effect = passthrough
    import rabbit_utils

sys.modules['MySQLdb'] = mock.Mock()

TO_PATCH = [
    # charmhelpers.core.hookenv
    'is_leader',
    'related_units',
    'relation_ids',
    'relation_get',
    'relation_set',
    'related_units',
    'leader_get',
    'config',
    'is_unit_paused_set',
    'local_unit',
    'lsb_release',
]


class ConfigRendererTests(CharmTestCase):

    class FakeContext(object):
        def __call__(self, *a, **k):
            return {'foo': 'bar'}

    config_map = collections.OrderedDict(
        [('/this/is/a/config', {
            'hook_contexts': [
                FakeContext()
            ]
        })]
    )

    def setUp(self):
        super(ConfigRendererTests, self).setUp(rabbit_utils,
                                               TO_PATCH)
        self.renderer = rabbit_utils.ConfigRenderer(
            self.config_map)

    def test_has_config_data(self):
        self.assertTrue(
            '/this/is/a/config' in self.renderer.config_data.keys())

    @mock.patch("rabbit_utils.log")
    @mock.patch("rabbit_utils.render")
    def test_write_all(self, log, render):
        self.renderer.write_all()

        self.assertTrue(render.called)
        self.assertTrue(log.called)


RABBITMQCTL_CLUSTERSTATUS_RUNNING = b"""Cluster status of node 'rabbit@juju-devel3-machine-19' ...
[{nodes,
    [{disc,
        ['rabbit@juju-devel3-machine-14','rabbit@juju-devel3-machine-19']},
     {ram,
        ['rabbit@juju-devel3-machine-42']}]},
 {running_nodes,
    ['rabbit@juju-devel3-machine-14','rabbit@juju-devel3-machine-19']},
 {cluster_name,<<"rabbit@juju-devel3-machine-14.openstacklocal">>},
 {partitions,[]}]
 """

RABBITMQCTL_CLUSTERSTATUS_RUNNING_382 = b"""
{"running_nodes": [
    "rabbit@juju-devel3-machine-14",
    "rabbit@juju-devel3-machine-19"],
 "disk_nodes":
    ["rabbit@juju-devel3-machine-14",
     "rabbit@juju-devel3-machine-19"],
 "ram_nodes": ["rabbit@juju-devel3-machine-42"]
}
"""


RABBITMQCTL_CLUSTERSTATUS_SOLO = b"""Cluster status of node 'rabbit@juju-devel3-machine-14' ...
[{nodes,[{disc,['rabbit@juju-devel3-machine-14']}]},
 {running_nodes,['rabbit@juju-devel3-machine-14']},
 {cluster_name,<<"rabbit@juju-devel3-machine-14.openstacklocal">>},
 {partitions,[]}]
 """


RABBITMQCTL_CLUSTERSTATUS_SOLO_382 = b"""
{"running_nodes": [
    "rabbit@juju-devel3-machine-14"],
 "disk_nodes":
    ["rabbit@juju-devel3-machine-14"],
 "ram_nodes": []
}
"""


RABBITMQCTL_LIST_QUEUES = b"""Listing queues ...
a_sample_queue	0	1
cinder-scheduler.cinder	0	1
cinder-fanout-12345	250	0
myqueue	0	1
...done
"""

RABBITMQCTL_LIST_QUEUES_382 = (
    b'[{"name": "a_sample_queue", "messages": 0, "consumers": 1},'
    b'{"name": "cinder-scheduler.cinder", "messages": 0, "consumers": 1},'
    b'{"name": "cinder-fanout-12345", "messages": 250, "consumers": 0},'
    b'{"name": "myqueue", "messages": 0, "consumers": 1}]')

RABBITMQCTL_LIST_VHOSTS = b"""Listing vhosts ...
/
landscape
openstack
...done
"""

RABBITMQCTL_LIST_VHOSTS_382 = (b'[{"name": "/"},{"name": "landscape"},'
                               b'{"name": "openstack"}]')


class UtilsTests(CharmTestCase):
    def setUp(self):
        super(UtilsTests, self).setUp(rabbit_utils,
                                      TO_PATCH)
        self.tmp_dir = tempfile.mkdtemp()
        self.nrpe_compat = mock.MagicMock()
        self.nrpe_compat.add_check = mock.MagicMock()
        self.nrpe_compat.remove_check = mock.MagicMock()
        self.lsb_release.return_value = {
            'DISTRIB_CODENAME': 'focal'}

    def tearDown(self):
        super(UtilsTests, self).tearDown()
        self.nrpe_compat.reset_mock()

    @mock.patch("rabbit_utils.log")
    def test_update_empty_hosts_file(self, mock_log):
        _map = {'1.2.3.4': 'my-host'}
        with tempfile.NamedTemporaryFile(delete=False) as tmpfile:
            rabbit_utils.HOSTS_FILE = tmpfile.name
            rabbit_utils.HOSTS_FILE = tmpfile.name
            rabbit_utils.update_hosts_file(_map)

        with open(tmpfile.name, 'r') as fd:
            lines = fd.readlines()

        os.remove(tmpfile.name)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0], "%s %s\n" % (list(_map.items())[0]))

    @mock.patch("rabbit_utils.log")
    def test_update_hosts_file_w_dup(self, mock_log):
        _map = {'1.2.3.4': 'my-host'}
        with tempfile.NamedTemporaryFile(delete=False) as tmpfile:
            rabbit_utils.HOSTS_FILE = tmpfile.name

            with open(tmpfile.name, 'w') as fd:
                fd.write("%s %s\n" % (list(_map.items())[0]))

            rabbit_utils.update_hosts_file(_map)

        with open(tmpfile.name, 'r') as fd:
            lines = fd.readlines()

        os.remove(tmpfile.name)
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0], "%s %s\n" % (list(_map.items())[0]))

    @mock.patch("rabbit_utils.log")
    def test_update_hosts_file_entry(self, mock_log):
        altmap = {'1.1.1.1': 'alt-host'}
        _map = {'1.1.1.1': 'hostA',
                '2.2.2.2': 'hostB',
                '3.3.3.3': 'hostC',
                '4.4.4.4': 'hostD'}
        with tempfile.NamedTemporaryFile(delete=False) as tmpfile:
            rabbit_utils.HOSTS_FILE = tmpfile.name

            with open(tmpfile.name, 'w') as fd:
                fd.write("#somedata\n")
                fd.write("%s %s\n" % (list(altmap.items())[0]))

            rabbit_utils.update_hosts_file(_map)

        with open(rabbit_utils.HOSTS_FILE, 'r') as fd:
            lines = fd.readlines()

        os.remove(tmpfile.name)
        self.assertEqual(len(lines), 5)
        self.assertEqual(lines[0], "#somedata\n")
        self.assertEqual(lines[1], "%s %s\n" % (list(_map.items())[0]))
        self.assertEqual(lines[4], "%s %s\n" % (list(_map.items())[3]))

    @mock.patch('rabbit_utils.running_nodes')
    def test_not_clustered(self, mock_running_nodes):
        print("test_not_clustered")
        mock_running_nodes.return_value = []
        self.assertFalse(rabbit_utils.clustered())

    @mock.patch('rabbit_utils.running_nodes')
    def test_clustered(self, mock_running_nodes):
        mock_running_nodes.return_value = ['a', 'b']
        self.assertTrue(rabbit_utils.clustered())

    @mock.patch('rabbit_utils.caching_cmp_pkgrevno')
    @mock.patch('rabbit_utils.subprocess')
    def test_nodes(self, mock_subprocess, mock_cmp_pkgrevno):
        '''Ensure cluster_status can be parsed for a clustered deployment'''
        mock_subprocess.check_output.return_value = \
            RABBITMQCTL_CLUSTERSTATUS_RUNNING
        mock_cmp_pkgrevno.return_value = -1
        self.assertEqual(rabbit_utils.nodes(),
                         ['rabbit@juju-devel3-machine-14',
                          'rabbit@juju-devel3-machine-19',
                          'rabbit@juju-devel3-machine-42'])

    @mock.patch('rabbit_utils.caching_cmp_pkgrevno')
    @mock.patch('rabbit_utils.subprocess')
    def test_nodes_382(self, mock_subprocess, mock_cmp_pkgrevno):
        '''Ensure cluster_status can be parsed for a clustered deployment'''
        mock_subprocess.check_output.return_value = \
            RABBITMQCTL_CLUSTERSTATUS_RUNNING_382
        mock_cmp_pkgrevno.return_value = 0
        self.assertEqual(rabbit_utils.nodes(),
                         ['rabbit@juju-devel3-machine-14',
                          'rabbit@juju-devel3-machine-19',
                          'rabbit@juju-devel3-machine-42'])

    @mock.patch('rabbit_utils.caching_cmp_pkgrevno')
    @mock.patch('rabbit_utils.subprocess')
    def test_running_nodes(self, mock_subprocess, mock_cmp_pkgrevno):
        '''Ensure cluster_status can be parsed for a clustered deployment'''
        mock_subprocess.check_output.return_value = \
            RABBITMQCTL_CLUSTERSTATUS_RUNNING
        mock_cmp_pkgrevno.return_value = -1
        self.assertEqual(rabbit_utils.running_nodes(),
                         ['rabbit@juju-devel3-machine-14',
                          'rabbit@juju-devel3-machine-19'])

    @mock.patch('rabbit_utils.caching_cmp_pkgrevno')
    @mock.patch('rabbit_utils.subprocess')
    def test_running_nodes_382(self, mock_subprocess, mock_cmp_pkgrevno):
        '''Ensure cluster_status can be parsed for a clustered deployment'''
        mock_subprocess.check_output.return_value = \
            RABBITMQCTL_CLUSTERSTATUS_RUNNING_382
        mock_cmp_pkgrevno.return_value = 0
        self.assertEqual(rabbit_utils.running_nodes(),
                         ['rabbit@juju-devel3-machine-14',
                          'rabbit@juju-devel3-machine-19'])

    @mock.patch('rabbit_utils.caching_cmp_pkgrevno')
    @mock.patch('rabbit_utils.subprocess')
    def test_get_cluster_status(self, mock_subprocess, mock_cmp_pkgrevno):
        mock_subprocess.check_output.return_value = b'{"status": "tip top"}'
        mock_cmp_pkgrevno.return_value = -1
        with self.assertRaises(NotImplementedError):
            rabbit_utils.get_cluster_status()
        mock_cmp_pkgrevno.return_value = 1
        self.assertEqual(
            rabbit_utils.get_cluster_status(),
            {'status': 'tip top'})
        mock_subprocess.check_output.reset_mock()
        self.assertEqual(
            rabbit_utils.get_cluster_status(cmd_timeout=42),
            {'status': 'tip top'})
        mock_subprocess.check_output.assert_called_once_with(
            ['/usr/sbin/rabbitmqctl', 'cluster_status', '--formatter=json'],
            timeout=42)

    @mock.patch('rabbit_utils.get_cluster_status')
    def test_is_partitioned(self, get_cluster_status):
        get_cluster_status.return_value = {'partitions': {}}
        self.assertFalse(rabbit_utils.is_partitioned())
        get_cluster_status.return_value = {
            'partitions': {'node1': ['node2', 'node3']}}
        self.assertTrue(rabbit_utils.is_partitioned())

    @mock.patch('rabbit_utils.caching_cmp_pkgrevno')
    @mock.patch('rabbit_utils.subprocess')
    def test_list_vhosts(self, mock_subprocess, mock_cmp_pkgrevno):
        '''Ensure list_vhosts parses output into the proper list'''
        mock_subprocess.check_output.return_value = \
            RABBITMQCTL_LIST_VHOSTS
        mock_cmp_pkgrevno.return_value = -1
        self.assertEqual(rabbit_utils.list_vhosts(),
                         ['/', 'landscape', 'openstack'])

    @mock.patch('rabbit_utils.caching_cmp_pkgrevno')
    @mock.patch('rabbit_utils.subprocess')
    def test_list_vhosts_382(self, mock_subprocess, mock_cmp_pkgrevno):
        '''Ensure list_vhosts parses output into the proper list for
        rabbitmq_server 3.8.2+
        '''
        mock_subprocess.check_output.return_value = \
            RABBITMQCTL_LIST_VHOSTS_382
        mock_cmp_pkgrevno.return_value = 0
        self.assertEqual(rabbit_utils.list_vhosts(),
                         ['/', 'landscape', 'openstack'])

    @mock.patch('rabbit_utils.caching_cmp_pkgrevno')
    @mock.patch('rabbit_utils.subprocess')
    def test_vhost_queue_info(self, mock_subprocess, mock_cmp_pkgrevno):
        '''Ensure vhost_queue_info parses output into the proper format/info'''
        mock_subprocess.check_output.return_value = \
            RABBITMQCTL_LIST_QUEUES
        mock_cmp_pkgrevno.return_value = -1
        self.assertEqual(rabbit_utils.vhost_queue_info('openstack'),
                         [{'name': 'a_sample_queue', 'messages': 0,
                           'consumers': 1},
                          {'name': 'cinder-scheduler.cinder', 'messages': 0,
                           'consumers': 1},
                          {'name': 'cinder-fanout-12345', 'messages': 250,
                           'consumers': 0},
                          {'name': 'myqueue', 'messages': 0, 'consumers': 1}])

    @mock.patch('rabbit_utils.caching_cmp_pkgrevno')
    @mock.patch('rabbit_utils.subprocess')
    def test_vhost_queue_info_382(self, mock_subprocess, mock_cmp_pkgrevno):
        '''Ensure vhost_queue_info parses output into the proper format/info'''
        mock_subprocess.check_output.return_value = \
            RABBITMQCTL_LIST_QUEUES_382
        mock_cmp_pkgrevno.return_value = 0
        self.assertEqual(rabbit_utils.vhost_queue_info('openstack'),
                         [{'name': 'a_sample_queue', 'messages': 0,
                           'consumers': 1},
                          {'name': 'cinder-scheduler.cinder', 'messages': 0,
                           'consumers': 1},
                          {'name': 'cinder-fanout-12345', 'messages': 250,
                           'consumers': 0},
                          {'name': 'myqueue', 'messages': 0, 'consumers': 1}])

    @mock.patch('rabbit_utils.caching_cmp_pkgrevno')
    @mock.patch('rabbit_utils.subprocess')
    def test_nodes_solo(self, mock_subprocess, mock_cmp_pkgrevno):
        '''Ensure cluster_status can be parsed for a single unit deployment'''
        mock_subprocess.check_output.return_value = \
            RABBITMQCTL_CLUSTERSTATUS_SOLO
        mock_cmp_pkgrevno.return_value = -1
        self.assertEqual(rabbit_utils.nodes(),
                         ['rabbit@juju-devel3-machine-14'])

    @mock.patch('rabbit_utils.caching_cmp_pkgrevno')
    @mock.patch('rabbit_utils.subprocess')
    def test_nodes_solo_382(self, mock_subprocess, mock_cmp_pkgrevno):
        '''Ensure cluster_status can be parsed for a single unit deployment'''
        mock_subprocess.check_output.return_value = \
            RABBITMQCTL_CLUSTERSTATUS_SOLO_382
        mock_cmp_pkgrevno.return_value = 0
        self.assertEqual(rabbit_utils.nodes(),
                         ['rabbit@juju-devel3-machine-14'])

    @mock.patch('rabbit_utils.caching_cmp_pkgrevno')
    @mock.patch('rabbit_utils.subprocess')
    def test_running_nodes_solo(self, mock_subprocess, mock_cmp_pkgrevno):
        '''Ensure cluster_status can be parsed for a single unit deployment'''
        mock_subprocess.check_output.return_value = \
            RABBITMQCTL_CLUSTERSTATUS_SOLO
        mock_cmp_pkgrevno.return_value = -1
        self.assertEqual(rabbit_utils.running_nodes(),
                         ['rabbit@juju-devel3-machine-14'])

    @mock.patch('rabbit_utils.caching_cmp_pkgrevno')
    @mock.patch('rabbit_utils.subprocess')
    def test_running_nodes_solo_382(self, mock_subprocess, mock_cmp_pkgrevno):
        '''Ensure cluster_status can be parsed for a single unit deployment'''
        mock_subprocess.check_output.return_value = \
            RABBITMQCTL_CLUSTERSTATUS_SOLO_382
        mock_cmp_pkgrevno.return_value = 0
        self.assertEqual(rabbit_utils.running_nodes(),
                         ['rabbit@juju-devel3-machine-14'])

    @mock.patch('rabbit_utils.get_hostname')
    def test_get_node_hostname(self, mock_get_hostname):
        mock_get_hostname.return_value = 'juju-devel3-machine-13'
        self.assertEqual(rabbit_utils.get_node_hostname('192.168.20.50'),
                         'juju-devel3-machine-13')
        mock_get_hostname.assert_called_with('192.168.20.50', fqdn=False)

    @mock.patch('rabbit_utils.peer_retrieve')
    def test_leader_node(self, mock_peer_retrieve):
        mock_peer_retrieve.return_value = 'juju-devel3-machine-15'
        self.assertEqual(rabbit_utils.leader_node(),
                         'rabbit@juju-devel3-machine-15')

    @mock.patch('rabbit_utils.is_unit_paused_set')
    @mock.patch('rabbit_utils.cluster_wait')
    @mock.patch('rabbit_utils.relation_set')
    @mock.patch('rabbit_utils.wait_app')
    @mock.patch('rabbit_utils.subprocess.check_call')
    @mock.patch('rabbit_utils.subprocess.check_output')
    @mock.patch('rabbit_utils.time')
    @mock.patch('rabbit_utils.running_nodes')
    @mock.patch('rabbit_utils.leader_node')
    @mock.patch('rabbit_utils.clustered')
    @mock.patch('rabbit_utils.cmp_pkgrevno')
    @mock.patch('rabbit_utils.rabbitmq_version_newer_or_equal')
    def test_cluster_with_not_clustered(
            self, mock_new_rabbitmq, mock_cmp_pkgrevno, mock_clustered,
            mock_leader_node, mock_running_nodes, mock_time, mock_check_output,
            mock_check_call, mock_wait_app, mock_relation_set,
            mock_cluster_wait, mock_is_unit_paused_set):
        mock_new_rabbitmq.return_value = True
        mock_is_unit_paused_set.return_value = False
        mock_cmp_pkgrevno.return_value = True
        mock_clustered.return_value = False
        mock_leader_node.return_value = 'rabbit@juju-devel7-machine-11'
        mock_running_nodes.return_value = ['rabbit@juju-devel5-machine-19']
        rabbit_utils.cluster_with()
        mock_cluster_wait.assert_called_once_with()
        mock_check_output.assert_called_with([rabbit_utils.RABBITMQ_CTL,
                                              'join_cluster',
                                              'rabbit@juju-devel7-machine-11'],
                                             stderr=-2)

    @mock.patch('rabbit_utils.is_unit_paused_set')
    @mock.patch('rabbit_utils.relation_get')
    @mock.patch('rabbit_utils.relation_id')
    @mock.patch('rabbit_utils.peer_retrieve')
    @mock.patch('rabbit_utils.subprocess.check_call')
    @mock.patch('rabbit_utils.subprocess.check_output')
    @mock.patch('rabbit_utils.time')
    @mock.patch('rabbit_utils.running_nodes')
    @mock.patch('rabbit_utils.leader_node')
    @mock.patch('rabbit_utils.clustered')
    @mock.patch('rabbit_utils.cmp_pkgrevno')
    def test_cluster_with_clustered(self, mock_cmp_pkgrevno, mock_clustered,
                                    mock_leader_node, mock_running_nodes,
                                    mock_time, mock_check_output,
                                    mock_check_call, mock_peer_retrieve,
                                    mock_relation_id, mock_relation_get,
                                    mock_is_unit_paused_set):
        mock_is_unit_paused_set.return_value = False
        mock_clustered.return_value = True
        mock_peer_retrieve.return_value = 'juju-devel7-machine-11'
        mock_leader_node.return_value = 'rabbit@juju-devel7-machine-11'
        mock_running_nodes.return_value = ['rabbit@juju-devel5-machine-19',
                                           'rabbit@juju-devel7-machine-11']
        mock_relation_id.return_value = 'cluster:1'
        rabbit_utils.cluster_with()
        self.assertEqual(0, mock_check_output.call_count)

    @mock.patch('rabbit_utils.wait_app')
    @mock.patch('rabbit_utils.subprocess.check_call')
    @mock.patch('rabbit_utils.subprocess.check_output')
    @mock.patch('rabbit_utils.time')
    @mock.patch('rabbit_utils.running_nodes')
    @mock.patch('rabbit_utils.leader_node')
    @mock.patch('rabbit_utils.clustered')
    @mock.patch('rabbit_utils.cmp_pkgrevno')
    def test_cluster_with_no_leader(self, mock_cmp_pkgrevno, mock_clustered,
                                    mock_leader_node, mock_running_nodes,
                                    mock_time, mock_check_output,
                                    mock_check_call, mock_wait_app):
        mock_clustered.return_value = False
        mock_leader_node.return_value = None
        mock_running_nodes.return_value = ['rabbit@juju-devel5-machine-19']
        rabbit_utils.cluster_with()
        self.assertEqual(0, mock_check_output.call_count)

    @mock.patch('rabbit_utils.is_unit_paused_set')
    @mock.patch('time.time')
    @mock.patch('rabbit_utils.relation_set')
    @mock.patch('rabbit_utils.get_unit_hostname')
    @mock.patch('rabbit_utils.relation_get')
    @mock.patch('rabbit_utils.relation_id')
    @mock.patch('rabbit_utils.running_nodes')
    @mock.patch('rabbit_utils.peer_retrieve')
    def test_cluster_with_single_node(self, mock_peer_retrieve,
                                      mock_running_nodes, mock_relation_id,
                                      mock_relation_get,
                                      mock_get_unit_hostname,
                                      mock_relation_set, mock_time,
                                      mock_is_unit_paused_set):
        mock_is_unit_paused_set.return_value = False
        mock_peer_retrieve.return_value = 'localhost'
        mock_running_nodes.return_value = ['rabbit@localhost']
        mock_relation_id.return_value = 'cluster:1'
        mock_relation_get.return_value = False
        mock_get_unit_hostname.return_value = 'localhost'
        mock_time.return_value = 1234.1

        self.assertFalse(rabbit_utils.cluster_with())

        mock_relation_set.assert_called_with(relation_id='cluster:1',
                                             clustered='localhost',
                                             timestamp=1234.1)

    @mock.patch('rabbit_utils.application_version_set')
    @mock.patch('rabbit_utils.get_upstream_version')
    def test_assess_status(self, mock_get_upstream_version,
                           mock_application_version_set):
        mock_get_upstream_version.return_value = None
        with mock.patch.object(rabbit_utils, 'assess_status_func') as asf:
            callee = mock.MagicMock()
            asf.return_value = callee
            rabbit_utils.assess_status('test-config')
            asf.assert_called_once_with('test-config')
            callee.assert_called_once_with()
            self.assertFalse(mock_application_version_set.called)

    @mock.patch('rabbit_utils.application_version_set')
    @mock.patch('rabbit_utils.get_upstream_version')
    def test_assess_status_installed(self, mock_get_upstream_version,
                                     mock_application_version_set):
        mock_get_upstream_version.return_value = '3.5.7'
        with mock.patch.object(rabbit_utils, 'assess_status_func') as asf:
            callee = mock.MagicMock()
            asf.return_value = callee
            rabbit_utils.assess_status('test-config')
            asf.assert_called_once_with('test-config')
            callee.assert_called_once_with()
            mock_application_version_set.assert_called_with('3.5.7')

    @mock.patch.object(rabbit_utils, 'is_cron_schedule_valid')
    @mock.patch.object(rabbit_utils.deferred_events, 'get_deferred_hooks')
    @mock.patch.object(rabbit_utils.deferred_events, 'get_deferred_restarts')
    @mock.patch.object(rabbit_utils, 'clustered')
    @mock.patch.object(rabbit_utils, 'status_set')
    @mock.patch.object(rabbit_utils, 'assess_cluster_status')
    @mock.patch.object(rabbit_utils, 'services')
    @mock.patch.object(rabbit_utils, '_determine_os_workload_status')
    def test_assess_status_func(self,
                                _determine_os_workload_status,
                                services,
                                assess_cluster_status,
                                status_set,
                                clustered,
                                get_deferred_restarts,
                                get_deferred_hooks,
                                is_cron_schedule_valid):
        is_cron_schedule_valid.return_value = True
        get_deferred_hooks.return_value = []
        get_deferred_restarts.return_value = []
        self.leader_get.return_value = None
        services.return_value = 's1'
        _determine_os_workload_status.return_value = ('active', '')
        clustered.return_value = True
        rabbit_utils.assess_status_func('test-config')()
        # ports=None whilst port checks are disabled.
        _determine_os_workload_status.assert_called_once_with(
            'test-config', {}, charm_func=assess_cluster_status, services='s1',
            ports=None)
        status_set.assert_called_once_with('active',
                                           'Unit is ready and clustered')

    @mock.patch.object(rabbit_utils, 'is_cron_schedule_valid')
    @mock.patch.object(rabbit_utils.deferred_events, 'get_deferred_hooks')
    @mock.patch.object(rabbit_utils.deferred_events, 'get_deferred_restarts')
    @mock.patch.object(rabbit_utils, 'clustered')
    @mock.patch.object(rabbit_utils, 'status_set')
    @mock.patch.object(rabbit_utils, 'assess_cluster_status')
    @mock.patch.object(rabbit_utils, 'services')
    @mock.patch.object(rabbit_utils, '_determine_os_workload_status')
    def test_assess_status_func_invalid_cron(self,
                                             _determine_os_workload_status,
                                             services,
                                             assess_cluster_status,
                                             status_set,
                                             clustered,
                                             get_deferred_restarts,
                                             get_deferred_hooks,
                                             is_cron_schedule_valid):
        is_cron_schedule_valid.return_value = False
        get_deferred_hooks.return_value = []
        get_deferred_restarts.return_value = []
        self.leader_get.return_value = None
        services.return_value = 's1'
        _determine_os_workload_status.return_value = ('active', '')
        clustered.return_value = True
        rabbit_utils.assess_status_func('test-config')()
        # ports=None whilst port checks are disabled.
        _determine_os_workload_status.assert_called_once_with(
            'test-config', {}, charm_func=assess_cluster_status, services='s1',
            ports=None)
        msg = 'Unit is ready and clustered. stats_cron_schedule is invalid'
        status_set.assert_called_once_with('active', msg)

    @mock.patch.object(rabbit_utils, 'is_cron_schedule_valid')
    @mock.patch.object(rabbit_utils.deferred_events, 'get_deferred_hooks')
    @mock.patch.object(rabbit_utils.deferred_events, 'get_deferred_restarts')
    @mock.patch.object(rabbit_utils, 'clustered')
    @mock.patch.object(rabbit_utils, 'status_set')
    @mock.patch.object(rabbit_utils, 'assess_cluster_status')
    @mock.patch.object(rabbit_utils, 'services')
    @mock.patch.object(rabbit_utils, '_determine_os_workload_status')
    def test_assess_status_func_cluster_upgrading(
            self, _determine_os_workload_status, services,
            assess_cluster_status, status_set, clustered,
            get_deferred_restarts, get_deferred_hooks, is_cron_schedule_valid):
        is_cron_schedule_valid.return_value = True
        get_deferred_hooks.return_value = []
        get_deferred_restarts.return_value = []
        self.leader_get.return_value = True
        services.return_value = 's1'
        _determine_os_workload_status.return_value = ('active', '')
        clustered.return_value = True
        rabbit_utils.assess_status_func('test-config')()
        # ports=None whilst port checks are disabled.
        _determine_os_workload_status.assert_called_once_with(
            'test-config', {}, charm_func=assess_cluster_status, services='s1',
            ports=None)
        status_set.assert_called_once_with(
            'active', 'Unit is ready and clustered, run '
            'complete-cluster-series-upgrade when the cluster has completed '
            'its upgrade')

    @mock.patch.object(rabbit_utils, 'is_cron_schedule_valid')
    @mock.patch.object(rabbit_utils.deferred_events, 'get_deferred_hooks')
    @mock.patch.object(rabbit_utils.deferred_events, 'get_deferred_restarts')
    @mock.patch.object(rabbit_utils, 'clustered')
    @mock.patch.object(rabbit_utils, 'status_set')
    @mock.patch.object(rabbit_utils, 'assess_cluster_status')
    @mock.patch.object(rabbit_utils, 'services')
    @mock.patch.object(rabbit_utils, '_determine_os_workload_status')
    def test_assess_status_func_cluster_upgrading_first_unit(
            self, _determine_os_workload_status, services,
            assess_cluster_status, status_set, clustered,
            get_deferred_restarts, get_deferred_hooks, is_cron_schedule_valid):
        is_cron_schedule_valid.return_value = True
        get_deferred_hooks.return_value = []
        get_deferred_restarts.return_value = []
        self.leader_get.return_value = True
        services.return_value = 's1'
        _determine_os_workload_status.return_value = ('waiting', 'No peers')
        clustered.return_value = False
        rabbit_utils.assess_status_func('test-config')()
        # ports=None whilst port checks are disabled.
        _determine_os_workload_status.assert_called_once_with(
            'test-config', {}, charm_func=assess_cluster_status, services='s1',
            ports=None)
        status_set.assert_called_once_with(
            'active', 'No peers, run '
            'complete-cluster-series-upgrade when the cluster has completed '
            'its upgrade')

    def test_pause_unit_helper(self):
        with mock.patch.object(rabbit_utils, '_pause_resume_helper') as prh:
            rabbit_utils.pause_unit_helper('random-config')
            prh.assert_called_once_with(
                rabbit_utils.pause_unit,
                'random-config')
        with mock.patch.object(rabbit_utils, '_pause_resume_helper') as prh:
            rabbit_utils.resume_unit_helper('random-config')
            prh.assert_called_once_with(
                rabbit_utils.resume_unit,
                'random-config')

    @mock.patch.object(rabbit_utils, 'services')
    def test_pause_resume_helper(self, services):
        f = mock.MagicMock()
        services.return_value = 's1'
        with mock.patch.object(rabbit_utils, 'assess_status_func') as asf:
            asf.return_value = 'assessor'
            rabbit_utils._pause_resume_helper(f, 'some-config')
            asf.assert_called_once_with('some-config')
            # ports=None whilst port checks are disabled.
            f.assert_called_once_with('assessor', services='s1', ports=None)

    @mock.patch('rabbit_utils.subprocess.check_call')
    @mock.patch('rabbit_utils.rabbitmq_version_newer_or_equal')
    def test_rabbitmqctl_wait_before_focal(self, mock_new_rabbitmq,
                                           check_call):
        mock_new_rabbitmq.return_value = False
        rabbit_utils.rabbitmqctl('wait', '/var/lib/rabbitmq.pid')
        check_call.assert_called_with([
            'timeout', '180', '/usr/sbin/rabbitmqctl', 'wait',
            '/var/lib/rabbitmq.pid'])

    @mock.patch('rabbit_utils.subprocess.check_call')
    @mock.patch('rabbit_utils.rabbitmq_version_newer_or_equal')
    def test_rabbitmqctl_wait_focal_or_newer(self, mock_new_rabbitmq,
                                             check_call):
        mock_new_rabbitmq.return_value = True
        rabbit_utils.rabbitmqctl('wait', '/var/lib/rabbitmq.pid')
        check_call.assert_called_with([
            '/usr/sbin/rabbitmqctl', 'wait', '/var/lib/rabbitmq.pid',
            '--timeout', '180'])

    @mock.patch('rabbit_utils.subprocess.check_call')
    def test_rabbitmqctl_start_app(self, check_call):
        rabbit_utils.rabbitmqctl('start_app')
        check_call.assert_called_with(['/usr/sbin/rabbitmqctl', 'start_app'])

    @mock.patch('rabbit_utils.subprocess.check_call')
    @mock.patch('rabbit_utils.rabbitmq_version_newer_or_equal')
    def test_rabbitmqctl_wait_fail(self, mock_new_rabbitmq,
                                   check_call):
        mock_new_rabbitmq.return_value = True
        check_call.side_effect = (rabbit_utils.subprocess.
                                  CalledProcessError(1, 'cmd'))
        with self.assertRaises(rabbit_utils.subprocess.CalledProcessError):
            rabbit_utils.wait_app()

    @mock.patch('rabbit_utils.subprocess.check_call')
    def test_rabbitmqctl_wait_success(self, check_call):
        check_call.return_value = 0
        self.assertTrue(rabbit_utils.wait_app())

    @mock.patch.object(rabbit_utils, 'is_leader')
    @mock.patch.object(rabbit_utils, 'related_units')
    @mock.patch.object(rabbit_utils, 'relation_ids')
    @mock.patch.object(rabbit_utils, 'config')
    def test_is_sufficient_peers(self, mock_config, mock_relation_ids,
                                 mock_related_units, mock_is_leader):
        self.relation_get.return_value = None
        # With leadership Election
        mock_is_leader.return_value = False
        _config = {'min-cluster-size': None}
        mock_config.side_effect = lambda key: _config.get(key)
        self.assertTrue(rabbit_utils.is_sufficient_peers())

        mock_is_leader.return_value = False
        mock_relation_ids.return_value = ['cluster:0']
        mock_related_units.return_value = ['test/0']
        _config = {'min-cluster-size': 3}
        mock_config.side_effect = lambda key: _config.get(key)
        self.assertFalse(rabbit_utils.is_sufficient_peers())

        self.relation_get.side_effect = ['testhost0', 'testhost1']
        mock_is_leader.return_value = False
        mock_related_units.return_value = ['test/0', 'test/1']
        _config = {'min-cluster-size': 3}
        mock_config.side_effect = lambda key: _config.get(key)
        self.assertTrue(rabbit_utils.is_sufficient_peers())

    @mock.patch.object(rabbit_utils.os.path, 'exists')
    def test_rabbitmq_is_installed(self, mock_os_exists):
        mock_os_exists.return_value = True
        self.assertTrue(rabbit_utils.rabbitmq_is_installed())

        mock_os_exists.return_value = False
        self.assertFalse(rabbit_utils.rabbitmq_is_installed())

    @mock.patch.object(rabbit_utils, 'clustered')
    @mock.patch.object(rabbit_utils, 'rabbitmq_is_installed')
    @mock.patch.object(rabbit_utils, 'is_sufficient_peers')
    def test_cluster_ready(self, mock_is_sufficient_peers,
                           mock_rabbitmq_is_installed, mock_clustered):

        # Not sufficient number of peers
        mock_is_sufficient_peers.return_value = False
        self.assertFalse(rabbit_utils.cluster_ready())

        # This unit not yet clustered
        mock_is_sufficient_peers.return_value = True
        self.relation_ids.return_value = ['cluster:0']
        self.related_units.return_value = ['test/0', 'test/1']
        self.relation_get.return_value = 'teset/0'
        _config = {'min-cluster-size': 3}
        self.config.side_effect = lambda key: _config.get(key)
        mock_clustered.return_value = False
        self.assertFalse(rabbit_utils.cluster_ready())

        # Not all cluster ready
        mock_is_sufficient_peers.return_value = True
        self.relation_ids.return_value = ['cluster:0']
        self.related_units.return_value = ['test/0', 'test/1']
        self.relation_get.return_value = False
        _config = {'min-cluster-size': 3}
        self.config.side_effect = lambda key: _config.get(key)
        mock_clustered.return_value = True
        self.assertFalse(rabbit_utils.cluster_ready())

        # All cluster ready
        mock_is_sufficient_peers.return_value = True
        self.relation_ids.return_value = ['cluster:0']
        self.related_units.return_value = ['test/0', 'test/1']
        self.relation_get.return_value = 'teset/0'
        _config = {'min-cluster-size': 3}
        self.config.side_effect = lambda key: _config.get(key)
        mock_clustered.return_value = True
        self.assertTrue(rabbit_utils.cluster_ready())

        # Not all cluster ready no min-cluster-size
        mock_is_sufficient_peers.return_value = True
        self.relation_ids.return_value = ['cluster:0']
        self.related_units.return_value = ['test/0', 'test/1']
        self.relation_get.return_value = False
        _config = {'min-cluster-size': None}
        self.config.side_effect = lambda key: _config.get(key)
        mock_clustered.return_value = True
        self.assertFalse(rabbit_utils.cluster_ready())

        # All cluster ready no min-cluster-size
        mock_is_sufficient_peers.return_value = True
        self.relation_ids.return_value = ['cluster:0']
        self.related_units.return_value = ['test/0', 'test/1']
        self.relation_get.return_value = 'teset/0'
        _config = {'min-cluster-size': None}
        self.config.side_effect = lambda key: _config.get(key)
        mock_clustered.return_value = True
        self.assertTrue(rabbit_utils.cluster_ready())

        # Assume single unit no-min-cluster-size
        mock_is_sufficient_peers.return_value = True
        self.relation_ids.return_value = []
        self.related_units.return_value = []
        self.relation_get.return_value = None
        _config = {'min-cluster-size': None}
        self.config.side_effect = lambda key: _config.get(key)
        mock_clustered.return_value = True
        self.assertTrue(rabbit_utils.cluster_ready())

    def test_client_node_is_ready(self):
        # Paused
        self.is_unit_paused_set.return_value = True
        self.assertFalse(rabbit_utils.client_node_is_ready())

        # Not ready
        self.is_unit_paused_set.return_value = False
        self.relation_ids.return_value = ['amqp:0']
        self.leader_get.return_value = {}
        self.assertFalse(rabbit_utils.client_node_is_ready())

        # Ready
        self.is_unit_paused_set.return_value = False
        self.relation_ids.return_value = ['amqp:0']
        self.leader_get.return_value = {'amqp:0_password': 'password'}
        self.assertTrue(rabbit_utils.client_node_is_ready())

    @mock.patch.object(rabbit_utils, 'cluster_ready')
    @mock.patch.object(rabbit_utils, 'rabbitmq_is_installed')
    def test_leader_node_is_ready(self, mock_rabbitmq_is_installed,
                                  mock_cluster_ready):
        # Paused
        self.is_unit_paused_set.return_value = True
        self.assertFalse(rabbit_utils.leader_node_is_ready())

        # Not installed
        self.is_unit_paused_set.return_value = False
        mock_rabbitmq_is_installed.return_value = False
        self.is_leader.return_value = True
        mock_cluster_ready.return_value = True
        self.assertFalse(rabbit_utils.leader_node_is_ready())

        # Not leader
        self.is_unit_paused_set.return_value = False
        mock_rabbitmq_is_installed.return_value = True
        self.is_leader.return_value = False
        mock_cluster_ready.return_value = True
        self.assertFalse(rabbit_utils.leader_node_is_ready())

        # Not clustered
        self.is_unit_paused_set.return_value = False
        mock_rabbitmq_is_installed.return_value = True
        self.is_leader.return_value = True
        mock_cluster_ready.return_value = False
        self.assertFalse(rabbit_utils.leader_node_is_ready())

        # Leader ready
        self.is_unit_paused_set.return_value = False
        mock_rabbitmq_is_installed.return_value = True
        self.is_leader.return_value = True
        mock_cluster_ready.return_value = True
        self.assertTrue(rabbit_utils.leader_node_is_ready())

    @mock.patch('rabbit_utils.rabbitmq_version_newer_or_equal')
    def test_get_managment_port_legacy(self, mock_new_rabbitmq):
        mock_new_rabbitmq.return_value = False
        self.assertEqual(rabbit_utils.get_managment_port(), 55672)

    @mock.patch('rabbit_utils.rabbitmq_version_newer_or_equal')
    def test_get_managment_port(self, mock_new_rabbitmq):
        mock_new_rabbitmq.return_value = True
        self.assertEqual(rabbit_utils.get_managment_port(), 15672)

    @mock.patch('glob.glob')
    @mock.patch('rabbit_utils.subprocess.check_call')
    @mock.patch('os.path.exists')
    def test_enable_management_plugin(self, mock_os_path,
                                      mock_subprocess,
                                      mock_glob):
        mock_os_path.return_value = True
        rabbitmq_plugins = '/sbin/rabbitmq-plugins'
        rabbit_utils._manage_plugin("rabbitmq_prometheus", "enable")
        mock_subprocess.assert_called_with([rabbitmq_plugins,
                                            "enable", "rabbitmq_prometheus"])
        mock_os_path.return_value = False
        rabbitmq_plugins = '/usr/lib/rabbitmq/lib/'\
                           'rabbitmq_server-3.8.2/sbin/rabbitmq-plugins'
        mock_glob.return_value = [rabbitmq_plugins]
        rabbit_utils._manage_plugin("rabbitmq_prometheus", "enable")
        mock_subprocess.assert_called_with([rabbitmq_plugins,
                                            "enable", "rabbitmq_prometheus"])

    @mock.patch('rabbit_utils.caching_cmp_pkgrevno')
    @mock.patch('rabbit_utils.relations_for_id')
    @mock.patch('rabbit_utils.subprocess')
    @mock.patch('rabbit_utils.relation_ids')
    def test_check_cluster_memberships(self, mock_relation_ids,
                                       mock_subprocess,
                                       mock_relations_for_id,
                                       mock_cmp_pkgrevno):
        mock_relation_ids.return_value = [0]
        mock_subprocess.check_output.return_value = \
            RABBITMQCTL_CLUSTERSTATUS_RUNNING
        mock_cmp_pkgrevno.return_value = -1
        mock_relations_for_id.return_value = [
            {'clustered': 'juju-devel3-machine-14'},
            {'clustered': 'juju-devel3-machine-19'},
            {'dummy-entry': 'to validate behaviour on relations without '
                            'clustered key in dict'},
        ]
        self.assertEqual(
            "rabbit@juju-devel3-machine-42",
            rabbit_utils.check_cluster_memberships())

    @mock.patch.object(rabbit_utils, 'cmp_pkgrevno')
    @mock.patch('rabbitmq_context.psutil.NUM_CPUS', 2)
    @mock.patch('rabbitmq_context.relation_ids')
    @mock.patch('rabbitmq_context.config')
    def test_render_rabbitmq_env(self, mock_config, mock_relation_ids,
                                 mock_cmp_pkgrevno):
        mock_cmp_pkgrevno.return_value = 0
        mock_relation_ids.return_value = []
        mock_config.return_value = 3
        with mock.patch('rabbit_utils.render') as mock_render:
            ctxt = {rabbit_utils.ENV_CONF:
                    rabbit_utils.CONFIG_FILES()[rabbit_utils.ENV_CONF]}
            rabbit_utils.ConfigRenderer(ctxt).write(
                rabbit_utils.ENV_CONF)

            ctxt = {'settings': {'RABBITMQ_SERVER_ADDITIONAL_ERL_ARGS':
                                 "'+A 6'",
                                 'RABBITMQ_SERVER_START_ARGS':
                                 "'-proto_dist inet6_tcp'"}}
            mock_render.assert_called_with('rabbitmq-env.conf',
                                           '/etc/rabbitmq/rabbitmq-env.conf',
                                           ctxt,
                                           perms=420)

    def test_archive_upgrade_available(self):
        self.config.side_effect = self.test_config.get
        self.test_config.set("source", "new-config")
        self.test_config.set_previous("source", "old-config")
        self.assertTrue(rabbit_utils.archive_upgrade_available())

        self.test_config.set("source", "same")
        self.test_config.set_previous("source", "same")
        self.assertFalse(rabbit_utils.archive_upgrade_available())

    @mock.patch.object(rabbit_utils, 'distributed_wait')
    def test_cluster_wait(self, mock_distributed_wait):
        self.relation_ids.return_value = ['amqp:27']
        self.related_units.return_value = ['unit/1', 'unit/2', 'unit/3']
        # Default check peer relation
        _config = {'known-wait': 30}
        self.config.side_effect = lambda key: _config.get(key)
        rabbit_utils.cluster_wait()
        mock_distributed_wait.assert_called_with(modulo=4, wait=30)

        # Use Min Cluster Size
        _config = {'min-cluster-size': 5, 'known-wait': 30}
        self.config.side_effect = lambda key: _config.get(key)
        rabbit_utils.cluster_wait()
        mock_distributed_wait.assert_called_with(modulo=5, wait=30)

        # Override with modulo-nodes
        _config = {'min-cluster-size': 5, 'modulo-nodes': 10, 'known-wait': 60}
        self.config.side_effect = lambda key: _config.get(key)
        rabbit_utils.cluster_wait()
        mock_distributed_wait.assert_called_with(modulo=10, wait=60)

        # Just modulo-nodes
        _config = {'modulo-nodes': 10, 'known-wait': 60}
        self.config.side_effect = lambda key: _config.get(key)
        rabbit_utils.cluster_wait()
        mock_distributed_wait.assert_called_with(modulo=10, wait=60)

    @mock.patch.object(rabbit_utils, 'rabbitmqctl')
    def test_configure_notification_ttl(self, rabbitmqctl):
        rabbit_utils.configure_notification_ttl('test',
                                                23000)
        rabbitmqctl.assert_called_once_with(
            'set_policy',
            'TTL', '^(versioned_)?notifications.*',
            '{"message-ttl":23000}',
            '--priority', '1',
            '--apply-to', 'queues',
            '-p', 'test'
        )

    @mock.patch.object(rabbit_utils, 'rabbitmqctl')
    def test_configure_ttl(self, rabbitmqctl):
        rabbit_utils.configure_ttl('test', ttlname='heat_expiry',
                                   ttlreg='heat-engine-listener|engine_worker',
                                   ttl=23000)
        rabbitmqctl.assert_called_once_with(
            'set_policy',
            'heat_expiry', '"heat-engine-listener|engine_worker"',
            '{"expires":23000}',
            '--priority', '1',
            '--apply-to', 'queues',
            '-p', 'test'
        )

    @mock.patch.object(rabbit_utils, 'leader_get')
    @mock.patch.object(rabbit_utils, 'is_partitioned')
    @mock.patch.object(rabbit_utils, 'wait_app')
    @mock.patch.object(rabbit_utils, 'check_cluster_memberships')
    @mock.patch.object(rabbit_utils, 'clustered')
    @mock.patch.object(rabbit_utils, 'is_sufficient_peers')
    @mock.patch.object(rabbit_utils, 'is_unit_paused_set')
    @mock.patch.object(rabbit_utils, 'rabbitmq_is_installed')
    def test_assess_cluster_status(
            self, rabbitmq_is_installed, is_unit_paused_set,
            is_sufficient_peers, clustered, check_cluster_memberships,
            wait_app, is_partitioned, leader_get):
        is_partitioned.return_value = False
        self.relation_ids.return_value = ["cluster:1"]
        self.related_units.return_value = ["rabbitmq-server/1"]
        _min = 3
        _config = {
            'min-cluster-size': _min,
            'cluster-partition-handling': 'autoheal'}
        self.config.side_effect = lambda key: _config.get(key)

        # Paused
        is_unit_paused_set.return_value = True
        _expected = ("maintenance", "Paused")
        self.assertEqual(_expected, rabbit_utils.assess_cluster_status())

        # Not installed
        is_unit_paused_set.return_value = False
        rabbitmq_is_installed.return_value = False
        _expected = ("waiting", "RabbitMQ is not yet installed")
        self.assertEqual(_expected, rabbit_utils.assess_cluster_status())

        # Not sufficient peers
        rabbitmq_is_installed.return_value = True
        is_sufficient_peers.return_value = False
        _expected = (
            "waiting",
            "Waiting for all {} peers to complete the cluster.".format(_min))
        self.assertEqual(_expected, rabbit_utils.assess_cluster_status())

        # Nodes not clustered
        is_sufficient_peers.return_value = True
        clustered.return_value = False
        _expected = (
            "waiting",
            "Unit has peers, but RabbitMQ not clustered")
        self.assertEqual(_expected, rabbit_utils.assess_cluster_status())

        # Departed node
        clustered.return_value = True
        _departed_node = "rabbit@hostname"
        check_cluster_memberships.return_value = _departed_node
        _expected = (
            "blocked",
            "Node {} in the cluster but not running. If it is a departed "
            "node, remove with `forget-cluster-node` action"
            .format(_departed_node))
        self.assertEqual(_expected, rabbit_utils.assess_cluster_status())

        # Wait app does not return True
        check_cluster_memberships.return_value = None
        wait_app.return_value = None
        _expected = (
            "blocked",
            "Unable to determine if the rabbitmq service is up")
        self.assertEqual(_expected, rabbit_utils.assess_cluster_status())

        wait_app.return_value = True
        is_partitioned.return_value = True
        _expected = (
            "blocked",
            "RabbitMQ is partitioned")
        self.assertEqual(_expected, rabbit_utils.assess_cluster_status())

        # CLUSTER_MODE_KEY not at target
        is_partitioned.return_value = False
        leader_get.return_value = 'ignore'
        _expected = (
            "waiting",
            "Not reached target cluster-partition-handling mode")
        self.assertEqual(_expected, rabbit_utils.assess_cluster_status())

        # All OK
        leader_get.return_value = 'autoheal'
        wait_app.return_value = True
        is_partitioned.return_value = False
        _expected = (
            "active",
            "message is ignored")
        self.assertEqual(_expected, rabbit_utils.assess_cluster_status())

    @mock.patch("rabbit_utils.log")
    def test_remove_file(self, mock_log):
        """test delete existing and non-existent file"""
        with tempfile.NamedTemporaryFile(delete=False) as tmpfile:
            rabbit_utils.remove_file(tmpfile.name)
            mock_log.asset_not_called()

            mock_log.reset_mock()
            rabbit_utils.remove_file(tmpfile.name)
            mock_log.assert_has_calls([
                mock.call('{} file does not exist'.format(tmpfile.name),
                          level='DEBUG')
            ])

    @mock.patch('os.path.isdir')
    @mock.patch('rabbit_utils.charm_dir')
    @mock.patch('rabbit_utils.config')
    @mock.patch('rabbit_utils.rsync')
    @mock.patch("rabbit_utils.write_file")
    def test_sync_nrpe_files(self,
                             mock_write_file,
                             mock_rsync,
                             mock_config,
                             mock_charm_dir,
                             mock_isdir):
        """Testing copy the NRPE files"""
        self.test_config.set('stats_cron_schedule', '*/1 * * * *')
        self.test_config.set('cron-timeout', '300')
        self.test_config.unset('management_plugin')
        rabbit_utils.NAGIOS_PLUGINS = self.tmp_dir
        rabbit_utils.SCRIPTS_DIR = self.tmp_dir
        rabbit_utils.STATS_CRONFILE = os.path.join(self.tmp_dir, 'cronfile')
        rabbit_utils.CRONJOB_CMD = '{schedule} {timeout} {command}'

        mock_config.side_effect = self.test_config
        mock_isdir.return_value = True
        mock_charm_dir.side_effect = lambda: self.tmp_dir
        rabbit_utils.sync_nrpe_files()
        mock_rsync.assert_has_calls([
            mock.call(os.path.join(self.tmp_dir, 'files', 'check_rabbitmq.py'),
                      os.path.join(self.tmp_dir, 'check_rabbitmq.py')),
            mock.call(os.path.join(self.tmp_dir, 'files',
                                   'check_rabbitmq_queues.py'),
                      os.path.join(self.tmp_dir, 'check_rabbitmq_queues.py')),
            mock.call(os.path.join(self.tmp_dir, 'files',
                                   'collect_rabbitmq_stats.sh'),
                      os.path.join(self.tmp_dir, 'collect_rabbitmq_stats.sh'))
        ])
        mock_write_file.assert_has_calls([
            mock.call(os.path.join(self.tmp_dir, 'cronfile'),
                      '*/1 * * * * 300 {}/collect_rabbitmq_stats.sh'.format(
                          self.tmp_dir))
        ])

    @mock.patch('rabbit_utils.config')
    @mock.patch('rabbit_utils.remove_file')
    def test_remove_nrpe_files(self, mock_remove_file, mock_config):
        """Testing remove the NRPE scripts and the cron file"""
        self.test_config.unset('stats_cron_schedule')
        self.test_config.unset('management_plugin')
        rabbit_utils.NAGIOS_PLUGINS = self.tmp_dir
        rabbit_utils.SCRIPTS_DIR = self.tmp_dir
        rabbit_utils.STATS_CRONFILE = os.path.join(self.tmp_dir, 'cronfile')

        mock_config.side_effect = self.test_config
        rabbit_utils.remove_nrpe_files()
        mock_remove_file.assert_has_calls([
            mock.call(os.path.join(self.tmp_dir, 'cronfile')),
            mock.call(os.path.join(self.tmp_dir, 'collect_rabbitmq_stats.sh')),
            mock.call(os.path.join(self.tmp_dir, 'check_rabbitmq_queues.py')),
            mock.call(os.path.join(self.tmp_dir, 'check_rabbitmq_cluster.py')),
        ])

    @mock.patch('charmhelpers.contrib.charmsupport.nrpe.get_nagios_hostname')
    @mock.patch('charmhelpers.contrib.charmsupport.nrpe.get_nagios_unit_name')
    @mock.patch('rabbit_utils.create_user')
    @mock.patch('rabbit_utils.get_rabbit_password_on_disk')
    @mock.patch('rabbit_utils.local_unit')
    @mock.patch('rabbit_utils.config')
    def test_get_nrpe_credentials(self,
                                  mock_config,
                                  mock_local_unit,
                                  mock_get_rabbit_password_on_disk,
                                  mock_create_user,
                                  mock_get_nagios_unit_name,
                                  mock_get_nagios_hostname):
        """Testing get the NRPE credentials"""
        self.test_config.unset('check-vhosts')

        mock_get_nagios_hostname.return_value = "foo-0"
        mock_get_nagios_unit_name.return_value = "bar-0"
        mock_local_unit.return_value = 'unit/0'
        mock_config.side_effect = self.test_config
        mock_get_rabbit_password_on_disk.return_value = "qwerty"

        nrpe_credentials = rabbit_utils.get_nrpe_credentials()
        self.assertTupleEqual(nrpe_credentials,
                              ('foo-0',
                               'bar-0',
                               [{'vhost': 'nagios-unit-0',
                                 'shortname': 'rabbitmq'}],
                               'nagios-unit-0',
                               'qwerty'))

    @mock.patch('charmhelpers.contrib.charmsupport.nrpe.config')
    @mock.patch('rabbit_utils.config')
    def test_nrpe_update_vhost_check(self, mock_config, mock_config2):
        """Testing add and remove RabbitMQ non-SSL check"""
        mock_config.side_effect = self.test_config
        mock_config2.side_effect = self.test_config
        rabbit_utils.NAGIOS_PLUGINS = self.tmp_dir

        # call with ssl set to 'on'
        self.test_config.set('ssl', 'on')
        rabbit_utils.nrpe_update_vhost_check(
            nrpe_compat=self.nrpe_compat,
            unit='bar-0',
            user='nagios-unit-0',
            password='qwerty',
            vhost={'vhost': 'nagios-unit-0', 'shortname': 'rabbitmq'})
        self.nrpe_compat.add_check.assert_called_with(
            shortname='rabbitmq',
            description='Check RabbitMQ bar-0 nagios-unit-0',
            check_cmd='{}/check_rabbitmq.py --user nagios-unit-0 '
                      '--password qwerty '
                      '--vhost nagios-unit-0'.format(self.tmp_dir))
        self.nrpe_compat.remove_check.assert_not_called()

        self.nrpe_compat.reset_mock()

        # call with ssl set to 'only'
        self.test_config.set('ssl', 'only')
        rabbit_utils.nrpe_update_vhost_check(
            nrpe_compat=self.nrpe_compat,
            unit='bar-0',
            user='nagios-unit-0',
            password='qwerty',
            vhost={'vhost': 'nagios-unit-0', 'shortname': 'rabbitmq'})
        self.nrpe_compat.add_check.assert_not_called()
        self.nrpe_compat.remove_check.assert_called_with(
            shortname='rabbitmq',
            description='Remove check RabbitMQ bar-0 nagios-unit-0',
            check_cmd='{}/check_rabbitmq.py'.format(self.tmp_dir))

    @mock.patch('charmhelpers.contrib.charmsupport.nrpe.config')
    @mock.patch('rabbit_utils.config')
    def test_nrpe_update_vhost_ssl_check(self, mock_config, mock_config2):
        """Testing add and remove RabbitMQ SSL check"""
        mock_config.side_effect = self.test_config
        mock_config2.side_effect = self.test_config
        rabbit_utils.NAGIOS_PLUGINS = self.tmp_dir

        # call with ssl set to 'on'
        self.test_config.set('ssl', 'on')
        rabbit_utils.nrpe_update_vhost_ssl_check(
            nrpe_compat=self.nrpe_compat,
            unit='bar-0',
            user='nagios-unit-0',
            password='qwerty',
            vhost={'vhost': 'nagios-unit-0', 'shortname': 'rabbitmq'})
        self.nrpe_compat.add_check.assert_called_with(
            shortname='rabbitmq_ssl',
            description='Check RabbitMQ (SSL) bar-0 nagios-unit-0',
            check_cmd='{}/check_rabbitmq.py --user nagios-unit-0 '
                      '--password qwerty --vhost nagios-unit-0 --ssl '
                      '--ssl-ca /etc/rabbitmq/rabbit-server-ca.pem '
                      '--port 5671'.format(self.tmp_dir))
        self.nrpe_compat.remove_check.assert_not_called()

        self.nrpe_compat.reset_mock()

        # call with ssl set to 'off'
        self.test_config.set('ssl', 'off')
        rabbit_utils.nrpe_update_vhost_ssl_check(
            nrpe_compat=self.nrpe_compat,
            unit='bar-0',
            user='nagios-unit-0',
            password='qwerty',
            vhost={'vhost': 'nagios-unit-0', 'shortname': 'rabbitmq'})
        self.nrpe_compat.add_check.assert_not_called()
        self.nrpe_compat.remove_check.assert_called_with(
            shortname='rabbitmq_ssl',
            description='Remove check RabbitMQ (SSL) bar-0 nagios-unit-0',
            check_cmd='{}/check_rabbitmq.py'.format(self.tmp_dir))

    @mock.patch('charmhelpers.contrib.charmsupport.nrpe.config')
    @mock.patch('rabbit_utils.config')
    @mock.patch('rabbit_utils.get_unit_hostname')
    def test_nrpe_update_queues_check(self,
                                      mock_get_unit_hostname,
                                      mock_config,
                                      mock_config2):
        """Testing add and remove RabbitMQ queues check"""
        mock_config.side_effect = self.test_config
        mock_config2.side_effect = self.test_config
        mock_get_unit_hostname.return_value = 'test'
        rabbit_utils.NAGIOS_PLUGINS = self.tmp_dir

        # call with stats_cron_schedule set to '*/5 * * * *'
        self.test_config.set('stats_cron_schedule', '*/5 * * * *')
        # set some queues to exclude to test proper command generation
        # with '-e' parameter
        self.test_config.set('exclude_queues',
                             "[['\\*', 'event.sample'], "
                             "['\\*', 'notifications_designate.info']]")
        rabbit_utils.nrpe_update_queues_check(self.nrpe_compat, self.tmp_dir)
        default_excludes = [
            ('\\*', 'event.sample'),
            ('\\*', 'notifications_designate.info'),
        ]
        exclude_queues = ''
        for vhost, queue in default_excludes:
            exclude_queues += '-e "{}" "{}" '.format(vhost, queue)
        self.nrpe_compat.add_check.assert_called_with(
            shortname='rabbitmq_queue',
            description='Check RabbitMQ Queues',
            check_cmd='{0}/check_rabbitmq_queues.py -c "\\*" "\\*" 100 200 {1}'
                      '-m 600 '
                      '{0}/data/test_queue_stats.dat'.format(self.tmp_dir,
                                                             exclude_queues))
        self.nrpe_compat.remove_check.assert_not_called()

        self.nrpe_compat.reset_mock()

        # call with set busiest_queues > 0
        queues_number = 3
        self.test_config.set('busiest_queues', str(queues_number))
        self.test_config.set('exclude_queues', "[]")
        rabbit_utils.nrpe_update_queues_check(self.nrpe_compat, self.tmp_dir)
        busiest_queues = '-d "{}" '.format(queues_number)
        self.nrpe_compat.add_check.assert_called_with(
            shortname='rabbitmq_queue',
            description='Check RabbitMQ Queues',
            check_cmd='{0}/check_rabbitmq_queues.py -c "\\*" "\\*" 100 200 {1}'
                      '-m 600 '
                      '{0}/data/test_queue_stats.dat'.format(self.tmp_dir,
                                                             busiest_queues))
        self.nrpe_compat.remove_check.assert_not_called()

        self.nrpe_compat.reset_mock()

        # call with unset stats_cron_schedule
        self.test_config.unset('stats_cron_schedule')
        rabbit_utils.nrpe_update_queues_check(self.nrpe_compat, self.tmp_dir)
        self.nrpe_compat.add_check.assert_not_called()
        self.nrpe_compat.remove_check.assert_called_with(
            shortname='rabbitmq_queue',
            description='Remove check RabbitMQ Queues',
            check_cmd='{}/check_rabbitmq_queues.py'.format(self.tmp_dir))

    @mock.patch('charmhelpers.contrib.charmsupport.nrpe.config')
    @mock.patch('rabbit_utils.config')
    @mock.patch('rabbit_utils.get_managment_port')
    def test_nrpe_update_cluster_check(self,
                                       mock_get_managment_port,
                                       mock_config,
                                       mock_config2):
        """Testing add and remove RabbitMQ cluster check"""
        mock_config.side_effect = self.test_config
        mock_config2.side_effect = self.test_config
        mock_get_managment_port.return_value = '1234'
        rabbit_utils.NAGIOS_PLUGINS = self.tmp_dir

        # call with management_plugin set to True
        self.test_config.set('management_plugin', True)
        rabbit_utils.nrpe_update_cluster_check(
            nrpe_compat=self.nrpe_compat,
            user='nagios-unit-0',
            password='qwerty')
        self.nrpe_compat.add_check.assert_called_with(
            shortname='rabbitmq_cluster',
            description='Check RabbitMQ Cluster',
            check_cmd='{}/check_rabbitmq_cluster.py --port 1234 '
                      '--user nagios-unit-0 --password qwerty'.format(
                          self.tmp_dir))
        self.nrpe_compat.remove_check.assert_not_called()

        self.nrpe_compat.reset_mock()

        # call with management_plugin set to False
        self.test_config.set('management_plugin', False)
        rabbit_utils.nrpe_update_cluster_check(
            nrpe_compat=self.nrpe_compat,
            user='nagios-unit-0',
            password='qwerty')
        self.nrpe_compat.add_check.assert_not_called()
        self.nrpe_compat.remove_check.assert_called_with(
            shortname='rabbitmq_cluster',
            description='Remove check RabbitMQ Cluster',
            check_cmd='{}/check_rabbitmq_cluster.py'.format(self.tmp_dir))

    @mock.patch('rabbit_utils.config')
    def test_get_max_stats_file_age(self, mock_config):
        """Testing the max stats file age"""
        mock_config.side_effect = self.test_config

        # default config value should show 10 minutes
        max_age = rabbit_utils.get_max_stats_file_age()
        self.assertEqual(600, max_age)
        # changing to run every 15 minutes shows 30 minutes
        self.test_config.set('stats_cron_schedule', '*/15 * * * *')
        max_age = rabbit_utils.get_max_stats_file_age()
        expected = timedelta(minutes=30).total_seconds()
        self.assertEqual(expected, max_age)

        # oddball cron schedule, just to validate. This runs every Saturday
        # at 23:30, which means the max age would be 14 days since it calcs
        # to twice the cron schedule
        self.test_config.set('stats_cron_schedule', '30 23 * * SAT')
        max_age = rabbit_utils.get_max_stats_file_age()
        expected = timedelta(days=14).total_seconds()
        self.assertEqual(expected, max_age)

        # empty cron schedule will return 0 for the max_age
        self.test_config.set('stats_cron_schedule', '')
        max_age = rabbit_utils.get_max_stats_file_age()
        self.assertEqual(0, max_age)

        # poorly formatted cron schedule will return 0 for the max_age
        self.test_config.set('stats_cron_schedule', 'poorly formatted')
        max_age = rabbit_utils.get_max_stats_file_age()
        self.assertEqual(0, max_age)

    @mock.patch('rabbit_utils.caching_cmp_pkgrevno')
    def test_rabbit_supports_json(self, mock_cmp_pkgrevno):
        mock_cmp_pkgrevno.return_value = 1
        self.assertTrue(rabbit_utils.rabbit_supports_json())
        mock_cmp_pkgrevno.return_value = -1
        self.assertFalse(rabbit_utils.rabbit_supports_json())

    @mock.patch('rabbit_utils.caching_cmp_pkgrevno')
    @mock.patch('rabbit_utils.set_policy')
    @mock.patch('rabbit_utils.config')
    def test_set_ha_mode(self,
                         mock_config,
                         mock_set_policy,
                         mock_caching_cmp_pkgrevno):
        """Testing set_ha_mode"""
        mock_config.side_effect = self.test_config
        mock_caching_cmp_pkgrevno.return_value = 1

        expected_policy = {
            'all': {
                'ha-mode': 'all',
                'ha-sync-mode': 'automatic',
            },
            'exactly': {
                'ha-mode': 'exactly',
                'ha-sync-mode': 'automatic',
                'ha-params': 2,
            },
            'nodes': {
                'ha-mode': 'nodes',
                'ha-sync-mode': 'automatic',
                'ha-params': ["rabbit@nodeA", "rabbit@nodeB"]
            },
        }
        for mode, policy in expected_policy.items():
            rabbit_utils.set_ha_mode('test_vhost', mode,
                                     params=policy.get('ha-params'))
            mock_set_policy.assert_called_once_with(
                'test_vhost', 'HA', r'^(?!amq\.).*',
                json.dumps(policy, sort_keys=True)
            )
            mock_set_policy.reset_mock()

    @mock.patch('rabbit_utils.config')
    def test_management_plugin_enabled(self, mock_config):
        mock_config.side_effect = self.test_config
        self.lsb_release.return_value = {
            'DISTRIB_CODENAME': 'focal'}
        self.test_config.set('management_plugin', True)
        self.assertTrue(rabbit_utils.management_plugin_enabled())
        self.test_config.set('management_plugin', False)
        self.assertFalse(rabbit_utils.management_plugin_enabled())
        self.lsb_release.return_value = {
            'DISTRIB_CODENAME': 'xenial'}
        self.test_config.set('management_plugin', True)
        self.assertFalse(rabbit_utils.management_plugin_enabled())
