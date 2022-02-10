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

import configparser
import socket

from keystoneauth1 import loading, session
from novaclient import client as nova_client_

from charmhelpers.core.hookenv import (
    log,
    DEBUG,
    WARNING
)


def _nova_cfg():
    """
    Parse nova config and return it in form of ConfigParser instance
    :return: Parsed nova config
    :rtype: configparser.ConfigParser
    """
    nova_cfg = configparser.ConfigParser()
    nova_cfg.read('/etc/nova/nova.conf')
    return nova_cfg


def _os_credentials():
    """
    Returns Openstack credentials that Openstack clients can use to
    authenticate with keystone.

    :return: Openstack credentials
    :rtype: dict
    """
    nova_cfg = _nova_cfg()
    auth_section = 'keystone_authtoken'
    auth_details = [
        'username',
        'password',
        'auth_url',
        'project_name',
        'project_domain_name',
        'user_domain_name',
    ]
    return {attr: nova_cfg.get(auth_section, attr) for attr in auth_details}


def service_hostname():
    """Returns hostname used to identify this host within openstack."""
    nova_cfg = _nova_cfg()
    # This follows same logic as in nova, If 'host' is not defined in the
    # config, use system's hostname
    return nova_cfg['DEFAULT'].get('host', socket.gethostname())


def nova_client():
    """
    Creates and authenticates new nova client.

    :return: Authenticated nova client
    :rtype: novaclient.v2.client.Client
    """
    log('Initiating nova client', DEBUG)
    loader = loading.get_plugin_loader('password')
    credentials = _os_credentials()
    log('Authenticating with Keystone '
        'at "{}"'.format(credentials['auth_url']), DEBUG)
    auth = loader.load_from_options(**credentials)
    session_ = session.Session(auth=auth)
    return nova_client_.Client('2', session=session_)


def nova_service_id(nc_client):
    """
    Returns ID of nova-compute service running on this unit.

    :param nc_client: Authenticated nova client
    :type nc_client: novaclient.v2.client.Client
    :return: nova-compute ID
    :rtype: str
    """
    hostname = service_hostname()
    service = nc_client.services.list(host=hostname, binary='nova-compute')
    if len(service) == 0:
        raise RuntimeError('Host "{}" is not registered in nova service list')
    elif len(service) > 1:
        log('Host "{}" has more than 1 nova-compute service registered. '
            'Selecting one ID randomly.'.format(hostname), WARNING)
    return service[0].id


def running_vms(nc_client):
    """
    Returns number of VMs managed by the nova-compute service on this unit.

    :param nc_client: Authenticated nova client
    :type nc_client: novaclient.v2.client.Client
    :return: Number of running VMs
    :rtype: int
    """
    # NOTE(martin-kalcok): Hypervisor list always uses host's fqdn for
    # 'hypervisor_hostname', even if config variable 'host' is set in
    # the nova.conf
    hostname = socket.getfqdn()
    # NOTE(martin-kalcok): After the support for trusty (and by extension
    # mitaka) is dropped, `hypervisors.list()` can be changed to
    # `hypervisors.search(hostname, detailed=True) to improve performance.
    for server in nc_client.hypervisors.list():
        if server.hypervisor_hostname == hostname:
            log("VMs running on hypervisor '{}':"
                " {}".format(hostname, server.running_vms), DEBUG)
            return server.running_vms
    else:
        raise RuntimeError("Nova compute node '{}' not found in the list of "
                           "hypervisors. Is the unit already removed from the"
                           " cloud?".format(hostname))
