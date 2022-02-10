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

from unittest import mock
from functools import wraps

import json

from unit_tests.test_utils import CharmTestCase

with mock.patch('charmhelpers.core.hookenv.cached') as cached:
    with mock.patch('os.getenv'):
        def passthrough(func):
            @wraps(func)
            def wrapper(*args, **kwargs):
                return func(*args, **kwargs)
            wrapper._wrapped = func
            return wrapper
        cached.side_effect = passthrough
        import actions


class PauseTestCase(CharmTestCase):

    def setUp(self):
        super(PauseTestCase, self).setUp(
            actions, ["pause_unit_helper", "ConfigRenderer", "CONFIG_FILES"])
        self.ConfigRenderer.return_value = 'test-config'

    def test_pauses_services(self):
        actions.pause([])
        self.pause_unit_helper.assert_called_once_with('test-config')


class ResumeTestCase(CharmTestCase):

    def setUp(self):
        super(ResumeTestCase, self).setUp(
            actions, ["resume_unit_helper", "ConfigRenderer", "CONFIG_FILES"])
        self.ConfigRenderer.return_value = 'test-config'

    def test_pauses_services(self):
        actions.resume([])
        self.resume_unit_helper.assert_called_once_with('test-config')


class ClusterStatusTestCase(CharmTestCase):

    def setUp(self):
        super(ClusterStatusTestCase, self).setUp(
            actions, ["check_output", "action_set", "action_fail",
                      "rabbitmq_version_newer_or_equal"])

    def test_cluster_status_json(self):
        self.rabbitmq_version_newer_or_equal.return_value = True
        self.check_output.return_value = json.dumps({"Status":
                                                     "Cluster status OK"})
        actions.cluster_status([])
        self.check_output.assert_called_once_with(['rabbitmqctl',
                                                   'cluster_status',
                                                   '--formatter', 'json'],
                                                  universal_newlines=True)
        self.action_set.assert_called()

    def test_cluster_status_exception_json(self):
        self.rabbitmq_version_newer_or_equal.return_value = True
        self.check_output.side_effect = actions.CalledProcessError(1,
                                                                   "Failure")
        actions.cluster_status([])
        self.check_output.assert_called_once_with(['rabbitmqctl',
                                                   'cluster_status',
                                                   '--formatter', 'json'],
                                                  universal_newlines=True)
        self.action_set.assert_called()
        self.action_fail.assert_called()

    def test_cluster_status(self):
        self.rabbitmq_version_newer_or_equal.return_value = False
        self.check_output.return_value = b'Cluster status OK'
        actions.cluster_status([])
        self.check_output.assert_called_once_with(['rabbitmqctl',
                                                   'cluster_status'],
                                                  universal_newlines=True)
        self.action_set.assert_called()

    def test_cluster_status_exception(self):
        self.rabbitmq_version_newer_or_equal.return_value = False
        self.check_output.side_effect = actions.CalledProcessError(1,
                                                                   "Failure")
        actions.cluster_status([])
        self.check_output.assert_called_once_with(['rabbitmqctl',
                                                   'cluster_status'],
                                                  universal_newlines=True)
        self.action_set.assert_called()
        self.action_fail.assert_called()


class CheckQueuesTestCase(CharmTestCase):
    TEST_QUEUE_RESULTS = [
        b'Listing queues ...\ntest\t0\ntest\t0\n',
        b'name\tmessage\ntest\t0\ntest\t0\n',
    ]

    def dummy_action_get(self, key):
        action_values = {"queue-depth": -1, "vhost": "/"}
        return action_values[key]

    def setUp(self):
        super(CheckQueuesTestCase, self).setUp(
            actions, ["check_output", "action_set", "action_fail",
                      "ConfigRenderer", "action_get"])

    def test_check_queues(self):
        self.action_get.side_effect = self.dummy_action_get
        for queue_res in self.TEST_QUEUE_RESULTS:
            with self.subTest(queue_res=queue_res):
                self.check_output.return_value = queue_res
                actions.check_queues([])
                self.check_output.assert_called_once_with(
                    ['rabbitmqctl', 'list_queues', '-q', '-p', '/'],
                )
                self.check_output.reset_mock()
                self.action_set.assert_called_once_with(
                    {'outcome': 'Success', 'output': {'test': 0}}
                )
                self.action_set.reset_mock()

    def test_check_queues_execption(self):
        self.action_get.side_effect = self.dummy_action_get
        self.check_output.side_effect = actions.CalledProcessError(
            1, "Failure"
        )
        actions.check_queues([])
        self.check_output.assert_called_once_with(
            ['rabbitmqctl', 'list_queues', '-q', '-p', '/']
        )


class ListUnconsumedQueuesTestCase(CharmTestCase):

    def setUp(self):
        super(ListUnconsumedQueuesTestCase, self).setUp(
            actions, ["list_vhosts", "vhost_queue_info", "action_set",
                      "action_fail"])

    def test_list_unconsumed_queues(self):
        self.list_vhosts.return_value = ['/']
        self.vhost_queue_info.return_value = [
            {'name': 'unconsumed_queue', 'messages': 1, 'consumers': 0},
            {'name': 'consumed_queue', 'messages': 0, 'consumers': 1}]
        actions.list_unconsumed_queues([])

        self.list_vhosts.assert_called()
        self.vhost_queue_info.assert_called_once_with('/')
        calls = [
            mock.call({
                "unconsumed-queues.0":
                '{"vhost": "/", "name": "unconsumed_queue", "messages": 1}'}),
            mock.call({'unconsumed-queue-count': 1})
        ]
        self.action_set.assert_has_calls(calls)

    def test_list_multiple_vhosts_unconsumed_queues(self):
        self.list_vhosts.return_value = ['/', 'other_vhost']
        self.vhost_queue_info.return_value = [
            {'name': 'unconsumed_queue', 'messages': 1, 'consumers': 0},
            {'name': 'consumed_queue', 'messages': 0, 'consumers': 1}]
        actions.list_unconsumed_queues([])

        self.list_vhosts.assert_called()
        calls = [
            mock.call({
                "unconsumed-queues.0":
                '{"vhost": "/", "name": "unconsumed_queue", "messages": 1}'}),
            mock.call({
                "unconsumed-queues.1":
                '{"vhost": "other_vhost", "name": "unconsumed_queue", '
                '"messages": 1}'}),
            mock.call({'unconsumed-queue-count': 2})
        ]
        self.action_set.assert_has_calls(calls)

    def test_list_unconsumed_queues_no_unconsumed(self):
        self.list_vhosts.return_value = ['/']
        self.vhost_queue_info.return_value = [
            {'name': 'consumed_queue', 'messages': 1, 'consumers': 1},
            {'name': 'consumed_queue2', 'messages': 0, 'consumers': 1}]
        actions.list_unconsumed_queues([])

        self.list_vhosts.assert_called()
        self.vhost_queue_info.assert_called_once_with('/')
        self.action_set.assert_called_once_with({'unconsumed-queue-count': 0})

    def test_list_unconsumed_queues_exception(self):
        self.vhost_queue_info.side_effect = \
            actions.CalledProcessError(1, "Failure")
        self.list_vhosts.return_value = ['/']
        self.vhost_queue_info.return_value = [
            {'name': 'unconsumed_queue', 'messages': 1, 'consumers': 0},
            {'name': 'consumed_queue', 'messages': 0, 'consumers': 1}]
        actions.list_unconsumed_queues([])

        self.list_vhosts.assert_called()
        self.vhost_queue_info.assert_called_once_with('/')
        self.action_set.assert_called()
        self.action_fail.assert_called_once_with(
            "Failed to query RabbitMQ vhost / queues")


class ForceBootTestCase(CharmTestCase):
    """Tests for force-boot action.

    """

    def setUp(self):
        super(ForceBootTestCase, self).setUp(
            actions, ["service_stop", "service_start", "check_output",
                      "action_set", "action_fail"])

    def test_force_boot_fail_stop(self):
        self.service_stop.side_effect = \
            actions.CalledProcessError(1, "Failure")
        actions.force_boot([])
        self.service_stop.assert_called()
        self.service_stop.assert_called_once_with('rabbitmq-server')
        self.action_set.assert_called()
        self.action_fail.assert_called_once_with(
            'Failed to stop rabbitmqctl service')

    def test_force_boot_fail(self):
        self.check_output.side_effect = \
            actions.CalledProcessError(1, "Failure")
        actions.force_boot([])
        self.service_stop.assert_called()
        self.check_output.assert_called()
        self.action_set.assert_called()
        self.action_fail.assert_called_once_with(
            'Failed to run rabbitmqctl force_boot')

    def test_force_boot_fail_start(self):
        self.service_start.side_effect = \
            actions.CalledProcessError(1, "Failure")
        actions.force_boot([])
        self.service_start.assert_called()
        self.service_start.assert_called_once_with('rabbitmq-server')
        self.action_set.assert_called()
        self.action_fail.assert_called_once_with(
            'Failed to start rabbitmqctl service after force_boot')

    def test_force_boot(self):
        output = 'Forcing boot for Mnesia dir ' \
            '/var/lib/rabbitmq/mnesia/rabbit@juju-f52a8d-rabbitmq-12'
        self.check_output.return_value = output
        actions.force_boot([])
        self.check_output.assert_called()
        self.action_set.assert_called_once_with({'output': output})


class MainTestCase(CharmTestCase):

    def setUp(self):
        super(MainTestCase, self).setUp(actions, ["action_fail"])

    def test_invokes_action(self):
        dummy_calls = []

        def dummy_action(args):
            dummy_calls.append(True)

        with mock.patch.dict(actions.ACTIONS, {"foo": dummy_action}):
            actions.main(["foo"])
        self.assertEqual(dummy_calls, [True])

    def test_unknown_action(self):
        """Unknown actions aren't a traceback."""
        exit_string = actions.main(["foo"])
        self.assertEqual("Action foo undefined", exit_string)

    def test_failing_action(self):
        """Actions which traceback trigger action_fail() calls."""
        dummy_calls = []

        self.action_fail.side_effect = dummy_calls.append

        def dummy_action(args):
            raise ValueError("uh oh")

        with mock.patch.dict(actions.ACTIONS, {"foo": dummy_action}):
            actions.main(["foo"])
        self.assertEqual(dummy_calls, ["Action foo failed: uh oh"])
