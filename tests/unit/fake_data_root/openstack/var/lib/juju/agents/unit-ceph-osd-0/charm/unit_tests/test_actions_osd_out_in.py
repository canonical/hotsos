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

import subprocess
import sys

from unittest import mock

from test_utils import CharmTestCase

sys.path.append('hooks')

import osd_in_out as actions


def mock_check_output(cmd, **kwargs):
    action, osd_id = cmd[-2:]  # get the last two arguments from cmd
    return "marked {} osd.{}. \n".format(action, osd_id).encode("utf-8")


class OSDOutTestCase(CharmTestCase):
    def setUp(self):
        super(OSDOutTestCase, self).setUp(
            actions, ["check_output",
                      "get_local_osd_ids",
                      "assess_status",
                      "parse_osds_arguments",
                      "function_fail",
                      "function_set"])

        self.check_output.side_effect = mock_check_output

    def test_osd_out(self):
        self.get_local_osd_ids.return_value = ["5", "6", "7"]
        self.parse_osds_arguments.return_value = {"5"}
        actions.osd_out()
        self.check_output.assert_called_once_with(
            ["ceph", "--id", "osd-upgrade", "osd", "out", "5"],
            stderr=subprocess.STDOUT
        )
        self.assess_status.assert_called_once_with()

    def test_osd_out_all(self):
        self.get_local_osd_ids.return_value = ["5", "6", "7"]
        self.parse_osds_arguments.return_value = {"all"}
        actions.osd_out()
        self.check_output.assert_has_calls(
            [mock.call(
                ["ceph", "--id", "osd-upgrade", "osd", "out", i],
                stderr=subprocess.STDOUT
            ) for i in set(["5", "6", "7"])])
        self.assess_status.assert_called_once_with()

    def test_osd_out_not_local(self):
        self.get_local_osd_ids.return_value = ["5"]
        self.parse_osds_arguments.return_value = {"6", "7", "8"}
        actions.osd_out()
        self.check_output.assert_not_called()
        self.function_fail.assert_called_once_with(
            "invalid ceph OSD device id: "
            "{}".format(",".join(set(["6", "7", "8"]))))
        self.assess_status.assert_not_called()


class OSDInTestCase(CharmTestCase):
    def setUp(self):
        super(OSDInTestCase, self).setUp(
            actions, ["check_output",
                      "get_local_osd_ids",
                      "assess_status",
                      "parse_osds_arguments",
                      "function_fail",
                      "function_set"])

        self.check_output.side_effect = mock_check_output

    def test_osd_in(self):
        self.get_local_osd_ids.return_value = ["5", "6", "7"]
        self.parse_osds_arguments.return_value = {"5"}
        actions.osd_in()
        self.check_output.assert_called_once_with(
            ["ceph", "--id", "osd-upgrade", "osd", "in", "5"],
            stderr=subprocess.STDOUT
        )
        self.assess_status.assert_called_once_with()

    def test_osd_in_all(self):
        self.get_local_osd_ids.return_value = ["5", "6", "7"]
        self.parse_osds_arguments.return_value = {"all"}
        actions.osd_in()
        self.check_output.assert_has_calls(
            [mock.call(
                ["ceph", "--id", "osd-upgrade", "osd", "in", i],
                stderr=subprocess.STDOUT
            ) for i in set(["5", "6", "7"])])
        self.assess_status.assert_called_once_with()

    def test_osd_in_not_local(self):
        self.get_local_osd_ids.return_value = ["5"]
        self.parse_osds_arguments.return_value = {"6"}
        actions.osd_in()
        self.check_output.assert_not_called()
        self.function_fail.assert_called_once_with(
            "invalid ceph OSD device id: 6")
        self.assess_status.assert_not_called()


class OSDMountTestCase(CharmTestCase):
    def setUp(self):
        super(OSDMountTestCase, self).setUp(actions, [])

    @mock.patch('os.path.exists')
    @mock.patch('os.listdir')
    @mock.patch('charms_ceph.utils.filesystem_mounted')
    def test_mounted_osds(self, fs_mounted, listdir, exists):
        exists.return_value = True
        listdir.return_value = [
            '/var/lib/ceph/osd/ceph-1', '/var/lib/ceph/osd/ceph-2']
        fs_mounted.side_effect = lambda x: x == listdir.return_value[0]
        osds = actions.get_local_osd_ids()
        self.assertIn(listdir.return_value[0][-1], osds)
        self.assertNotIn(listdir.return_value[1][-1], osds)


class MainTestCase(CharmTestCase):
    def setUp(self):
        super(MainTestCase, self).setUp(actions, ["function_fail"])

    def test_invokes_action(self):
        dummy_calls = []

        def dummy_action():
            dummy_calls.append(True)

        with mock.patch.dict(actions.ACTIONS, {"foo": dummy_action}):
            actions.main(["foo"])
        self.assertEqual(dummy_calls, [True])

    def test_unknown_action(self):
        """Unknown actions aren't a traceback."""
        exit_string = actions.main(["foo"])
        self.assertEqual("Action foo undefined", exit_string)

    def test_failing_action(self):
        """Actions which traceback trigger function_fail() calls."""
        dummy_calls = []

        self.function_fail.side_effect = dummy_calls.append

        def dummy_action():
            raise ValueError("uh oh")

        with mock.patch.dict(actions.ACTIONS, {"foo": dummy_action}):
            actions.main(["foo"])
        self.assertEqual(dummy_calls, ["Action foo failed: uh oh"])
