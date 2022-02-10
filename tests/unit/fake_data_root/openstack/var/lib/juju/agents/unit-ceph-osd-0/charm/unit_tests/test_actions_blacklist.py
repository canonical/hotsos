# Copyright 2017 Canonical Ltd
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

from charmhelpers.core import hookenv

from actions import blacklist

from test_utils import CharmTestCase


class BlacklistActionTests(CharmTestCase):
    def setUp(self):
        super(BlacklistActionTests, self).setUp(
            blacklist, [])

    @mock.patch('os.path.isabs')
    @mock.patch('os.path.exists')
    @mock.patch('charmhelpers.core.unitdata.kv')
    @mock.patch('charmhelpers.core.hookenv.action_get')
    def test_add_disk(self, _action_get, _kv, _exists, _isabs):
        """Add device with absolute and existent path succeeds"""
        _action_get.return_value = '/dev/vda'
        _kv.return_value = _kv
        _kv.get.return_value = []
        _exists.return_value = True
        _isabs.return_value = True
        blacklist.blacklist_add()
        _exists.assert_called()
        _isabs.assert_called()
        _kv.get.assert_called_with('osd-blacklist', [])
        _kv.set.assert_called_with('osd-blacklist', ['/dev/vda'])
        _kv.flush.assert_called()

    @mock.patch('os.path.isabs')
    @mock.patch('os.path.exists')
    @mock.patch('charmhelpers.core.unitdata.kv')
    @mock.patch('charmhelpers.core.hookenv.action_get')
    def test_add_disk_nonexistent(self, _action_get, _kv, _exists, _isabs):
        """Add device with non-existent path raises exception"""
        _action_get.return_value = '/dev/vda'
        _kv.return_value = _kv
        _kv.get.return_value = []
        _exists.return_value = False
        _isabs.return_value = True
        with self.assertRaises(blacklist.Error):
            blacklist.blacklist_add()
        _isabs.assert_called()
        _exists.assert_called()
        _kv.get.assert_called_with('osd-blacklist', [])
        assert not _kv.set.called
        assert not _kv.flush.called

    @mock.patch('os.path.isabs')
    @mock.patch('os.path.exists')
    @mock.patch('charmhelpers.core.unitdata.kv')
    @mock.patch('charmhelpers.core.hookenv.action_get')
    def test_add_disk_nonabsolute(self, _action_get, _kv, _exists, _isabs):
        """Add device with non-absolute path raises exception"""
        _action_get.return_value = 'vda'
        _kv.return_value = _kv
        _kv.get.return_value = []
        _exists.return_value = True
        _isabs.return_value = False
        with self.assertRaises(blacklist.Error):
            blacklist.blacklist_add()
        _isabs.assert_called()
        _kv.get.assert_called_with('osd-blacklist', [])
        assert not _exists.called
        assert not _kv.set.called
        assert not _kv.flush.called

    @mock.patch('charmhelpers.core.unitdata.kv')
    @mock.patch('charmhelpers.core.hookenv.action_get')
    def test_remove_disk(self, _action_get, _kv):
        """Remove action succeeds, and regardless of existence of device"""
        _action_get.return_value = '/nonexistent2'
        _kv.return_value = _kv
        _kv.get.return_value = ['/nonexistent1', '/nonexistent2']
        blacklist.blacklist_remove()
        _kv.get.assert_called_with('osd-blacklist', [])
        _kv.set.assert_called_with('osd-blacklist', ['/nonexistent1'])
        _kv.flush.assert_called()

    @mock.patch('charmhelpers.core.unitdata.kv')
    @mock.patch('charmhelpers.core.hookenv.action_get')
    def test_remove_disk_nonlisted(self, _action_get, _kv):
        """Remove action raises on removal of device not in list"""
        _action_get.return_value = '/nonexistent3'
        _kv.return_value = _kv
        _kv.get.return_value = ['/nonexistent1', '/nonexistent2']
        with self.assertRaises(blacklist.Error):
            blacklist.blacklist_remove()
        _kv.get.assert_called_with('osd-blacklist', [])
        assert not _kv.set.called
        assert not _kv.flush.called


class MainTestCase(CharmTestCase):
    def setUp(self):
        super(MainTestCase, self).setUp(hookenv, ["action_fail"])

    def test_invokes_action(self):
        dummy_calls = []

        def dummy_action():
            dummy_calls.append(True)

        with mock.patch.dict(blacklist.ACTIONS, {"foo": dummy_action}):
            blacklist.main(["foo"])
        self.assertEqual(dummy_calls, [True])

    def test_unknown_action(self):
        """Unknown actions aren't a traceback."""
        exit_string = blacklist.main(["foo"])
        self.assertEqual("Action foo undefined", exit_string)

    def test_failing_action(self):
        """Actions which traceback trigger action_fail() calls."""
        dummy_calls = []

        self.action_fail.side_effect = dummy_calls.append

        def dummy_action():
            raise ValueError("uh oh")

        with mock.patch.dict(blacklist.ACTIONS, {"foo": dummy_action}):
            blacklist.main(["foo"])
        self.assertEqual(dummy_calls, ["Action foo failed: uh oh"])
