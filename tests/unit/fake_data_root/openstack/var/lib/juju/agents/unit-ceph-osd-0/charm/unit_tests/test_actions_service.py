# Copyright 2020 Canonical Ltd
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

import unittest.mock as mock
from contextlib import contextmanager

from actions import service
from hooks import utils

from test_utils import CharmTestCase


class CompletedProcessMock:
    def __init__(self, stdout=b'', stderr=b''):
        self.stdout = stdout
        self.stderr = stderr


class ServiceActionTests(CharmTestCase):
    _PRESENT_SERVICES = [
        "ceph-osd@0.service",
        "ceph-osd@1.service",
        "ceph-osd@2.service",
    ]

    _TARGET_ALL = 'ceph-osd.target'

    _CHECK_CALL_TIMEOUT = 300

    def __init__(self, methodName='runTest'):
        super(ServiceActionTests, self).__init__(methodName)

    def setUp(self, obj=None, patches=None):
        super(ServiceActionTests, self).setUp(
            service,
            ['subprocess', 'function_fail',
             'log', 'assess_status', 'shutil']
        )
        present_services = '\n'.join(self._PRESENT_SERVICES).encode('utf-8')

        self.shutil.which.return_value = '/bin/systemctl'
        self.subprocess.check_call.return_value = None
        self.subprocess.run.return_value = CompletedProcessMock(
            stdout=present_services)

    @contextmanager
    def func_call_arguments(self, osds=None):
        with mock.patch("utils.function_get") as mock_function_get:
            self._func_args = {'osds': osds}
            mock_function_get.side_effect = \
                lambda arg: self._func_args.get(arg)
            yield

    def assert_action_start_fail(self, msg):
        self.assert_function_fail(service.START, msg)

    def assert_action_stop_fail(self, msg):
        self.assert_function_fail(service.STOP, msg)

    def assert_function_fail(self, action, msg):
        expected_error = "Action '{}' failed: {}".format(action, msg)
        self.function_fail.assert_called_with(expected_error)

    @staticmethod
    def call_action_start():
        service.main(['start'])

    @staticmethod
    def call_action_stop():
        service.main(['stop'])

    def test_systemctl_execute_all(self):
        action = 'start'
        services = utils.ALL

        expected_call = mock.call(['systemctl', action, self._TARGET_ALL],
                                  timeout=self._CHECK_CALL_TIMEOUT)

        service.systemctl_execute(action, services)

        self.subprocess.check_call.assert_has_calls([expected_call])

    def systemctl_execute_specific(self):
        action = 'start'
        services = ['ceph-osd@1.service', 'ceph-osd@2.service']

        systemctl_call = ['systemctl', action] + services
        expected_call = mock.call(systemctl_call,
                                  timeout=self._CHECK_CALL_TIMEOUT)

        service.systemctl_execute(action, services)

        self.subprocess.check_call.assert_has_calls([expected_call])

    def test_id_translation(self):
        service_ids = {1, utils.ALL, 2}
        expected_names = [
            'ceph-osd@1.service',
            utils.ALL,
            'ceph-osd@2.service',
        ]
        service_names = service.osd_ids_to_service_names(service_ids)
        self.assertEqual(sorted(service_names), sorted(expected_names))

    def test_skip_service_presence_check(self):
        service_list = [utils.ALL]

        service.check_service_is_present(service_list)

        self.subprocess.run.assert_not_called()

    def test_raise_all_missing_services(self):
        missing_service_id = '99,100'
        missing_list = []
        for id_ in missing_service_id.split(','):
            missing_list.append("ceph-osd@{}.service".format(id_))

        service_list_cmd = ['systemctl', 'list-units', '--full', '--all',
                            '--no-pager', '-t', 'service']

        err_msg = 'Some services are not present on this ' \
                  'unit: {}'.format(missing_list)

        with self.assertRaises(RuntimeError, msg=err_msg):
            service.check_service_is_present(missing_list)

        self.subprocess.run.assert_called_with(service_list_cmd,
                                               stdout=self.subprocess.PIPE,
                                               timeout=30)

    def test_fail_execute_unknown_action(self):
        action = 'foo'
        err_msg = 'Unknown action "{}"'.format(action)
        with self.assertRaises(RuntimeError, msg=err_msg):
            service.execute_action(action)

    @mock.patch.object(service, 'systemctl_execute')
    def test_execute_action(self, _):
        with self.func_call_arguments(osds=utils.ALL):
            service.execute_action(service.START)
            service.systemctl_execute.assert_called_with(service.START,
                                                         [utils.ALL])

            service.execute_action(service.STOP)
            service.systemctl_execute.assert_called_with(service.STOP,
                                                         [utils.ALL])

    @mock.patch.object(service, 'execute_action')
    def test_action_stop(self, execute_action):
        self.call_action_stop()
        execute_action.assert_called_with(service.STOP)

    @mock.patch.object(service, 'execute_action')
    def test_action_start(self, execute_action):
        self.call_action_start()
        execute_action.assert_called_with(service.START)

    def test_actions_requires_systemd(self):
        """Actions will fail if systemd is not present on the system"""
        self.shutil.which.return_value = None
        expected_error = 'This action requires systemd'
        with self.func_call_arguments(osds='all'):
            self.call_action_start()
            self.assert_action_start_fail(expected_error)

            self.call_action_stop()
            self.assert_action_stop_fail(expected_error)

            self.subprocess.check_call.assert_not_called()

    def test_unknown_action(self):
        action = 'foo'
        err_msg = 'Action {} undefined'.format(action)
        service.main([action])
        self.function_fail.assert_called_with(err_msg)

    @mock.patch.object(service, 'execute_action')
    def test_action_failure(self, start_function):
        err_msg = 'Test Error'
        service.execute_action.side_effect = RuntimeError(err_msg)

        self.call_action_start()

        self.assert_action_start_fail(err_msg)
