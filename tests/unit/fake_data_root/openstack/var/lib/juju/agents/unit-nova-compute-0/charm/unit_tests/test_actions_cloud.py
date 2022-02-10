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
import sys
from unittest import TestCase
from unittest.mock import MagicMock, patch, call

sys.modules['nova_compute_hooks'] = MagicMock()
import cloud
del sys.modules['nova_compute_hooks']


class _MockComputeHost:

    def __init__(self, node_name, state='enabled', binary='nova-compute'):
        self.node_name = node_name
        self.state = state
        self.binary = binary

    def to_dict(self):
        return {'node_name': self.node_name,
                'state': self.state,
                'binary': self.binary}


class _ActionTestCase(TestCase):

    NAME = ''

    def __init__(self, methodName='runTest'):
        super(_ActionTestCase, self).__init__(methodName)
        self._func_args = {}
        self.hostname = 'nova.compute.0'
        self.nova_service_id = '0'

    def setUp(self, to_mock=None):
        """
        Mock commonly used objects from cloud.py module. Additional objects
        can be passed in for mocking in the form of a dict with format
        {module.object: ['method1', 'method2']}

        Example usage:
        ```python
            class MyTestCase(unittest.TestCase):
                def setUp(self, to_mock=None):
                    additional_mocks = {
                                        actions.os: ['remove', 'mkdir'],
                                        actions.shutil: ['rmtree'],
                                        }
                    super(MyTestcase, self).setUp(to_mock=additional_mocks)

        ```

        :param to_mock: Additional objects to mock
        :return: None
        """
        to_mock = to_mock or {}
        default_mock = {
            cloud: {'function_set',
                    'function_fail',
                    'status_get',
                    'status_set',
                    },
            cloud.cloud_utils: {'service_hostname',
                                'nova_client',
                                'nova_service_id',
                                'running_vms',
                                }
        }
        for key, value in to_mock.items():
            if key in default_mock:
                default_mock[key].update(value)
            else:
                default_mock[key] = value
        self.patch_all(default_mock)

        cloud.cloud_utils.service_hostname.return_value = self.hostname
        cloud.cloud_utils.nova_service_id.return_value = self.nova_service_id
        cloud.cloud_utils.running_vms.return_value = 0
        cloud.cloud_utils.nova_client.return_value = MagicMock()

    def patch_all(self, to_patch):
        for object_, methods in to_patch.items():
            for method in methods:
                mock_ = patch.object(object_, method, MagicMock())
                mock_.start()
                self.addCleanup(mock_.stop)

    def assert_function_fail_msg(self, msg):
        """Shortcut for asserting error with default structure"""
        cloud.function_fail.assert_called_with("Action {} failed: "
                                               "{}".format(self.NAME, msg))

    def call_action(self):
        """Shortcut to calling action based on the current TestCase"""
        cloud.main([self.NAME])


class TestGenericAction(_ActionTestCase):

    def test_unknown_action(self):
        """Test expected fail when running undefined action."""
        bad_action = 'foo'
        expected_error = 'Action {} undefined'.format(bad_action)
        cloud.main([bad_action])
        cloud.function_fail.assert_called_with(expected_error)

    def test_unknown_nova_compute_state(self):
        """Test expected error when setting nova-compute state
        to unknown value"""

        bad_state = 'foo'
        self.assertRaises(RuntimeError, cloud._set_service, bad_state)


class TestDisableAction(_ActionTestCase):
    NAME = 'disable'

    def test_successful_disable(self):
        """Test that expected steps are performed when enabling nova-compute
        service"""
        client = MagicMock()
        nova_services = MagicMock()
        client.services = nova_services

        cloud.cloud_utils.nova_client.return_value = client

        self.call_action()

        nova_services.disable.assert_called_with(self.hostname, 'nova-compute')
        cloud.function_fail.assert_not_called()


class TestEnableAction(_ActionTestCase):
    NAME = 'enable'

    def test_successful_disable(self):
        """Test that expected steps are performed when disabling nova-compute
        service"""
        client = MagicMock()
        nova_services = MagicMock()
        client.services = nova_services

        cloud.cloud_utils.nova_client.return_value = client

        self.call_action()

        nova_services.enable.assert_called_with(self.hostname, 'nova-compute')
        cloud.function_fail.assert_not_called()


class TestRemoveFromCloudAction(_ActionTestCase):
    NAME = 'remove-from-cloud'

    def __init__(self, methodName='runTest'):
        super(TestRemoveFromCloudAction, self).__init__(methodName=methodName)
        self.nova_client = MagicMock()

    def setUp(self, to_mock=None):
        additional_mocks = {
            cloud: {'service_pause'}
        }
        super(TestRemoveFromCloudAction, self).setUp(to_mock=additional_mocks)
        cloud.cloud_utils.nova_client.return_value = self.nova_client

    def test_nova_is_running_vms(self):
        """Action fails if there are VMs present on the unit"""
        cloud.cloud_utils.running_vms.return_value = 1
        error_msg = "This unit can not be removed from the cloud because " \
                    "it's still running VMs. Please remove these VMs or " \
                    "migrate them to another nova-compute unit"
        self.call_action()
        self.assert_function_fail_msg(error_msg)

    def test_remove_from_cloud(self):
        """Test that expected steps are executed when running action
        remove-from-cloud"""
        nova_services = MagicMock()
        self.nova_client.services = nova_services

        self.call_action()

        # stopping services
        cloud.service_pause.assert_called_with('nova-compute')

        # unregistering services
        nova_services.delete.assert_called_with(self.nova_service_id)

        # setting unit state
        cloud.status_set.assert_called_with(
            cloud.WORKLOAD_STATES.BLOCKED,
            cloud.UNIT_REMOVED_MSG
        )
        cloud.function_set.assert_called_with(
            {'message': cloud.UNIT_REMOVED_MSG}
        )
        cloud.function_fail.assert_not_called()


class TestRegisterToCloud(_ActionTestCase):
    NAME = 'register-to-cloud'

    def setUp(self, to_mock=None):
        additional_mocks = {
            cloud: {'service_resume'}
        }
        super(TestRegisterToCloud, self).setUp(to_mock=additional_mocks)

    def test_dont_reset_unit_status(self):
        """Test that action won't reset unit state if the current state was not
        set explicitly by 'remove-from-cloud' action"""
        cloud.status_get.return_value = (cloud.WORKLOAD_STATES.BLOCKED.value,
                                         'Unrelated reason for blocked status')
        self.call_action()

        cloud.status_set.assert_not_called()
        cloud.function_fail.assert_not_called()

    def test_reset_unit_status(self):
        """Test that action will reset unit state if the current state was
        set explicitly by 'remove-from-cloud' action"""
        cloud.status_get.return_value = (cloud.WORKLOAD_STATES.BLOCKED.value,
                                         cloud.UNIT_REMOVED_MSG)
        self.call_action()

        cloud.status_set.assert_called_with(cloud.WORKLOAD_STATES.ACTIVE,
                                            'Unit is ready')
        cloud.function_fail.assert_not_called()

    def test_action_starts_services(self):
        """Test that expected steps are executed when running action
        register-to-cloud"""
        self.call_action()

        cloud.service_resume.assert_called_with('nova-compute')
        cloud.function_fail.assert_not_called()


class TestInstanceCount(_ActionTestCase):
    NAME = 'instance-count'

    def test_action_instance_count(self):
        """Test 'instance-count' action"""
        running_vms = 2
        cloud.cloud_utils.running_vms.return_value = 2

        self.call_action()

        cloud.function_set.assert_called_with({'instance-count': running_vms})


class TestListComputeNodes(_ActionTestCase):
    NAME = 'list-compute-nodes'

    MOCK_LIST = [_MockComputeHost('compute0'),
                 _MockComputeHost('compute1')]

    def setUp(self, to_mock=None):
        super(TestListComputeNodes, self).setUp()
        self.nova_client = MagicMock()
        services = MagicMock()
        services.list.return_value = self.MOCK_LIST
        self.nova_client.services = services

    def test_list_compute_nodes(self):
        """Test listing nov-compute services."""
        cloud.cloud_utils.nova_client.return_value = self.nova_client
        expected_identity = 'compute-0'
        cloud.cloud_utils.service_hostname.return_value = expected_identity
        self.call_action()

        expected_nodes = [host.to_dict() for host in self.MOCK_LIST
                          if host.binary == 'nova-compute']

        expected_calls = [call({'node-name': expected_identity}),
                          call({'compute-nodes': json.dumps(expected_nodes)})]

        self.nova_client.services.list.assert_called_with(
            binary='nova-compute')
        cloud.function_set.assert_has_calls(expected_calls)


class TestNodeName(_ActionTestCase):
    NAME = 'node-name'

    def setUp(self, to_mock=None):
        super(TestNodeName, self).setUp()

    def test_get_compute_name(self):
        """Test action 'node-name'"""
        hostname = 'compute0.cloud'
        cloud.cloud_utils.service_hostname.return_value = hostname

        self.call_action()

        cloud.function_set.assert_called_with({'node-name': hostname})
