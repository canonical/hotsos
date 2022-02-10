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
from test_utils import CharmTestCase
import virshaudit as actions


class MainTestCase(CharmTestCase):
    def setUp(self):
        pass

    @mock.patch('subprocess.check_output')
    @mock.patch('charmhelpers.core.hookenv.action_set')
    def test_virsh_audit(self, mock_action_set, mock_check_output):
        virsh_output = "1    instance-00000001   running"
        mock_check_output.return_value = virsh_output.encode()
        dummy_action = []
        mock_action_set.side_effect = dummy_action.append
        actions.virsh_audit()
        self.assertEqual(len(dummy_action), 1)
        d = dummy_action[0]
        self.assertIsInstance(d, dict)
        self.assert_('virsh-domains' in d)
        self.assertEqual(d['virsh-domains'], virsh_output)
