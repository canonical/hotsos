#!/usr/bin/env python3
#
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


import os
import sys
import shutil
import subprocess


sys.path.append('lib')
sys.path.append('hooks')

from charmhelpers.core.hookenv import (
    function_fail,
    log,
)
from ceph_hooks import assess_status
from utils import parse_osds_arguments, ALL

START = 'start'
STOP = 'stop'


def systemctl_execute(action, services):
    """
    Execute `systemctl` action on specified services.

    Action can be either 'start' or 'stop' (defined by global constants
    START, STOP). Parameter `services` is list of service names on which the
    action will be executed. If the parameter `services` contains constant
    ALL, the action will be executed on all ceph-osd services.

    :param action: Action to be executed (start or stop)
    :type action: str
    :param services: List of services to be targetd by the action
    :type services: list[str]
    :return: None
    """
    if ALL in services:
        cmd = ['systemctl', action, 'ceph-osd.target']
    else:
        cmd = ['systemctl', action] + services
    subprocess.check_call(cmd, timeout=300)


def osd_ids_to_service_names(osd_ids):
    """
    Transform set of OSD IDs into the list of respective service names.

    Example:
        >>> osd_ids_to_service_names({0,1})
        ['ceph-osd@0.service', 'ceph-osd@1.service']

    :param osd_ids: Set of service IDs to be converted
    :type osd_ids: set[str | int]
    :return: List of service names
    :rtype: list[str]
    """
    service_list = []
    for id_ in osd_ids:
        if id_ == ALL:
            service_list.append(ALL)
        else:
            service_list.append("ceph-osd@{}.service".format(id_))
    return service_list


def check_service_is_present(service_list):
    """
    Checks that every service, from the `service_list` parameter exists
    on the system. Raises RuntimeError if any service is missing.

    :param service_list: List of systemd services
    :type service_list: list[str]
    :raises RuntimeError: if any service is missing
    """
    if ALL in service_list:
        return

    service_list_cmd = ['systemctl', 'list-units', '--full',
                        '--all', '--no-pager', '-t', 'service']
    present_services = subprocess.run(service_list_cmd,
                                      stdout=subprocess.PIPE,
                                      timeout=30).stdout.decode('utf-8')

    missing_services = []
    for service_name in service_list:
        if service_name not in present_services:
            missing_services.append(service_name)

    if missing_services:
        raise RuntimeError('Some services are not present on this '
                           'unit: {}'.format(missing_services))


def execute_action(action):
    """Core implementation of the 'start'/'stop' actions

    :param action: Either START or STOP (see global constants)
    :return: None
    """
    if action not in (START, STOP):
        raise RuntimeError('Unknown action "{}"'.format(action))

    osds = parse_osds_arguments()
    services = osd_ids_to_service_names(osds)

    check_service_is_present(services)

    systemctl_execute(action, services)

    assess_status()


def stop():
    """Shortcut to execute 'stop' action"""
    execute_action(STOP)


def start():
    """Shortcut to execute 'start' action"""
    execute_action(START)


ACTIONS = {'stop': stop,
           'start': start,
           }


def main(args):
    action_name = os.path.basename(args.pop(0))
    try:
        action = ACTIONS[action_name]
    except KeyError:
        s = "Action {} undefined".format(action_name)
        function_fail(s)
        return
    else:
        try:
            log("Running action '{}'.".format(action_name))
            if shutil.which('systemctl') is None:
                raise RuntimeError("This action requires systemd")
            action()
        except Exception as e:
            function_fail("Action '{}' failed: {}".format(action_name, str(e)))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
