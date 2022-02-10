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
import json
import unittest.mock as mock
import subprocess
import sys

mock_apt = mock.MagicMock()
sys.modules["apt_pkg"] = mock_apt
import actions
import test_utils


class ClusterStatusTestCase(test_utils.CharmTestCase):
    TO_PATCH = [
        "function_fail",
        "function_get",
        "function_set",
        "pcmk",
        "log",
    ]
    health_status = {
        "crm_mon_version": "2.0.3",
        "summary": {
            "last_update": {"time": "Fri Dec  4 14:52:26 2020"},
            "last_change": {"time": "Fri Dec  4 14:08:26 2020"},
            "nodes_configured": {"number": "3"}},
        "nodes": {
            "juju-d07fb7-3": {"online": "true", "type": "member"},
            "juju-d07fb7-4": {"online": "true", "type": "member"},
            "juju-d07fb7-5": {"online": "true", "type": "member"}},
        "resources": {},
        "history": {
            "juju-d07fb7-3": {
                "res_ks_36385de_vip": [{"call": "11", "task": "start"},
                                       {"call": "13", "task": "monitor"}],
                "res_ks_haproxy": [{"call": "10", "task": "probe"},
                                   {"call": "12", "task": "monitor"}]}}
    }

    def setUp(self):
        super(ClusterStatusTestCase, self).setUp(actions, self.TO_PATCH)

        def _cluster_status(resources=True, history=False):
            status = self.health_status.copy()
            if not resources:
                del status["resources"]

            if not history:
                del status["history"]

            return status

        self.pcmk.cluster_status.side_effect = _cluster_status
        self._function_get = {"history": 1, "resources": 1}
        self.function_get.side_effect = self._function_get.get

    def test_status_without_resources(self):
        """test getting cluster status without resources"""
        self._function_get["resources"] = 0
        health_status = self.health_status.copy()
        del health_status["resources"]
        self.pcmk.cluster_status.return_value = health_status

        actions.status([])
        self.function_get.assert_has_calls([
            mock.call("resources"), mock.call("history")])
        self.function_set.assert_called_once_with(
            {"result": json.dumps(health_status)})

    def test_status_without_history(self):
        """test getting cluster status without history"""
        self._function_get["history"] = 0
        health_status = self.health_status.copy()
        del health_status["history"]
        self.pcmk.cluster_status.return_value = health_status

        actions.status([])
        self.function_get.assert_has_calls([
            mock.call("resources"), mock.call("history")])
        self.function_set.assert_called_once_with(
            {"result": json.dumps(health_status)})

    def test_status_with_history(self):
        """test getting cluster status with history"""
        health_status = self.health_status.copy()
        self.pcmk.cluster_status.return_value = health_status

        actions.status([])
        self.function_get.assert_has_calls([
            mock.call("resources"), mock.call("history")])
        self.function_set.assert_called_once_with(
            {"result": json.dumps(health_status)})

    def test_status_raise_error(self):
        self.pcmk.cluster_status.side_effect = subprocess.CalledProcessError(
            returncode=1, cmd=["crm", "status", "xml", "--inactive"])

        actions.status([])
        self.function_get.assert_has_calls([
            mock.call("resources"), mock.call("history")])
        self.function_set.assert_called_once_with({"result": "failure"})
        self.function_fail.assert_called_once_with(
            "failed to get cluster health")
