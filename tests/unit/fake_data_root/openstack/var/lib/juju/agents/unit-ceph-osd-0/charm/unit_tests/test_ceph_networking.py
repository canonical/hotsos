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

import test_utils
import charmhelpers.core.hookenv as hookenv
import utils as ceph_utils

TO_PATCH_SPACES = [
    'network_get_primary_address',
    'log',
    'get_host_ip',
    'config',
    'get_network_addrs',
    'cached',
]


class CephNetworkSpaceTestCase(test_utils.CharmTestCase):
    def setUp(self):
        super(CephNetworkSpaceTestCase, self).setUp(ceph_utils,
                                                    TO_PATCH_SPACES)
        self.config.side_effect = self.test_config.get

    def tearDown(self):
        # Reset @cached cache
        hookenv.cache = {}

    def test_no_network_space_support(self):
        self.get_host_ip.return_value = '192.168.2.1'
        self.network_get_primary_address.side_effect = NotImplementedError
        self.assertEqual(ceph_utils.get_cluster_addr(),
                         '192.168.2.1')
        self.assertEqual(ceph_utils.get_public_addr(),
                         '192.168.2.1')

    def test_public_network_space(self):
        self.network_get_primary_address.return_value = '10.20.40.2'
        self.assertEqual(ceph_utils.get_public_addr(),
                         '10.20.40.2')
        self.network_get_primary_address.assert_called_with('public')
        self.config.assert_called_with('ceph-public-network')

    def test_cluster_network_space(self):
        self.network_get_primary_address.return_value = '10.20.50.2'
        self.assertEqual(ceph_utils.get_cluster_addr(),
                         '10.20.50.2')
        self.network_get_primary_address.assert_called_with('cluster')
        self.config.assert_called_with('ceph-cluster-network')

    def test_config_options_in_use(self):
        self.get_network_addrs.return_value = ['192.122.20.2']
        self.test_config.set('ceph-cluster-network', '192.122.20.0/24')
        self.assertEqual(ceph_utils.get_cluster_addr(),
                         '192.122.20.2')
