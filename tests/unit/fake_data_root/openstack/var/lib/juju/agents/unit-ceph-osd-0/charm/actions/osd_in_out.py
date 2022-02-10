#!/usr/bin/env python3
#
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

# osd_out/osd_in actions file.

import os
import sys

from subprocess import check_output, STDOUT

sys.path.append('lib')
sys.path.append('hooks')

from charmhelpers.core.hookenv import (
    function_fail,
    function_set,
    log,
    ERROR,
)

from charms_ceph.utils import get_local_osd_ids
from ceph_hooks import assess_status
from utils import parse_osds_arguments, ALL

IN = "in"
OUT = "out"


def check_osd_id(osds):
    """Check ceph OSDs existence.

    :param osds: list of osds IDs
    :type osds: set
    :returns: list of osds IDs present on the local machine and
              list of failed osds IDs
    :rtype: Tuple[set, set]
    :raises OSError: if the unit can't get the local osd ids
    """
    all_local_osd = get_local_osd_ids()
    if ALL in osds:
        return set(all_local_osd), set()

    failed_osds = osds.difference(all_local_osd)
    if failed_osds:
        log("Ceph OSDs not present: {}".format(", ".join(failed_osds)),
            level=ERROR)

    return osds, failed_osds


def ceph_osd_upgrade(action, osd_id):
    """Execute ceph osd-upgrade command.

    :param action: action type IN/OUT
    :type action: str
    :param osd_id: osd ID
    :type osd_id: str
    :returns: output message
    :rtype: str
    :raises subprocess.CalledProcessError: if the ceph commands fails
    """
    cmd = ["ceph", "--id", "osd-upgrade", "osd", action, osd_id]
    output = check_output(cmd, stderr=STDOUT).decode("utf-8")

    log("ceph-osd {osd_id} was updated by the action osd-{action} with "
        "output: {output}".format(osd_id=osd_id, action=action, output=output))

    return output


def osd_in_out(action):
    """Pause/Resume the ceph OSDs unit ont the local machine only.

    :param action: Either IN or OUT (see global constants)
    :type action: string
    :raises RuntimeError: if a supported action is not used
    :raises subprocess.CalledProcessError: if the ceph commands fails
    :raises OSError: if the unit can't get the local osd ids
    """
    if action not in (IN, OUT):
        raise RuntimeError("Unknown action \"{}\"".format(action))

    osds = parse_osds_arguments()
    osds, failed_osds = check_osd_id(osds)

    if failed_osds:
        function_fail("invalid ceph OSD device id: "
                      "{}".format(",".join(failed_osds)))
        return

    outputs = []
    for osd_id in osds:
        output = ceph_osd_upgrade(action, str(osd_id))
        outputs.append(output)

    function_set({
        "message": "osd-{action} action was successfully executed for ceph "
                   "OSD devices [{osds}]".format(action=action,
                                                 osds=",".join(osds)),
        "outputs": os.linesep.join(outputs)
    })

    assess_status()


def osd_in():
    """Shortcut to execute 'osd_in' action"""
    osd_in_out(IN)


def osd_out():
    """Shortcut to execute 'osd_out' action"""
    osd_in_out(OUT)


# A dictionary of all the defined actions to callables (which take
# parsed arguments).
ACTIONS = {"osd-out": osd_out, "osd-in": osd_in}


def main(args):
    action_name = os.path.basename(args[0])
    try:
        action = ACTIONS[action_name]
    except KeyError:
        s = "Action {} undefined".format(action_name)
        function_fail(s)
        return s
    else:
        try:
            action()
        except Exception as e:
            function_fail("Action {} failed: {}".format(action_name, str(e)))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
