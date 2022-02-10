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

import base64
import os

from charmhelpers.contrib.ssl.service import ServiceCA

from charmhelpers.core.hookenv import (
    INFO,
    config,
    relation_ids,
    relation_set,
    relation_get,
    local_unit,
    log,
)
from charmhelpers.contrib.network.ip import (
    get_hostname,
    get_relation_ip,
)
import charmhelpers.contrib.openstack.cert_utils as ch_cert_utils
import charmhelpers.contrib.openstack.deferred_events as deferred_events

import rabbit_net_utils

CERTS_FROM_RELATION = 'certs-relation'


def get_unit_amqp_endpoint_data():
    """Get the hostname and ip address associated with amqp interface.

    :returns: Tuple containing ip address and hostname.
    :rtype: (str, str)
    """
    ip = get_relation_ip(
        rabbit_net_utils.AMQP_INTERFACE,
        cidr_network=config(rabbit_net_utils.AMQP_OVERRIDE_CONFIG))
    return ip, get_hostname(ip)


def get_relation_cert_data():
    """Get certificate bundle associated with the amqp interface.

    :returns: Dict with key, cert, ca and, optional, chain keys.
    :rtype: Dict
    """
    _, hostname = get_unit_amqp_endpoint_data()
    return ch_cert_utils.get_bundle_for_cn(hostname)


def get_ssl_mode():
    relation_certs = get_relation_cert_data()
    if relation_certs:
        ssl_mode = CERTS_FROM_RELATION
        external_ca = True
    else:
        ssl_mode = config('ssl')
        external_ca = False

        # Legacy config boolean option
        ssl_on = config('ssl_enabled')
        if ssl_mode == 'off' and ssl_on is False:
            ssl_mode = 'off'
        elif ssl_mode == 'off' and ssl_on:
            ssl_mode = 'on'

        ssl_key = config('ssl_key')
        ssl_cert = config('ssl_cert')

        if all((ssl_key, ssl_cert)):
            external_ca = True
    return ssl_mode, external_ca


def b64encoded_string(ss):
    return base64.b64encode(ss.encode('ascii')).decode('ascii')


def configure_client_ssl(relation_data):
    """Configure client with ssl
    """
    ssl_mode, external_ca = get_ssl_mode()
    if ssl_mode == 'off':
        return
    relation_data['ssl_port'] = config('ssl_port')
    if ssl_mode == CERTS_FROM_RELATION:
        relation_certs = get_relation_cert_data()
        ca_data = relation_certs['ca']
        if relation_certs.get('chain'):
            ca_data = ca_data + os.linesep + relation_certs.get('chain')
        relation_data['ssl_ca'] = b64encoded_string(ca_data)
    else:
        if external_ca:
            if config('ssl_ca'):
                if "BEGIN CERTIFICATE" in config('ssl_ca'):
                    ssl_ca_encoded = b64encoded_string(config('ssl_ca'))
                else:
                    ssl_ca_encoded = config('ssl_ca')
                relation_data['ssl_ca'] = ssl_ca_encoded
            return
        ca = ServiceCA.get_ca()
        relation_data['ssl_ca'] = b64encoded_string(ca.get_ca_bundle())


def reconfigure_client_ssl(ssl_enabled=False):
    if deferred_events.get_deferred_restarts():
        log("Deferred event detected, not updating client", INFO)
        return
    ssl_config_keys = set(('ssl_key', 'ssl_cert', 'ssl_ca'))
    for rid in relation_ids('amqp'):
        rdata = relation_get(rid=rid, unit=local_unit())
        if not ssl_enabled and ssl_config_keys.intersection(rdata):
            # No clean way to remove entirely, but blank them.
            relation_set(relation_id=rid, ssl_key='', ssl_cert='', ssl_ca='',
                         ssl_port='')
        elif ssl_enabled and not ssl_config_keys.intersection(rdata):
            configure_client_ssl(rdata)
            relation_set(relation_id=rid, **rdata)
