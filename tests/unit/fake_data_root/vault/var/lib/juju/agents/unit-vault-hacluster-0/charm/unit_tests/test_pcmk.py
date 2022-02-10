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
import pcmk
import os
import tempfile
import test_utils
import unittest
import xml.etree.ElementTree as etree
from distutils.version import StrictVersion


CRM_CONFIGURE_SHOW_XML = '''<?xml version="1.0" ?>
<cib num_updates="1" dc-uuid="1002" update-origin="juju-34fde5-0" crm_feature_set="3.0.7" validate-with="pacemaker-1.2" update-client="cibadmin" epoch="1103" admin_epoch="0" cib-last-written="Fri Aug  4 13:45:06 2017" have-quorum="1">
  <configuration>
    <crm_config>
      <cluster_property_set id="cib-bootstrap-options">
        <nvpair id="cib-bootstrap-options-dc-version" name="dc-version" value="1.1.10-42f2063"/>
        <nvpair id="cib-bootstrap-options-cluster-infrastructure" name="cluster-infrastructure" value="corosync"/>
        <nvpair name="no-quorum-policy" value="stop" id="cib-bootstrap-options-no-quorum-policy"/>
        <nvpair name="stonith-enabled" value="false" id="cib-bootstrap-options-stonith-enabled"/>
      </cluster_property_set>
    </crm_config>
    <nodes>
      <node id="1002" uname="juju-34fde5-0"/>
    </nodes>
    <resources/>
    <constraints/>
    <rsc_defaults>
      <meta_attributes id="rsc-options">
        <nvpair name="resource-stickiness" value="100" id="rsc-options-resource-stickiness"/>
      </meta_attributes>
    </rsc_defaults>
  </configuration>
</cib>

'''  # noqa

CRM_CONFIGURE_SHOW_XML_MAINT_MODE_TRUE = '''<?xml version="1.0" ?>
<cib num_updates="1" dc-uuid="1002" update-origin="juju-34fde5-0" crm_feature_set="3.0.7" validate-with="pacemaker-1.2" update-client="cibadmin" epoch="1103" admin_epoch="0" cib-last-written="Fri Aug  4 13:45:06 2017" have-quorum="1">
  <configuration>
    <crm_config>
      <cluster_property_set id="cib-bootstrap-options">
        <nvpair id="cib-bootstrap-options-dc-version" name="dc-version" value="1.1.10-42f2063"/>
        <nvpair id="cib-bootstrap-options-cluster-infrastructure" name="cluster-infrastructure" value="corosync"/>
        <nvpair name="no-quorum-policy" value="stop" id="cib-bootstrap-options-no-quorum-policy"/>
        <nvpair name="stonith-enabled" value="false" id="cib-bootstrap-options-stonith-enabled"/>
        <nvpair name="maintenance-mode" value="true" id="cib-bootstrap-options-maintenance-mode"/>
      </cluster_property_set>
    </crm_config>
    <nodes>
      <node id="1002" uname="juju-34fde5-0"/>
    </nodes>
    <resources/>
    <constraints/>
    <rsc_defaults>
      <meta_attributes id="rsc-options">
        <nvpair name="resource-stickiness" value="100" id="rsc-options-resource-stickiness"/>
      </meta_attributes>
    </rsc_defaults>
  </configuration>
</cib>

'''  # noqa

CRM_NODE_STATUS_XML = b'''
<nodes>
  <node id="1000" uname="juju-982848-zaza-ce47c58f6c88-10"/>
  <node id="1001" uname="juju-982848-zaza-ce47c58f6c88-9"/>
  <node id="1002" uname="juju-982848-zaza-ce47c58f6c88-11"/>
</nodes>
'''

CRM_STATUS_XML = b"""
<pacemaker-result api-version="2.0" request="crm_mon --output-as=xml --inactive">
  <summary>
    <stack type="corosync"/>
    <current_dc present="true" version="2.0.3-4b1f869f0f" name="juju-424dd5-3" id="1001" with_quorum="true"/>
    <last_update time="Tue Jan  5 09:55:10 2021"/>
    <last_change time="Tue Jan  5 09:05:49 2021" user="hacluster" client="crmd" origin="juju-424dd5-3"/>
    <nodes_configured number="4"/>
    <resources_configured number="5" disabled="0" blocked="0"/>
    <cluster_options stonith-enabled="false" symmetric-cluster="true" no-quorum-policy="stop" maintenance-mode="false"/>
  </summary>
  <nodes>
    <node name="juju-424dd5-3" id="1001" online="true" standby="false" standby_onfail="false" maintenance="false" pending="false" unclean="false" shutdown="false" expected_up="true" is_dc="true" resources_running="2" type="member"/>
    <node name="juju-424dd5-4" id="1000" online="true" standby="false" standby_onfail="false" maintenance="false" pending="false" unclean="false" shutdown="false" expected_up="true" is_dc="false" resources_running="1" type="member"/>
    <node name="juju-424dd5-5" id="1002" online="true" standby="false" standby_onfail="false" maintenance="false" pending="false" unclean="false" shutdown="false" expected_up="true" is_dc="false" resources_running="1" type="member"/>
    <node name="node1" id="1" online="false" standby="false" standby_onfail="false" maintenance="false" pending="false" unclean="false" shutdown="false" expected_up="false" is_dc="false" resources_running="0" type="member"/>
  </nodes>
  <resources>
    <group id="grp_ks_vips" number_resources="1">
      <resource id="res_ks_3cb88eb_vip" resource_agent="ocf::heartbeat:IPaddr2" role="Started" active="true" orphaned="false" blocked="false" managed="true" failed="false" failure_ignored="false" nodes_running_on="1">
        <node name="juju-424dd5-3" id="1001" cached="true"/>
      </resource>
    </group>
    <clone id="cl_ks_haproxy" multi_state="false" unique="false" managed="true" failed="false" failure_ignored="false">
      <resource id="res_ks_haproxy" resource_agent="lsb:haproxy" role="Started" active="true" orphaned="false" blocked="false" managed="true" failed="false" failure_ignored="false" nodes_running_on="1">
        <node name="juju-424dd5-3" id="1001" cached="true"/>
      </resource>
      <resource id="res_ks_haproxy" resource_agent="lsb:haproxy" role="Started" active="true" orphaned="false" blocked="false" managed="true" failed="false" failure_ignored="false" nodes_running_on="1">
        <node name="juju-424dd5-5" id="1002" cached="true"/>
      </resource>
      <resource id="res_ks_haproxy" resource_agent="lsb:haproxy" role="Started" active="true" orphaned="false" blocked="false" managed="true" failed="false" failure_ignored="false" nodes_running_on="1">
        <node name="juju-424dd5-4" id="1000" cached="true"/>
      </resource>
      <resource id="res_ks_haproxy" resource_agent="lsb:haproxy" role="Stopped" active="false" orphaned="false" blocked="false" managed="true" failed="false" failure_ignored="false" nodes_running_on="0"/>
    </clone>
  </resources>
  <node_history>
    <node name="juju-424dd5-3">
      <resource_history id="res_ks_3cb88eb_vip" orphan="false" migration-threshold="1000000">
        <operation_history call="10" task="start" last-rc-change="Tue Jan  5 09:03:52 2021" last-run="Tue Jan  5 09:03:52 2021" exec-time="57ms" queue-time="0ms" rc="0" rc_text="ok"/>
        <operation_history call="11" task="monitor" interval="10000ms" last-rc-change="Tue Jan  5 09:03:52 2021" exec-time="57ms" queue-time="1ms" rc="0" rc_text="ok"/>
      </resource_history>
      <resource_history id="res_ks_haproxy" orphan="false" migration-threshold="1000000">
        <operation_history call="36" task="probe" last-rc-change="Tue Jan  5 09:05:50 2021" last-run="Tue Jan  5 09:05:50 2021" exec-time="44ms" queue-time="0ms" rc="0" rc_text="ok"/>
        <operation_history call="36" task="probe" last-rc-change="Tue Jan  5 09:05:50 2021" last-run="Tue Jan  5 09:05:50 2021" exec-time="44ms" queue-time="0ms" rc="0" rc_text="ok"/>
        <operation_history call="37" task="monitor" interval="5000ms" last-rc-change="Tue Jan  5 09:05:50 2021" exec-time="43ms" queue-time="0ms" rc="0" rc_text="ok"/>
      </resource_history>
    </node>
    <node name="juju-424dd5-5">
      <resource_history id="res_ks_haproxy" orphan="false" migration-threshold="1000000">
        <operation_history call="10" task="probe" last-rc-change="Tue Jan  5 09:03:52 2021" last-run="Tue Jan  5 09:03:52 2021" exec-time="54ms" queue-time="0ms" rc="0" rc_text="ok"/>
        <operation_history call="10" task="probe" last-rc-change="Tue Jan  5 09:03:52 2021" last-run="Tue Jan  5 09:03:52 2021" exec-time="54ms" queue-time="0ms" rc="0" rc_text="ok"/>
        <operation_history call="11" task="monitor" interval="5000ms" last-rc-change="Tue Jan  5 09:03:52 2021" exec-time="49ms" queue-time="0ms" rc="0" rc_text="ok"/>
      </resource_history>
    </node>
    <node name="juju-424dd5-4">
      <resource_history id="res_ks_haproxy" orphan="false" migration-threshold="1000000">
        <operation_history call="10" task="probe" last-rc-change="Tue Jan  5 09:04:11 2021" last-run="Tue Jan  5 09:04:11 2021" exec-time="32ms" queue-time="0ms" rc="0" rc_text="ok"/>
        <operation_history call="10" task="probe" last-rc-change="Tue Jan  5 09:04:11 2021" last-run="Tue Jan  5 09:04:11 2021" exec-time="32ms" queue-time="0ms" rc="0" rc_text="ok"/>
        <operation_history call="11" task="monitor" interval="5000ms" last-rc-change="Tue Jan  5 09:04:11 2021" exec-time="27ms" queue-time="0ms" rc="0" rc_text="ok"/>
      </resource_history>
    </node>
  </node_history>
  <status code="0" message="OK"/>
</pacemaker-result>
"""  # noqa


class TestPcmk(unittest.TestCase):
    def setUp(self):
        self.tmpfile = tempfile.NamedTemporaryFile(delete=False)

    def tearDown(self):
        os.remove(self.tmpfile.name)

    @mock.patch('subprocess.getstatusoutput')
    def test_crm_res_running_true(self, getstatusoutput):
        getstatusoutput.return_value = (0, ("resource res_nova_consoleauth is "
                                            "running on: juju-xxx-machine-6"))
        self.assertTrue(pcmk.crm_res_running('res_nova_consoleauth'))

    @mock.patch('subprocess.getstatusoutput')
    def test_crm_res_running_stopped(self, getstatusoutput):
        getstatusoutput.return_value = (0, ("resource res_nova_consoleauth is "
                                            "NOT running"))
        self.assertFalse(pcmk.crm_res_running('res_nova_consoleauth'))

    @mock.patch('subprocess.getstatusoutput')
    def test_crm_res_running_undefined(self, getstatusoutput):
        getstatusoutput.return_value = (1, "foobar")
        self.assertFalse(pcmk.crm_res_running('res_nova_consoleauth'))

    @mock.patch('subprocess.getstatusoutput')
    def test_crm_res_running_on_node(self, getstatusoutput):
        _resource = "res_nova_consoleauth"
        _this_node = "node1"
        _another_node = "node5"

        # Not running
        getstatusoutput.return_value = (1, "foobar")
        self.assertFalse(
            pcmk.crm_res_running_on_node(_resource, _this_node))

        # Running active/passive on some other node
        getstatusoutput.return_value = (
            0, "resource {} is running: {}".format(_resource, _another_node))
        self.assertTrue(
            pcmk.crm_res_running_on_node('res_nova_consoleauth', _this_node))

        # Running active/passive on this node
        getstatusoutput.return_value = (
            0, "resource {} is running: {}".format(_resource, _this_node))
        self.assertTrue(
            pcmk.crm_res_running_on_node('res_nova_consoleauth', _this_node))

        # Running on some but not this node
        getstatusoutput.return_value = (
            0, ("resource {} is running: {}\nresource {} is NOT running"
                .format(_resource, _another_node, _resource)))
        self.assertFalse(
            pcmk.crm_res_running_on_node('res_nova_consoleauth', _this_node))

        # Running on this node and not others
        getstatusoutput.return_value = (
            0, ("resource {} is running: {}\nresource {} is NOT running"
                .format(_resource, _this_node, _resource)))
        self.assertTrue(
            pcmk.crm_res_running_on_node('res_nova_consoleauth', _this_node))

        # Running on more than one and this node
        getstatusoutput.return_value = (
            0, ("resource {} is running: {}\nresource {} is running: {}"
                .format(_resource, _another_node, _resource, _this_node)))
        self.assertTrue(
            pcmk.crm_res_running_on_node('res_nova_consoleauth', _this_node))

    @mock.patch('socket.gethostname')
    @mock.patch('subprocess.getstatusoutput')
    def test_wait_for_pcmk(self, getstatusoutput, gethostname):
        # Pacemaker is down
        gethostname.return_value = 'hanode-1'
        getstatusoutput.return_value = (1, 'Not the hostname')
        with self.assertRaises(pcmk.ServicesNotUp):
            pcmk.wait_for_pcmk(retries=2, sleep=0)

        # Pacemaker is up
        gethostname.return_value = 'hanode-1'
        getstatusoutput.return_value = (0, 'Hosname: hanode-1')
        # Here we are asserting that it doesn't raise anything:
        pcmk.wait_for_pcmk(retries=2, sleep=0)

    @mock.patch('subprocess.check_output')
    def test_crm_version(self, mock_check_output):
        # xenial
        mock_check_output.return_value = "crm 2.2.0\n"
        ret = pcmk.crm_version()
        self.assertEqual(StrictVersion('2.2.0'), ret)
        mock_check_output.assert_called_with(['crm', '--version'],
                                             universal_newlines=True)

        # trusty
        mock_check_output.mock_reset()
        mock_check_output.return_value = (
            "1.2.5 (Build f2f315daf6a5fd7ddea8e564cd289aa04218427d)\n")
        ret = pcmk.crm_version()
        self.assertEqual(StrictVersion('1.2.5'), ret)
        mock_check_output.assert_called_with(['crm', '--version'],
                                             universal_newlines=True)

    @mock.patch('subprocess.check_output')
    @mock.patch.object(pcmk, 'crm_version')
    def test_get_property(self, mock_crm_version, mock_check_output):
        mock_crm_version.return_value = StrictVersion('2.2.0')  # xenial
        mock_check_output.return_value = 'false\n'
        self.assertEqual('false\n', pcmk.get_property('maintenance-mode'))

        mock_check_output.assert_called_with(['crm', 'configure',
                                              'show-property',
                                              'maintenance-mode'],
                                             universal_newlines=True)

        mock_crm_version.return_value = StrictVersion('2.4.0')
        mock_check_output.reset_mock()
        self.assertEqual('false\n', pcmk.get_property('maintenance-mode'))
        mock_check_output.assert_called_with(['crm', 'configure',
                                              'get-property',
                                              'maintenance-mode'],
                                             universal_newlines=True)

    @mock.patch('subprocess.check_output')
    @mock.patch.object(pcmk, 'crm_version')
    def test_get_property_from_xml(self, mock_crm_version, mock_check_output):
        mock_crm_version.return_value = StrictVersion('1.2.5')  # trusty
        mock_check_output.return_value = CRM_CONFIGURE_SHOW_XML
        self.assertRaises(pcmk.PropertyNotFound, pcmk.get_property,
                          'maintenance-mode')

        mock_check_output.assert_called_with(['crm', 'configure',
                                              'show', 'xml'],
                                             universal_newlines=True)
        mock_check_output.reset_mock()
        mock_check_output.return_value = CRM_CONFIGURE_SHOW_XML_MAINT_MODE_TRUE
        self.assertEqual('true', pcmk.get_property('maintenance-mode'))

        mock_check_output.assert_called_with(['crm', 'configure',
                                              'show', 'xml'],
                                             universal_newlines=True)

    @mock.patch('subprocess.check_call')
    def test_set_property(self, mock_check_output):
        pcmk.set_property('maintenance-mode', 'false')
        mock_check_output.assert_called_with(['crm', 'configure', 'property',
                                              'maintenance-mode=false'],
                                             universal_newlines=True)

    @mock.patch.object(pcmk.unitdata, 'kv')
    @mock.patch('subprocess.call')
    def test_crm_update_resource(self, mock_call, mock_kv):
        db = test_utils.FakeKvStore()
        mock_kv.return_value = db
        db.set('res_test-IPaddr2', '')
        mock_call.return_value = 0

        with mock.patch.object(tempfile, "NamedTemporaryFile",
                               side_effect=lambda: self.tmpfile):
            pcmk.crm_update_resource('res_test', 'IPaddr2',
                                     ('params ip=1.2.3.4 '
                                      'cidr_netmask=255.255.0.0'))

        mock_call.assert_any_call(['crm', 'configure', 'load',
                                   'update', self.tmpfile.name])
        with open(self.tmpfile.name, 'rt') as f:
            self.assertEqual(f.read(),
                             ('primitive res_test IPaddr2 \\\n'
                              '\tparams ip=1.2.3.4 cidr_netmask=255.255.0.0'))

    @mock.patch.object(pcmk.unitdata, 'kv')
    @mock.patch('subprocess.call')
    def test_crm_update_resource_exists_in_kv(self, mock_call, mock_kv):
        db = test_utils.FakeKvStore()
        mock_kv.return_value = db
        db.set('res_test-IPaddr2', 'ef395293b1b7c29c5bf1c99774f75cf4')

        pcmk.crm_update_resource('res_test', 'IPaddr2',
                                 'params ip=1.2.3.4 cidr_netmask=255.0.0.0')

        mock_call.assert_called_once_with([
            'juju-log',
            "Resource res_test already defined and parameters haven't changed"
        ])

    @mock.patch.object(pcmk.unitdata, 'kv')
    @mock.patch('subprocess.call')
    def test_crm_update_resource_exists_in_kv_force_true(self, mock_call,
                                                         mock_kv):
        db = test_utils.FakeKvStore()
        mock_kv.return_value = db
        db.set('res_test-IPaddr2', 'ef395293b1b7c29c5bf1c99774f75cf4')

        with mock.patch.object(tempfile, "NamedTemporaryFile",
                               side_effect=lambda: self.tmpfile):
            pcmk.crm_update_resource('res_test', 'IPaddr2',
                                     ('params ip=1.2.3.4 '
                                      'cidr_netmask=255.0.0.0'),
                                     force=True)

        mock_call.assert_any_call(['crm', 'configure', 'load',
                                   'update', self.tmpfile.name])

    def test_resource_checksum(self):
        r = pcmk.resource_checksum('res_test', 'IPaddr2',
                                   'params ip=1.2.3.4 cidr_netmask=255.0.0.0')
        self.assertEqual(r, 'ef395293b1b7c29c5bf1c99774f75cf4')

    @mock.patch('subprocess.check_output', return_value=CRM_NODE_STATUS_XML)
    def test_list_nodes(self, mock_check_output):
        self.assertSequenceEqual(
            pcmk.list_nodes(),
            [
                'juju-982848-zaza-ce47c58f6c88-10',
                'juju-982848-zaza-ce47c58f6c88-11',
                'juju-982848-zaza-ce47c58f6c88-9'])
        mock_check_output.assert_called_once_with(['crm', 'node', 'status'])

    def test_get_tag(self):
        """Test get element by tag if exists else empty element."""
        main = etree.Element("test")
        main.append(etree.Element("child_1", {"id": "t1", "class": "test"}))
        main.append(etree.Element("child_2", {"id": "t2", "class": "test"}))

        assert pcmk.get_tag(main, "child_1").get("id") == "t1"
        assert pcmk.get_tag(main, "child_2").get("id") == "t2"
        assert pcmk.get_tag(main, "child_3").get("id") is None

    def test_add_key(self):
        """Test add new key to dictionary."""
        dict_1 = {"a": 1}
        self.assertDictEqual(pcmk.add_key(dict_1, "b", [1, 2, 3]),
                             {"a": 1, "b": [1, 2, 3]})

        dict_1 = {"a": 1, "b": 2}
        self.assertDictEqual(pcmk.add_key(dict_1, "b", [1, 2, 3]),
                             {"a": 1, "b": [1, 2, 3]})

    @mock.patch('subprocess.check_output')
    def test_crm_mon_version(self, mock_check_output):
        # trusty
        mock_check_output.return_value = "Pacemaker 1.1.10\n" \
                                         "Written by Andrew Beekhof"
        ret = pcmk.crm_mon_version()
        self.assertEqual(StrictVersion("1.1.10"), ret)
        mock_check_output.assert_called_with(["crm_mon", "--version"],
                                             universal_newlines=True)

        # focal
        mock_check_output.return_value = "Pacemaker 2.0.3\n" \
                                         "Written by Andrew Beekhof"
        ret = pcmk.crm_mon_version()
        self.assertEqual(StrictVersion("2.0.3"), ret)
        mock_check_output.assert_called_with(["crm_mon", "--version"],
                                             universal_newlines=True)

    @mock.patch("subprocess.check_output", return_value=CRM_STATUS_XML)
    @mock.patch.object(pcmk, "crm_mon_version")
    def test_cluster_status(self, mock_crm_mon_version, mock_check_output):
        """Test parse cluster status from `crm status xml`."""
        mock_crm_mon_version.return_value = StrictVersion("2.0.3")  # Focal
        status = pcmk.cluster_status(resources=True, history=True)
        with open("status.json", "w") as file:
            import json
            json.dump({"result": json.dumps(status)}, file)

        mock_check_output.assert_called_with(
            ["crm_mon", "--output-as=xml", "--inactive"])

        self.assertEqual(status["crm_mon_version"], "2.0.3")
        self.assertEqual(status["summary"]["last_update"]["time"],
                         "Tue Jan  5 09:55:10 2021")
        self.assertEqual(status["summary"]["nodes_configured"]["number"], "4")
        self.assertListEqual(
            sorted(status["nodes"].keys()),
            sorted(["node1", "juju-424dd5-3", "juju-424dd5-4",
                    "juju-424dd5-5"]))
        self.assertEqual(status["resources"]["groups"]["grp_ks_vips"][0]["id"],
                         "res_ks_3cb88eb_vip")
        self.assertDictEqual(
            status["resources"]["groups"]["grp_ks_vips"][0]["nodes"][0],
            {"name": "juju-424dd5-3", "id": "1001", "cached": "true"})

        self.assertEqual(
            status["resources"]["clones"]["cl_ks_haproxy"]["resources"][0]
            ["id"],
            "res_ks_haproxy")
        self.assertDictEqual(
            status["resources"]["clones"]["cl_ks_haproxy"]["resources"][0]
            ["nodes"][0],
            {"name": "juju-424dd5-3", "id": "1001", "cached": "true"})
        self.assertEqual(
            status["history"]["juju-424dd5-3"]["res_ks_haproxy"][0]["call"],
            "36"
        )
        self.assertEqual(
            status["history"]["juju-424dd5-4"]["res_ks_haproxy"][2]["call"],
            "11"
        )
        self.assertEqual(
            status["history"]["juju-424dd5-4"]["res_ks_haproxy"][2]
            ["last-rc-change"],
            "Tue Jan  5 09:04:11 2021"
        )

    def test_parse_version(self):
        """Test parse version from cmd output."""
        for cmd_output, exp_version in [
            ("Pacemaker 1.1.10", StrictVersion("1.1.10")),
            ("Test 2.2.2\nnewline\nnewline", StrictVersion("2.2.2")),
            ("2.2.2", StrictVersion("2.2.2"))
        ]:
            self.assertEqual(pcmk.parse_version(cmd_output), exp_version)

        with self.assertRaises(ValueError):
            pcmk.parse_version("test 1.1")

        with self.assertRaises(ValueError):
            pcmk.parse_version("test 1.a.1")

        with self.assertRaises(ValueError):
            pcmk.parse_version("output failed")
