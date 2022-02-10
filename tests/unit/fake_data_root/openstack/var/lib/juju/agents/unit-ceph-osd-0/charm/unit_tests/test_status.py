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
import test_utils

from unittest.mock import MagicMock, patch

with patch('charmhelpers.contrib.hardening.harden.harden') as mock_dec:
    mock_dec.side_effect = (lambda *dargs, **dkwargs: lambda f:
                            lambda *args, **kwargs: f(*args, **kwargs))
    import ceph_hooks as hooks

TO_PATCH = [
    'status_set',
    'config',
    'ceph',
    'relation_ids',
    'relation_get',
    'related_units',
    'get_conf',
    'application_version_set',
    'get_upstream_version',
    'vaultlocker',
    'use_vaultlocker',
]

CEPH_MONS = [
    'ceph/0',
    'ceph/1',
    'ceph/2',
]


class ServiceStatusTestCase(test_utils.CharmTestCase):

    def setUp(self):
        super(ServiceStatusTestCase, self).setUp(hooks, TO_PATCH)
        self.config.side_effect = self.test_config.get
        self.get_upstream_version.return_value = '10.2.2'
        self.use_vaultlocker.return_value = False

    def test_assess_status_no_monitor_relation(self):
        self.relation_ids.return_value = []
        hooks.assess_status()
        self.status_set.assert_called_with('blocked', mock.ANY)
        self.application_version_set.assert_called_with('10.2.2')

    def test_assess_status_monitor_relation_incomplete(self):
        self.relation_ids.return_value = ['mon:1']
        self.related_units.return_value = CEPH_MONS
        self.get_conf.return_value = None
        hooks.assess_status()
        self.status_set.assert_called_with('waiting', mock.ANY)
        self.application_version_set.assert_called_with('10.2.2')

    @patch.object(hooks.ch_context, 'CephBlueStoreCompressionContext',
                  lambda: MagicMock())
    def test_assess_status_monitor_complete_no_disks(self):
        self.relation_ids.return_value = ['mon:1']
        self.related_units.return_value = CEPH_MONS
        self.get_conf.return_value = 'monitor-bootstrap-key'
        self.ceph.get_running_osds.return_value = []
        hooks.assess_status()
        self.status_set.assert_called_with('blocked', mock.ANY)
        self.application_version_set.assert_called_with('10.2.2')

    @patch.object(hooks.ch_context, 'CephBlueStoreCompressionContext',
                  lambda: MagicMock())
    def test_assess_status_monitor_complete_disks(self):
        self.relation_ids.return_value = ['mon:1']
        self.related_units.return_value = CEPH_MONS
        self.get_conf.return_value = 'monitor-bootstrap-key'
        self.ceph.get_running_osds.return_value = ['12345',
                                                   '67890']
        self.get_upstream_version.return_value = '12.2.4'
        hooks.assess_status()
        self.status_set.assert_called_with('active', mock.ANY)
        self.application_version_set.assert_called_with('12.2.4')

    def test_assess_status_monitor_vault_missing(self):
        _test_relations = {
            'mon': ['mon:1'],
        }
        self.relation_ids.side_effect = lambda x: _test_relations.get(x, [])
        self.related_units.return_value = CEPH_MONS
        self.vaultlocker.vault_relation_complete.return_value = False
        self.use_vaultlocker.return_value = True
        self.get_conf.return_value = 'monitor-bootstrap-key'
        self.ceph.get_running_osds.return_value = ['12345',
                                                   '67890']
        self.get_upstream_version.return_value = '12.2.4'
        hooks.assess_status()
        self.status_set.assert_called_with('blocked', mock.ANY)
        self.application_version_set.assert_called_with('12.2.4')

    def test_assess_status_monitor_vault_incomplete(self):
        _test_relations = {
            'mon': ['mon:1'],
            'secrets-storage': ['secrets-storage:6']
        }
        self.relation_ids.side_effect = lambda x: _test_relations.get(x, [])
        self.related_units.return_value = CEPH_MONS
        self.vaultlocker.vault_relation_complete.return_value = False
        self.use_vaultlocker.return_value = True
        self.get_conf.return_value = 'monitor-bootstrap-key'
        self.ceph.get_running_osds.return_value = ['12345',
                                                   '67890']
        self.get_upstream_version.return_value = '12.2.4'
        hooks.assess_status()
        self.status_set.assert_called_with('waiting', mock.ANY)
        self.application_version_set.assert_called_with('12.2.4')

    @patch.object(hooks.ch_context, 'CephBlueStoreCompressionContext')
    def test_assess_status_invalid_bluestore_compression_options(
            self, _bluestore_compression):
        self.relation_ids.return_value = ['mon:1']
        self.related_units.return_value = CEPH_MONS
        _bluestore_compression().validate.side_effect = ValueError(
            'fake-config is invalid')
        hooks.assess_status()
        self.status_set.assert_called_with(
            'blocked', 'Invalid configuration: fake-config is invalid')
