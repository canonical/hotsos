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
from unittest import TestCase
from unittest.mock import MagicMock, patch

import nova_compute.cloud_utils as cloud_utils


class NovaServiceMock():

    def __init__(self, id, host, binary):
        self.id = id
        self.host = host
        self.binary = binary


class TestCloudUtils(TestCase):

    def __init__(self, methodName='runTest'):
        super(TestCloudUtils, self).__init__(methodName=methodName)

        self.nova_client = MagicMock()
        nova_services = MagicMock()
        nova_services.list.return_value = []
        self.nova_client.services = nova_services

        self.neutron_client = MagicMock()

        self.unit_hostname = 'nova-commpute-0'

    def setUp(self):
        to_patch = [
            'loading',
            'log',
            'nova_client_',
            '_nova_cfg',
            'service_hostname',
        ]
        for object_ in to_patch:
            mock_ = patch.object(cloud_utils, object_, MagicMock())
            mock_.start()
            self.addCleanup(mock_.stop)

        cloud_utils._nova_cfg.return_value = MagicMock()
        cloud_utils.nova_client.return_value = self.nova_client
        cloud_utils.service_hostname.return_value = self.unit_hostname

    def test_os_credentials_content(self):
        """Test that function '_os_credentials' returns credentials
        in expected format"""
        credentials = cloud_utils._os_credentials()
        expected_keys = [
            'username',
            'password',
            'auth_url',
            'project_name',
            'project_domain_name',
            'user_domain_name',
        ]

        for key in expected_keys:
            self.assertIn(key, credentials.keys())

    def test_nova_service_not_present(self):
        """Test that function 'nova_service_id' raises expected exception if
        current unit is not registered in 'nova-cloud-controller'"""
        nova_client = MagicMock()
        nova_services = MagicMock()
        nova_services.list.return_value = []
        nova_client.services = nova_services
        cloud_utils.nova_client.return_value = nova_client

        self.assertRaises(RuntimeError, cloud_utils.nova_service_id,
                          nova_client)

    def test_nova_service_id_multiple_services(self):
        """Test that function 'nova_service_id' will log warning and return
        first ID in the event that multiple nova-compute services are present
        on the same host"""
        first_id = 0
        second_id = 1
        warning_msg = 'Host "{}" has more than 1 nova-compute service ' \
                      'registered. Selecting one ID ' \
                      'randomly.'.format(self.unit_hostname)

        self.nova_client.services.list.return_value = [
            NovaServiceMock(first_id, self.unit_hostname, 'nova-compute'),
            NovaServiceMock(second_id, self.unit_hostname, 'nova-compute'),
        ]

        service_id = cloud_utils.nova_service_id(self.nova_client)

        self.assertEqual(service_id, first_id)
        cloud_utils.log.assert_called_with(warning_msg, cloud_utils.WARNING)
