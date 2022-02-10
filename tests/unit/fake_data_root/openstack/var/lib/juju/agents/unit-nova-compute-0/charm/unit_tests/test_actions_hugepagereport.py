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
import os
import shutil
from tempfile import mkdtemp
from test_utils import CharmTestCase

import hugepagereport as actions

tmpdir = 'hugepagestats-test.'

test_stats = {'free_hugepages': '224',
              'nr_hugepages': '12'}


class MainTestCase(CharmTestCase):

    def setUp(self):
        self.sysfs = sysfs = mkdtemp(prefix=tmpdir)
        self.addCleanup(shutil.rmtree, sysfs)
        p = mock.patch('hugepagereport.SYSFS', new=sysfs)
        p.start()
        self.addCleanup(p.stop)
        hpath = "{}/devices/system/node/node0/hugepages/hugepages-1048576kB"
        self.hugepagestats = hpath.format(sysfs)
        os.makedirs(self.hugepagestats)
        for fn, val in test_stats.items():
            with open(os.path.join(self.hugepagestats, fn), 'w') as f:
                f.write(val)

    @mock.patch('charmhelpers.core.hookenv.action_get')
    @mock.patch('charmhelpers.core.hookenv.action_set')
    def test_hugepagesreport(self, mock_action_set, mock_action_get):
        dummy_action = []
        mock_action_set.side_effect = dummy_action.append
        actions.hugepages_report()
        self.assertEqual(len(dummy_action), 1)
        d = dummy_action[0]
        self.assertIsInstance(d, dict)
        self.assert_('hugepagestats' in d)
        self.assert_(
            d['hugepagestats'].find('/free_hugepages') != -1)
