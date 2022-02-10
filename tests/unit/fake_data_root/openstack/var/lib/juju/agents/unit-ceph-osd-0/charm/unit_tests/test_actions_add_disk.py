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

from unittest import mock

from actions import add_disk

from test_utils import CharmTestCase


class AddDiskActionTests(CharmTestCase):
    def setUp(self):
        super(AddDiskActionTests, self).setUp(
            add_disk, ['hookenv', 'kv'])
        self.kv.return_value = self.kv

    @mock.patch.object(add_disk.ceph_hooks, 'get_journal_devices')
    @mock.patch.object(add_disk.charms_ceph.utils, 'osdize')
    def test_add_device(self, mock_osdize, mock_get_journal_devices):

        def fake_config(key):
            return {
                'ignore-device-errors': True,
                'osd-encrypt': True,
                'bluestore': True,
                'osd-encrypt-keymanager': True,
                'autotune': False,
            }.get(key)

        self.hookenv.config.side_effect = fake_config
        mock_get_journal_devices.return_value = ''
        self.hookenv.relation_ids.return_value = ['ceph:0']

        db = mock.MagicMock()
        self.kv.return_value = db
        db.get.return_value = ['/dev/myosddev']

        request = {'ops': []}
        add_disk.add_device(request, '/dev/myosddev')

        call = mock.call(relation_id='ceph:0',
                         relation_settings={'bootstrapped-osds': 1})
        self.hookenv.relation_set.assert_has_calls([call])
        mock_osdize.assert_has_calls([mock.call('/dev/myosddev',
                                                None, '', True, True, True,
                                                True)])
