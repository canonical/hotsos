#! /usr/bin/python3
#
# Copyright 2019 Canonical Ltd
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

import aiohttp
import functools
import os
import subprocess
import sys
import time
import xml.etree.ElementTree as ET

import maas.client

DESCRIPTION = "Maas stonith plugin"
DESCRIPTION_LONG = "External Maas stonith plugin"

DEV_URL = "https://maas.io/"
PARAM_XML = """<parameters>

<parameter name="hostnames" unique="1">
<content type="string" />
<shortdesc lang="en">
Profile
</shortdesc>
<longdesc lang="en">
Space seperate list of hosts this stonith resource will manage
</longdesc>
</parameter>

<parameter name="url" unique="1">
<content type="string" />
<shortdesc lang="en">
Maas URL
</shortdesc>
<longdesc lang="en">
Maas API URL
</longdesc>
</parameter>

<parameter name="apikey" unique="1">
<content type="string" />
<shortdesc lang="en">
API Key
</shortdesc>
<longdesc lang="en">
Maas API key
</longdesc>
</parameter>

</parameters>"""

INFO = "info"
DEBUG = "debug"
CRIT = "crit"


class FindMachineException(Exception):
    """Exception raised when machine lookup fails

    :param count: Number of machines matching the hostname.
    :type count: int
    """
    def __init__(self, count):
        self.message = "Expected to find 1 machine found {}".format(count)
        log(self.message, CRIT)


class MachinePowerException(Exception):
    """Exception raised when machine fails to reach power state.

    :param state: Power state machine was transitioning to.
    :type state: str
    """

    def __init__(self, state):
        self.message = "Machine timed out reaching {} state".format(state)
        log(self.message, CRIT)


def get_config_names():
    """Derive the available configuration options

    :returns: Config options and their values
    :rtype: dict
    """
    root = ET.fromstring(PARAM_XML)
    config_names = []
    for child in root:
        if child.tag == 'parameter':
            config_names.append(child.attrib['name'])
    return config_names


def log(msg, level=None):
    """Log messages

    :param msg: Message to log
    :type msg: str
    :param level: Log level (crit, err, warn, notice, info or debug)
    :type auth_token: str
    """
    level = level or 'debug'
    subprocess.call(['ha_log.sh', level, msg])
    with open('/tmp/maas.log', 'a') as f:
        f.write('{} {}\n'.format(level, msg))


def get_maas_client(maas_url, auth_token):
    """Return a maas client

    :param maas_url: URL of maas api
    :type maas_url: str
    :param auth_token: Maas API key
    :type auth_token: str
    :returns: Maas client
    :rtype: maas.client.facade.Client
    """
    log("Creating maas client", DEBUG)
    return maas.client.connect(
        url=maas_url,
        apikey=auth_token)


def get_machine(client, hostname):
    """Return the machine corresponding to hostname.

    :param client: Maas client
    :type client: maas.client.facade.Client
    :param hostname: Name of hostname to lookup.
    :type hostname: str
    :returns: Maas machine
    :rtype: origin.Machine
    """
    log("Creating maas client", DEBUG)
    log("Getting machine with hostname {} from maas ".format(hostname), DEBUG)
    machines = client.machines.list(hostnames=[hostname])
    if len(machines) != 1:
        raise FindMachineException(len(machines))
    log("Found machine {} ({})".format(hostname, machines[0].system_id), DEBUG)
    return machines[0]


def wait_for_power_state(client, hostname, state):
    """Wait for machine power to reach given state.

    :param client: Maas client
    :type client: maas.client.facade.Client
    :param hostname: Name of hostname to lookup.
    :type hostname: str
    :param state: Target power state
    :type state: maas.client.enum.PowerState
    :raises: MachinePowerException
    """
    log("Waiting for {} to reach power state {}".format(hostname, state.value),
        DEBUG)
    for i in range(0, 20):
        machine = get_machine(client, hostname)
        if machine.power_state == state:
            log("{} reached {}".format(hostname, state.value), DEBUG)
            break
        time.sleep(0.5)
    else:
        raise MachinePowerException(state.value)
    log("{} is in power state {}".format(hostname, machine.power_state.value),
        INFO)


def power_on(maas_url, auth_token, hostname):
    """Power on given machine

    :param maas_url: URL of maas api
    :type maas_url: str
    :param auth_token: Maas API key
    :type auth_token: str
    :param hostname: Name of hostname to lookup.
    :type hostname: str
    :returns: Success indicator
    :rtype: int
    """
    log("Powering on {}".format(hostname), INFO)
    client = get_maas_client(maas_url, auth_token)
    machine = get_machine(client, hostname)
    machine.power_on()
    return 0


def power_off(maas_url, auth_token, hostname):
    """Power off given machine

    :param maas_url: URL of maas api
    :type maas_url: str
    :param auth_token: Maas API key
    :type auth_token: str
    :param hostname: Name of hostname to lookup.
    :type hostname: str
    :returns: Success indicator
    :rtype: int
    """
    log("Powering off {}".format(hostname), INFO)
    client = get_maas_client(maas_url, auth_token)
    machine = get_machine(client, hostname)
    machine.power_off()
    return 0


def power_reset(maas_url, auth_token, hostname):
    """Reset power on given machine

    :param maas_url: URL of maas api
    :type maas_url: str
    :param auth_token: Maas API key
    :type auth_token: str
    :param hostname: Name of hostname to lookup.
    :type hostname: str
    :returns: Success indicator
    :rtype: int
    """
    log("Performing power reset on {}".format(hostname), INFO)
    client = get_maas_client(maas_url, auth_token)
    machine = get_machine(client, hostname)
    log("{} is in power state {}".format(hostname, machine.power_state.value),
        INFO)
    if machine.power_state != maas.client.enum.PowerState.OFF:
        log("Powering off {}".format(hostname), INFO)
        machine.power_off()
    else:
        log("Skipping power off of {} it is already off".format(hostname),
            INFO)
    wait_for_power_state(client, hostname, maas.client.enum.PowerState.OFF)
    log("Powering on {}".format(hostname), INFO)
    machine.power_on()
    return 0


def status(maas_url, auth_token):
    """Test connectivity to maas api

    :param maas_url: URL of maas api
    :type maas_url: str
    :param auth_token: Maas API key
    :type auth_token: str
    :returns: Success indicator
    :rtype: int
    """
    log("Checking status of Maas", INFO)
    try:
        client = get_maas_client(maas_url, auth_token)
        client.version.get()
    except aiohttp.client_exceptions.ClientConnectorError:
        return 1
    return 0


def get_environment_config():
    """Extract config from environment variables

    :returns: Dictionary of config
    :rtype: dict
    """
    runtime_config = {}
    for k in get_config_names():
        runtime_config[k] = os.environ.get(k)
    return runtime_config


def show_hosts():
    """Print hosts supported by this stonith instance.

    :returns: Success indicator
    :rtype: int
    """
    for host in get_environment_config().get('hostnames').split():
        print(host)
    return 0


def show_config_names():
    """Print name of config options picked up from environment variables

    :returns: Success indicator
    :rtype: int
    """
    print(' '.join(get_config_names()))
    return 0


def show_info_devid():
    """Print name of config options picked up from environment variables

    :returns: Success indicator
    :rtype: int
    """
    print(DESCRIPTION)
    return 0


def show_info_devname():
    """Print description of this stonith method

    :returns: Success indicator
    :rtype: int
    """
    print(DESCRIPTION_LONG)
    return 0


def show_info_devdescr():
    """Print description of this stonith method

    :returns: Success indicator
    :rtype: int
    """
    print(DESCRIPTION_LONG)
    return 0


def show_info_devurl():
    """Print URL for dev community

    :returns: Success indicator
    :rtype: int
    """
    print(DEV_URL)
    return 0


def show_info_xml():
    """Print XML describing config options

    :returns: Success indicator
    :rtype: int
    """
    print(PARAM_XML)
    return 0


def map_commands(args):
    config = get_environment_config()
    maas_url = config['url']
    auth_token = config['apikey']
    cmd = args[1]
    try:
        hostname = args[2]
    except IndexError:
        hostname = config.get('hostname')
    commands = {
        'on': functools.partial(power_on, maas_url, auth_token, hostname),
        'off': functools.partial(power_off, maas_url, auth_token, hostname),
        'reset': functools.partial(power_reset, maas_url, auth_token,
                                   hostname),
        'status': functools.partial(status, maas_url, auth_token),
        'gethosts': show_hosts,
        'getconfignames': show_config_names,
        'getinfo-devid': show_info_devid,
        'getinfo-devname': show_info_devname,
        'getinfo-devdescr': show_info_devdescr,
        'getinfo-devurl': show_info_devurl,
        'getinfo-xml': show_info_xml}
    try:
        rc = commands[cmd]()
    except (FindMachineException, MachinePowerException):
        rc = 1
    return rc


if __name__ == '__main__':
    sys.exit(map_commands(sys.argv))
