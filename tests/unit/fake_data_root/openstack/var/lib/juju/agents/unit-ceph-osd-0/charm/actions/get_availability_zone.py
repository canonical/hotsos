#!/usr/bin/env python3
#
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
import sys

from tabulate import tabulate

sys.path.append("hooks")
sys.path.append("lib")

from charms_ceph.utils import get_osd_tree
from charmhelpers.core import hookenv
from utils import get_unit_hostname


CRUSH_MAP_HIERARCHY = [
    "root",  # 10
    "region",  # 9
    "datacenter",  # 8
    "room",  # 7
    "pod",  # 6
    "pdu",  # 5
    "row",  # 4
    "rack",  # 3
    "chassis",  # 2
    "host",  # 1
    "osd",  # 0
]


def _get_human_readable(availability_zones):
    """Get human readable table format.

    :param availability_zones: information about the availability zone
    :type availability_zones: Dict[str, Dict[str, str]]
    :returns: formatted data as table
    :rtype: str
    """
    data = availability_zones.get(
        "all-units", {get_unit_hostname(): availability_zones["unit"]}
    )
    data = [[unit, *crush_map.values()] for unit, crush_map in data.items()]
    return tabulate(
        data, tablefmt="grid", headers=["unit", *CRUSH_MAP_HIERARCHY]
    )


def _get_crush_map(crush_location):
    """Get Crush Map hierarchy from CrushLocation.

    :param crush_location: CrushLocation from function get_osd_tree
    :type crush_location: charms_ceph.utils.CrushLocation
    :returns: dictionary contains the Crush Map hierarchy, where
              the keys are according to the defined types of the
              Ceph Map Hierarchy
    :rtype: Dict[str, str]
    """
    return {
        crush_map_type: getattr(crush_location, crush_map_type)
        for crush_map_type in CRUSH_MAP_HIERARCHY
        if getattr(crush_location, crush_map_type, None)
    }


def get_availability_zones(show_all=False):
    """Get information about the availability zones.

    Returns dictionary contains the unit as the current unit and other_units
    (if the action was executed with the parameter show-all) that provide
    information about other units.

    :param show_all: define whether the result should contain AZ information
                     for all units
    :type show_all: bool
    :returns: {"unit": <current-unit-AZ>,
               "all-units": {<unit-hostname>: <unit-AZ>}}
    :rtype: Dict[str, Dict[str, str]]
    """
    results = {"unit": {}, "all-units": {}}
    osd_tree = get_osd_tree(service="osd-upgrade")

    this_unit_host = get_unit_hostname()
    for crush_location in osd_tree:
        crush_map = _get_crush_map(crush_location)
        if this_unit_host == crush_location.name:
            results["unit"] = crush_map

        results["all-units"][crush_location.name] = crush_map

    if not show_all:
        results.pop("all-units")

    return results


def format_availability_zones(availability_zones, human_readable=True):
    """Format availability zones to action output format."""
    if human_readable:
        return _get_human_readable(availability_zones)

    return json.dumps(availability_zones)


def main():
    try:
        show_all = hookenv.action_get("show-all")
        human_readable = hookenv.action_get("format") == "text"
        availability_zones = get_availability_zones(show_all)
        if not availability_zones["unit"]:
            hookenv.log(
                "Availability zone information for current unit not found.",
                hookenv.DEBUG
            )

        formatted_azs = format_availability_zones(availability_zones,
                                                  human_readable)
        hookenv.action_set({"availability-zone": formatted_azs})
    except Exception as error:
        hookenv.action_fail("Action failed: {}".format(str(error)))


if __name__ == "__main__":
    main()
