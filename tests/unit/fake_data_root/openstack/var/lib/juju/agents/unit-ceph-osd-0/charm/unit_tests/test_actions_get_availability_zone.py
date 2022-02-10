# Copyright 2021 Canonical Ltd
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

from actions import get_availability_zone
from lib.charms_ceph.utils import CrushLocation

from test_utils import CharmTestCase


TABULATE_OUTPUT = """
+-------------+---------+-------------+
| unit        | root    | region      |
+=============+=========+=============+
| juju-ceph-0 | default | juju-ceph-0 |
+-------------+---------+-------------+
| juju-ceph-1 | default | juju-ceph-1 |
+-------------+---------+-------------+
| juju-ceph-2 | default | juju-ceph-2 |
+-------------+---------+-------------+
"""

AVAILABILITY_ZONES = {
    "unit": {"root": "default", "host": "juju-ceph-0"},
    "all-units": {
        "juju-ceph-0": {"root": "default", "host": "juju-ceph-0"},
        "juju-ceph-1": {"root": "default", "host": "juju-ceph-1"},
        "juju-ceph-2": {"root": "default", "host": "juju-ceph-2"}
    }
}


class GetAvailabilityZoneActionTests(CharmTestCase):
    def setUp(self):
        super(GetAvailabilityZoneActionTests, self).setUp(
            get_availability_zone,
            ["get_osd_tree", "get_unit_hostname", "tabulate"]
        )
        self.tabulate.return_value = TABULATE_OUTPUT
        self.get_unit_hostname.return_value = "juju-ceph-0"

    def test_get_human_readable(self):
        """Test formatting as human readable."""
        table = get_availability_zone._get_human_readable(AVAILABILITY_ZONES)
        self.assertTrue(table == TABULATE_OUTPUT)

    def test_get_crush_map(self):
        """Test get Crush Map hierarchy from CrushLocation."""
        crush_location = CrushLocation(
            name="test", identifier="t1", host="test", rack=None, row=None,
            datacenter=None, chassis=None, root="default")
        crush_map = get_availability_zone._get_crush_map(crush_location)
        self.assertDictEqual(crush_map, {"root": "default", "host": "test"})

        crush_location = CrushLocation(
            name="test", identifier="t1", host="test", rack="AZ",
            row="customAZ", datacenter=None, chassis=None, root="default")
        crush_map = get_availability_zone._get_crush_map(crush_location)
        self.assertDictEqual(crush_map, {"root": "default", "row": "customAZ",
                                         "rack": "AZ", "host": "test"})

    def test_get_availability_zones(self):
        """Test function to get information about availability zones."""
        self.get_unit_hostname.return_value = "test_1"
        self.get_osd_tree.return_value = [
            CrushLocation(name="test_1", identifier="t1", host="test_1",
                          rack="AZ1", row="AZ", datacenter=None,
                          chassis=None, root="default"),
            CrushLocation(name="test_2", identifier="t2", host="test_2",
                          rack="AZ1", row="AZ", datacenter=None,
                          chassis=None, root="default"),
            CrushLocation(name="test_3", identifier="t3", host="test_3",
                          rack="AZ2", row="AZ", datacenter=None,
                          chassis=None, root="default"),
            CrushLocation(name="test_4", identifier="t4", host="test_4",
                          rack="AZ2", row="AZ", datacenter=None,
                          chassis=None, root="default"),
        ]
        results = get_availability_zone.get_availability_zones()

        self.assertDictEqual(results, {
            "unit": dict(root="default", row="AZ", rack="AZ1", host="test_1")})

        results = get_availability_zone.get_availability_zones(show_all=True)
        self.assertDictEqual(results, {
            "unit": dict(root="default", row="AZ", rack="AZ1", host="test_1"),
            "all-units": {
                "test_1": dict(root="default", row="AZ", rack="AZ1",
                               host="test_1"),
                "test_2": dict(root="default", row="AZ", rack="AZ1",
                               host="test_2"),
                "test_3": dict(root="default", row="AZ", rack="AZ2",
                               host="test_3"),
                "test_4": dict(root="default", row="AZ", rack="AZ2",
                               host="test_4"),
            }})

    def test_format_availability_zones(self):
        """Test function to formatted availability zones."""
        # human readable format
        results_table = get_availability_zone.format_availability_zones(
            AVAILABILITY_ZONES, True)
        self.assertEqual(results_table, TABULATE_OUTPUT)

        # json format
        results_json = get_availability_zone.format_availability_zones(
            AVAILABILITY_ZONES, False)
        self.assertDictEqual(json.loads(results_json), AVAILABILITY_ZONES)
