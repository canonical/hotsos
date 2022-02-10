# Copyright 2014-2021 Canonical Limited.
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

import collections
import copy
import enum
import glob
import hashlib
import json
import math
import os
import re
import socket
import time

from base64 import b64decode
from subprocess import (
    check_call,
    check_output,
    CalledProcessError)

import six

import charmhelpers.contrib.storage.linux.ceph as ch_ceph

from charmhelpers.contrib.openstack.audits.openstack_security_guide import (
    _config_ini as config_ini
)

from charmhelpers.fetch import (
    apt_install,
    filter_installed_packages,
)
from charmhelpers.core.hookenv import (
    NoNetworkBinding,
    config,
    is_relation_made,
    local_unit,
    log,
    relation_get,
    relation_ids,
    related_units,
    relation_set,
    unit_private_ip,
    charm_name,
    DEBUG,
    INFO,
    ERROR,
    status_set,
    network_get_primary_address,
    WARNING,
    service_name,
)

from charmhelpers.core.sysctl import create as sysctl_create
from charmhelpers.core.strutils import bool_from_string
from charmhelpers.contrib.openstack.exceptions import OSContextError

from charmhelpers.core.host import (
    get_bond_master,
    is_phy_iface,
    list_nics,
    get_nic_hwaddr,
    mkdir,
    write_file,
    pwgen,
    lsb_release,
    CompareHostReleases,
)
from charmhelpers.contrib.hahelpers.cluster import (
    determine_apache_port,
    determine_api_port,
    https,
    is_clustered,
)
from charmhelpers.contrib.hahelpers.apache import (
    get_cert,
    get_ca_cert,
    install_ca_cert,
)
from charmhelpers.contrib.openstack.neutron import (
    neutron_plugin_attribute,
    parse_data_port_mappings,
)
from charmhelpers.contrib.openstack.ip import (
    resolve_address,
    INTERNAL,
    ADMIN,
    PUBLIC,
    ADDRESS_MAP,
    local_address,
)
from charmhelpers.contrib.network.ip import (
    get_address_in_network,
    get_ipv4_addr,
    get_ipv6_addr,
    get_netmask_for_address,
    format_ipv6_addr,
    is_bridge_member,
    is_ipv6_disabled,
    get_relation_ip,
)
from charmhelpers.contrib.openstack.utils import (
    config_flags_parser,
    get_os_codename_install_source,
    enable_memcache,
    CompareOpenStackReleases,
    os_release,
)
from charmhelpers.core.unitdata import kv

try:
    from sriov_netplan_shim import pci
except ImportError:
    # The use of the function and contexts that require the pci module is
    # optional.
    pass

try:
    import psutil
except ImportError:
    if six.PY2:
        apt_install('python-psutil', fatal=True)
    else:
        apt_install('python3-psutil', fatal=True)
    import psutil

CA_CERT_PATH = '/usr/local/share/ca-certificates/keystone_juju_ca_cert.crt'
ADDRESS_TYPES = ['admin', 'internal', 'public']
HAPROXY_RUN_DIR = '/var/run/haproxy/'
DEFAULT_OSLO_MESSAGING_DRIVER = "messagingv2"


def ensure_packages(packages):
    """Install but do not upgrade required plugin packages."""
    required = filter_installed_packages(packages)
    if required:
        apt_install(required, fatal=True)


def context_complete(ctxt):
    _missing = []
    for k, v in six.iteritems(ctxt):
        if v is None or v == '':
            _missing.append(k)

    if _missing:
        log('Missing required data: %s' % ' '.join(_missing), level=INFO)
        return False

    return True


class OSContextGenerator(object):
    """Base class for all context generators."""
    interfaces = []
    related = False
    complete = False
    missing_data = []

    def __call__(self):
        raise NotImplementedError

    def context_complete(self, ctxt):
        """Check for missing data for the required context data.
        Set self.missing_data if it exists and return False.
        Set self.complete if no missing data and return True.
        """
        # Fresh start
        self.complete = False
        self.missing_data = []
        for k, v in six.iteritems(ctxt):
            if v is None or v == '':
                if k not in self.missing_data:
                    self.missing_data.append(k)

        if self.missing_data:
            self.complete = False
            log('Missing required data: %s' % ' '.join(self.missing_data),
                level=INFO)
        else:
            self.complete = True
        return self.complete

    def get_related(self):
        """Check if any of the context interfaces have relation ids.
        Set self.related and return True if one of the interfaces
        has relation ids.
        """
        # Fresh start
        self.related = False
        try:
            for interface in self.interfaces:
                if relation_ids(interface):
                    self.related = True
            return self.related
        except AttributeError as e:
            log("{} {}"
                "".format(self, e), 'INFO')
            return self.related


class SharedDBContext(OSContextGenerator):
    interfaces = ['shared-db']

    def __init__(self, database=None, user=None, relation_prefix=None,
                 ssl_dir=None, relation_id=None):
        """Allows inspecting relation for settings prefixed with
        relation_prefix. This is useful for parsing access for multiple
        databases returned via the shared-db interface (eg, nova_password,
        quantum_password)
        """
        self.relation_prefix = relation_prefix
        self.database = database
        self.user = user
        self.ssl_dir = ssl_dir
        self.rel_name = self.interfaces[0]
        self.relation_id = relation_id

    def __call__(self):
        self.database = self.database or config('database')
        self.user = self.user or config('database-user')
        if None in [self.database, self.user]:
            log("Could not generate shared_db context. Missing required charm "
                "config options. (database name and user)", level=ERROR)
            raise OSContextError

        ctxt = {}

        # NOTE(jamespage) if mysql charm provides a network upon which
        # access to the database should be made, reconfigure relation
        # with the service units local address and defer execution
        access_network = relation_get('access-network')
        if access_network is not None:
            if self.relation_prefix is not None:
                hostname_key = "{}_hostname".format(self.relation_prefix)
            else:
                hostname_key = "hostname"
            access_hostname = get_address_in_network(
                access_network,
                local_address(unit_get_fallback='private-address'))
            set_hostname = relation_get(attribute=hostname_key,
                                        unit=local_unit())
            if set_hostname != access_hostname:
                relation_set(relation_settings={hostname_key: access_hostname})
                return None  # Defer any further hook execution for now....

        password_setting = 'password'
        if self.relation_prefix:
            password_setting = self.relation_prefix + '_password'

        if self.relation_id:
            rids = [self.relation_id]
        else:
            rids = relation_ids(self.interfaces[0])

        rel = (get_os_codename_install_source(config('openstack-origin')) or
               'icehouse')
        for rid in rids:
            self.related = True
            for unit in related_units(rid):
                rdata = relation_get(rid=rid, unit=unit)
                host = rdata.get('db_host')
                host = format_ipv6_addr(host) or host
                ctxt = {
                    'database_host': host,
                    'database': self.database,
                    'database_user': self.user,
                    'database_password': rdata.get(password_setting),
                    'database_type': 'mysql+pymysql'
                }
                # Port is being introduced with LP Bug #1876188
                # but it not currently required and may not be set in all
                # cases, particularly in classic charms.
                port = rdata.get('db_port')
                if port:
                    ctxt['database_port'] = port
                if CompareOpenStackReleases(rel) < 'queens':
                    ctxt['database_type'] = 'mysql'
                if self.context_complete(ctxt):
                    db_ssl(rdata, ctxt, self.ssl_dir)
                    return ctxt
        return {}


class PostgresqlDBContext(OSContextGenerator):
    interfaces = ['pgsql-db']

    def __init__(self, database=None):
        self.database = database

    def __call__(self):
        self.database = self.database or config('database')
        if self.database is None:
            log('Could not generate postgresql_db context. Missing required '
                'charm config options. (database name)', level=ERROR)
            raise OSContextError

        ctxt = {}
        for rid in relation_ids(self.interfaces[0]):
            self.related = True
            for unit in related_units(rid):
                rel_host = relation_get('host', rid=rid, unit=unit)
                rel_user = relation_get('user', rid=rid, unit=unit)
                rel_passwd = relation_get('password', rid=rid, unit=unit)
                ctxt = {'database_host': rel_host,
                        'database': self.database,
                        'database_user': rel_user,
                        'database_password': rel_passwd,
                        'database_type': 'postgresql'}
                if self.context_complete(ctxt):
                    return ctxt

        return {}


def db_ssl(rdata, ctxt, ssl_dir):
    if 'ssl_ca' in rdata and ssl_dir:
        ca_path = os.path.join(ssl_dir, 'db-client.ca')
        with open(ca_path, 'wb') as fh:
            fh.write(b64decode(rdata['ssl_ca']))

        ctxt['database_ssl_ca'] = ca_path
    elif 'ssl_ca' in rdata:
        log("Charm not setup for ssl support but ssl ca found", level=INFO)
        return ctxt

    if 'ssl_cert' in rdata:
        cert_path = os.path.join(
            ssl_dir, 'db-client.cert')
        if not os.path.exists(cert_path):
            log("Waiting 1m for ssl client cert validity", level=INFO)
            time.sleep(60)

        with open(cert_path, 'wb') as fh:
            fh.write(b64decode(rdata['ssl_cert']))

        ctxt['database_ssl_cert'] = cert_path
        key_path = os.path.join(ssl_dir, 'db-client.key')
        with open(key_path, 'wb') as fh:
            fh.write(b64decode(rdata['ssl_key']))

        ctxt['database_ssl_key'] = key_path

    return ctxt


class IdentityServiceContext(OSContextGenerator):

    def __init__(self,
                 service=None,
                 service_user=None,
                 rel_name='identity-service'):
        self.service = service
        self.service_user = service_user
        self.rel_name = rel_name
        self.interfaces = [self.rel_name]

    def _setup_pki_cache(self):
        if self.service and self.service_user:
            # This is required for pki token signing if we don't want /tmp to
            # be used.
            cachedir = '/var/cache/%s' % (self.service)
            if not os.path.isdir(cachedir):
                log("Creating service cache dir %s" % (cachedir), level=DEBUG)
                mkdir(path=cachedir, owner=self.service_user,
                      group=self.service_user, perms=0o700)

            return cachedir
        return None

    def _get_pkg_name(self, python_name='keystonemiddleware'):
        """Get corresponding distro installed package for python
        package name.

        :param python_name: nameof the python package
        :type: string
        """
        pkg_names = map(lambda x: x + python_name, ('python3-', 'python-'))

        for pkg in pkg_names:
            if not filter_installed_packages((pkg,)):
                return pkg

        return None

    def _get_keystone_authtoken_ctxt(self, ctxt, keystonemiddleware_os_rel):
        """Build Jinja2 context for full rendering of [keystone_authtoken]
        section with variable names included. Re-constructed from former
        template 'section-keystone-auth-mitaka'.

        :param ctxt: Jinja2 context returned from self.__call__()
        :type: dict
        :param keystonemiddleware_os_rel: OpenStack release name of
            keystonemiddleware package installed
        """
        c = collections.OrderedDict((('auth_type', 'password'),))

        # 'www_authenticate_uri' replaced 'auth_uri' since Stein,
        # see keystonemiddleware upstream sources for more info
        if CompareOpenStackReleases(keystonemiddleware_os_rel) >= 'stein':
            c.update((
                ('www_authenticate_uri', "{}://{}:{}/v3".format(
                    ctxt.get('service_protocol', ''),
                    ctxt.get('service_host', ''),
                    ctxt.get('service_port', ''))),))
        else:
            c.update((
                ('auth_uri', "{}://{}:{}/v3".format(
                    ctxt.get('service_protocol', ''),
                    ctxt.get('service_host', ''),
                    ctxt.get('service_port', ''))),))

        c.update((
            ('auth_url', "{}://{}:{}/v3".format(
                ctxt.get('auth_protocol', ''),
                ctxt.get('auth_host', ''),
                ctxt.get('auth_port', ''))),
            ('project_domain_name', ctxt.get('admin_domain_name', '')),
            ('user_domain_name', ctxt.get('admin_domain_name', '')),
            ('project_name', ctxt.get('admin_tenant_name', '')),
            ('username', ctxt.get('admin_user', '')),
            ('password', ctxt.get('admin_password', '')),
            ('signing_dir', ctxt.get('signing_dir', '')),))

        return c

    def __call__(self):
        log('Generating template context for ' + self.rel_name, level=DEBUG)
        ctxt = {}

        keystonemiddleware_os_release = None
        if self._get_pkg_name():
            keystonemiddleware_os_release = os_release(self._get_pkg_name())

        cachedir = self._setup_pki_cache()
        if cachedir:
            ctxt['signing_dir'] = cachedir

        for rid in relation_ids(self.rel_name):
            self.related = True
            for unit in related_units(rid):
                rdata = relation_get(rid=rid, unit=unit)
                serv_host = rdata.get('service_host')
                serv_host = format_ipv6_addr(serv_host) or serv_host
                auth_host = rdata.get('auth_host')
                auth_host = format_ipv6_addr(auth_host) or auth_host
                int_host = rdata.get('internal_host')
                int_host = format_ipv6_addr(int_host) or int_host
                svc_protocol = rdata.get('service_protocol') or 'http'
                auth_protocol = rdata.get('auth_protocol') or 'http'
                int_protocol = rdata.get('internal_protocol') or 'http'
                api_version = rdata.get('api_version') or '2.0'
                ctxt.update({'service_port': rdata.get('service_port'),
                             'service_host': serv_host,
                             'auth_host': auth_host,
                             'auth_port': rdata.get('auth_port'),
                             'internal_host': int_host,
                             'internal_port': rdata.get('internal_port'),
                             'admin_tenant_name': rdata.get('service_tenant'),
                             'admin_user': rdata.get('service_username'),
                             'admin_password': rdata.get('service_password'),
                             'service_protocol': svc_protocol,
                             'auth_protocol': auth_protocol,
                             'internal_protocol': int_protocol,
                             'api_version': api_version})

                if float(api_version) > 2:
                    ctxt.update({
                        'admin_domain_name': rdata.get('service_domain'),
                        'service_project_id': rdata.get('service_tenant_id'),
                        'service_domain_id': rdata.get('service_domain_id')})

                # we keep all veriables in ctxt for compatibility and
                # add nested dictionary for keystone_authtoken generic
                # templating
                if keystonemiddleware_os_release:
                    ctxt['keystone_authtoken'] = \
                        self._get_keystone_authtoken_ctxt(
                            ctxt, keystonemiddleware_os_release)

                if self.context_complete(ctxt):
                    # NOTE(jamespage) this is required for >= icehouse
                    # so a missing value just indicates keystone needs
                    # upgrading
                    ctxt['admin_tenant_id'] = rdata.get('service_tenant_id')
                    ctxt['admin_domain_id'] = rdata.get('service_domain_id')
                    return ctxt

        return {}


class IdentityCredentialsContext(IdentityServiceContext):
    '''Context for identity-credentials interface type'''

    def __init__(self,
                 service=None,
                 service_user=None,
                 rel_name='identity-credentials'):
        super(IdentityCredentialsContext, self).__init__(service,
                                                         service_user,
                                                         rel_name)

    def __call__(self):
        log('Generating template context for ' + self.rel_name, level=DEBUG)
        ctxt = {}

        cachedir = self._setup_pki_cache()
        if cachedir:
            ctxt['signing_dir'] = cachedir

        for rid in relation_ids(self.rel_name):
            self.related = True
            for unit in related_units(rid):
                rdata = relation_get(rid=rid, unit=unit)
                credentials_host = rdata.get('credentials_host')
                credentials_host = (
                    format_ipv6_addr(credentials_host) or credentials_host
                )
                auth_host = rdata.get('auth_host')
                auth_host = format_ipv6_addr(auth_host) or auth_host
                svc_protocol = rdata.get('credentials_protocol') or 'http'
                auth_protocol = rdata.get('auth_protocol') or 'http'
                api_version = rdata.get('api_version') or '2.0'
                ctxt.update({
                    'service_port': rdata.get('credentials_port'),
                    'service_host': credentials_host,
                    'auth_host': auth_host,
                    'auth_port': rdata.get('auth_port'),
                    'admin_tenant_name': rdata.get('credentials_project'),
                    'admin_tenant_id': rdata.get('credentials_project_id'),
                    'admin_user': rdata.get('credentials_username'),
                    'admin_password': rdata.get('credentials_password'),
                    'service_protocol': svc_protocol,
                    'auth_protocol': auth_protocol,
                    'api_version': api_version
                })

                if float(api_version) > 2:
                    ctxt.update({'admin_domain_name':
                                 rdata.get('domain')})

                if self.context_complete(ctxt):
                    return ctxt

        return {}


class NovaVendorMetadataContext(OSContextGenerator):
    """Context used for configuring nova vendor metadata on nova.conf file."""

    def __init__(self, os_release_pkg, interfaces=None):
        """Initialize the NovaVendorMetadataContext object.

        :param os_release_pkg: the package name to extract the OpenStack
            release codename from.
        :type os_release_pkg: str
        :param interfaces: list of string values to be used as the Context's
            relation interfaces.
        :type interfaces: List[str]
        """
        self.os_release_pkg = os_release_pkg
        if interfaces is not None:
            self.interfaces = interfaces

    def __call__(self):
        cmp_os_release = CompareOpenStackReleases(
            os_release(self.os_release_pkg))
        ctxt = {'vendor_data': False}

        vdata_providers = []
        vdata = config('vendor-data')
        vdata_url = config('vendor-data-url')

        if vdata:
            try:
                # validate the JSON. If invalid, we do not set anything here
                json.loads(vdata)
            except (TypeError, ValueError) as e:
                log('Error decoding vendor-data. {}'.format(e), level=ERROR)
            else:
                ctxt['vendor_data'] = True
                # Mitaka does not support DynamicJSON
                # so vendordata_providers is not needed
                if cmp_os_release > 'mitaka':
                    vdata_providers.append('StaticJSON')

        if vdata_url:
            if cmp_os_release > 'mitaka':
                ctxt['vendor_data_url'] = vdata_url
                vdata_providers.append('DynamicJSON')
            else:
                log('Dynamic vendor data unsupported'
                    ' for {}.'.format(cmp_os_release), level=ERROR)
        if vdata_providers:
            ctxt['vendordata_providers'] = ','.join(vdata_providers)

        return ctxt


class NovaVendorMetadataJSONContext(OSContextGenerator):
    """Context used for writing nova vendor metadata json file."""

    def __init__(self, os_release_pkg):
        """Initialize the NovaVendorMetadataJSONContext object.

        :param os_release_pkg: the package name to extract the OpenStack
            release codename from.
        :type os_release_pkg: str
        """
        self.os_release_pkg = os_release_pkg

    def __call__(self):
        ctxt = {'vendor_data_json': '{}'}

        vdata = config('vendor-data')
        if vdata:
            try:
                # validate the JSON. If invalid, we return empty.
                json.loads(vdata)
            except (TypeError, ValueError) as e:
                log('Error decoding vendor-data. {}'.format(e), level=ERROR)
            else:
                ctxt['vendor_data_json'] = vdata

        return ctxt


class AMQPContext(OSContextGenerator):

    def __init__(self, ssl_dir=None, rel_name='amqp', relation_prefix=None,
                 relation_id=None):
        self.ssl_dir = ssl_dir
        self.rel_name = rel_name
        self.relation_prefix = relation_prefix
        self.interfaces = [rel_name]
        self.relation_id = relation_id

    def __call__(self):
        log('Generating template context for amqp', level=DEBUG)
        conf = config()
        if self.relation_prefix:
            user_setting = '%s-rabbit-user' % (self.relation_prefix)
            vhost_setting = '%s-rabbit-vhost' % (self.relation_prefix)
        else:
            user_setting = 'rabbit-user'
            vhost_setting = 'rabbit-vhost'

        try:
            username = conf[user_setting]
            vhost = conf[vhost_setting]
        except KeyError as e:
            log('Could not generate shared_db context. Missing required charm '
                'config options: %s.' % e, level=ERROR)
            raise OSContextError

        ctxt = {}
        if self.relation_id:
            rids = [self.relation_id]
        else:
            rids = relation_ids(self.rel_name)
        for rid in rids:
            ha_vip_only = False
            self.related = True
            transport_hosts = None
            rabbitmq_port = '5672'
            for unit in related_units(rid):
                if relation_get('clustered', rid=rid, unit=unit):
                    ctxt['clustered'] = True
                    vip = relation_get('vip', rid=rid, unit=unit)
                    vip = format_ipv6_addr(vip) or vip
                    ctxt['rabbitmq_host'] = vip
                    transport_hosts = [vip]
                else:
                    host = relation_get('private-address', rid=rid, unit=unit)
                    host = format_ipv6_addr(host) or host
                    ctxt['rabbitmq_host'] = host
                    transport_hosts = [host]

                ctxt.update({
                    'rabbitmq_user': username,
                    'rabbitmq_password': relation_get('password', rid=rid,
                                                      unit=unit),
                    'rabbitmq_virtual_host': vhost,
                })

                ssl_port = relation_get('ssl_port', rid=rid, unit=unit)
                if ssl_port:
                    ctxt['rabbit_ssl_port'] = ssl_port
                    rabbitmq_port = ssl_port

                ssl_ca = relation_get('ssl_ca', rid=rid, unit=unit)
                if ssl_ca:
                    ctxt['rabbit_ssl_ca'] = ssl_ca

                if relation_get('ha_queues', rid=rid, unit=unit) is not None:
                    ctxt['rabbitmq_ha_queues'] = True

                ha_vip_only = relation_get('ha-vip-only',
                                           rid=rid, unit=unit) is not None

                if self.context_complete(ctxt):
                    if 'rabbit_ssl_ca' in ctxt:
                        if not self.ssl_dir:
                            log("Charm not setup for ssl support but ssl ca "
                                "found", level=INFO)
                            break

                        ca_path = os.path.join(
                            self.ssl_dir, 'rabbit-client-ca.pem')
                        with open(ca_path, 'wb') as fh:
                            fh.write(b64decode(ctxt['rabbit_ssl_ca']))
                            ctxt['rabbit_ssl_ca'] = ca_path

                    # Sufficient information found = break out!
                    break

            # Used for active/active rabbitmq >= grizzly
            if (('clustered' not in ctxt or ha_vip_only) and
                    len(related_units(rid)) > 1):
                rabbitmq_hosts = []
                for unit in related_units(rid):
                    host = relation_get('private-address', rid=rid, unit=unit)
                    if not relation_get('password', rid=rid, unit=unit):
                        log(
                            ("Skipping {} password not sent which indicates "
                             "unit is not ready.".format(host)),
                            level=DEBUG)
                        continue
                    host = format_ipv6_addr(host) or host
                    rabbitmq_hosts.append(host)

                rabbitmq_hosts = sorted(rabbitmq_hosts)
                ctxt['rabbitmq_hosts'] = ','.join(rabbitmq_hosts)
                transport_hosts = rabbitmq_hosts

            if transport_hosts:
                transport_url_hosts = ','.join([
                    "{}:{}@{}:{}".format(ctxt['rabbitmq_user'],
                                         ctxt['rabbitmq_password'],
                                         host_,
                                         rabbitmq_port)
                    for host_ in transport_hosts])
                ctxt['transport_url'] = "rabbit://{}/{}".format(
                    transport_url_hosts, vhost)

        oslo_messaging_flags = conf.get('oslo-messaging-flags', None)
        if oslo_messaging_flags:
            ctxt['oslo_messaging_flags'] = config_flags_parser(
                oslo_messaging_flags)

        oslo_messaging_driver = conf.get(
            'oslo-messaging-driver', DEFAULT_OSLO_MESSAGING_DRIVER)
        if oslo_messaging_driver:
            ctxt['oslo_messaging_driver'] = oslo_messaging_driver

        notification_format = conf.get('notification-format', None)
        if notification_format:
            ctxt['notification_format'] = notification_format

        notification_topics = conf.get('notification-topics', None)
        if notification_topics:
            ctxt['notification_topics'] = notification_topics

        send_notifications_to_logs = conf.get('send-notifications-to-logs', None)
        if send_notifications_to_logs:
            ctxt['send_notifications_to_logs'] = send_notifications_to_logs

        if not self.complete:
            return {}

        return ctxt


class CephContext(OSContextGenerator):
    """Generates context for /etc/ceph/ceph.conf templates."""
    interfaces = ['ceph']

    def __call__(self):
        if not relation_ids('ceph'):
            return {}

        log('Generating template context for ceph', level=DEBUG)
        mon_hosts = []
        ctxt = {
            'use_syslog': str(config('use-syslog')).lower()
        }
        for rid in relation_ids('ceph'):
            for unit in related_units(rid):
                if not ctxt.get('auth'):
                    ctxt['auth'] = relation_get('auth', rid=rid, unit=unit)
                if not ctxt.get('key'):
                    ctxt['key'] = relation_get('key', rid=rid, unit=unit)
                if not ctxt.get('rbd_features'):
                    default_features = relation_get('rbd-features', rid=rid, unit=unit)
                    if default_features is not None:
                        ctxt['rbd_features'] = default_features

                ceph_addrs = relation_get('ceph-public-address', rid=rid,
                                          unit=unit)
                if ceph_addrs:
                    for addr in ceph_addrs.split(' '):
                        mon_hosts.append(format_ipv6_addr(addr) or addr)
                else:
                    priv_addr = relation_get('private-address', rid=rid,
                                             unit=unit)
                    mon_hosts.append(format_ipv6_addr(priv_addr) or priv_addr)

        ctxt['mon_hosts'] = ' '.join(sorted(mon_hosts))

        if config('pool-type') and config('pool-type') == 'erasure-coded':
            base_pool_name = config('rbd-pool') or config('rbd-pool-name')
            if not base_pool_name:
                base_pool_name = service_name()
            ctxt['rbd_default_data_pool'] = base_pool_name

        if not os.path.isdir('/etc/ceph'):
            os.mkdir('/etc/ceph')

        if not self.context_complete(ctxt):
            return {}

        ensure_packages(['ceph-common'])
        return ctxt

    def context_complete(self, ctxt):
        """Overridden here to ensure the context is actually complete.

        We set `key` and `auth` to None here, by default, to ensure
        that the context will always evaluate to incomplete until the
        Ceph relation has actually sent these details; otherwise,
        there is a potential race condition between the relation
        appearing and the first unit actually setting this data on the
        relation.

        :param ctxt: The current context members
        :type ctxt: Dict[str, ANY]
        :returns: True if the context is complete
        :rtype: bool
        """
        if 'auth' not in ctxt or 'key' not in ctxt:
            return False
        return super(CephContext, self).context_complete(ctxt)


class HAProxyContext(OSContextGenerator):
    """Provides half a context for the haproxy template, which describes
    all peers to be included in the cluster.  Each charm needs to include
    its own context generator that describes the port mapping.

    :side effect: mkdir is called on HAPROXY_RUN_DIR
    """
    interfaces = ['cluster']

    def __init__(self, singlenode_mode=False,
                 address_types=ADDRESS_TYPES):
        self.address_types = address_types
        self.singlenode_mode = singlenode_mode

    def __call__(self):
        if not os.path.isdir(HAPROXY_RUN_DIR):
            mkdir(path=HAPROXY_RUN_DIR)
        if not relation_ids('cluster') and not self.singlenode_mode:
            return {}

        l_unit = local_unit().replace('/', '-')
        cluster_hosts = collections.OrderedDict()

        # NOTE(jamespage): build out map of configured network endpoints
        # and associated backends
        for addr_type in self.address_types:
            cfg_opt = 'os-{}-network'.format(addr_type)
            # NOTE(thedac) For some reason the ADDRESS_MAP uses 'int' rather
            # than 'internal'
            if addr_type == 'internal':
                _addr_map_type = INTERNAL
            else:
                _addr_map_type = addr_type
            # Network spaces aware
            laddr = get_relation_ip(ADDRESS_MAP[_addr_map_type]['binding'],
                                    config(cfg_opt))
            if laddr:
                netmask = get_netmask_for_address(laddr)
                cluster_hosts[laddr] = {
                    'network': "{}/{}".format(laddr,
                                              netmask),
                    'backends': collections.OrderedDict([(l_unit,
                                                          laddr)])
                }
                for rid in relation_ids('cluster'):
                    for unit in sorted(related_units(rid)):
                        # API Charms will need to set {addr_type}-address with
                        # get_relation_ip(addr_type)
                        _laddr = relation_get('{}-address'.format(addr_type),
                                              rid=rid, unit=unit)
                        if _laddr:
                            _unit = unit.replace('/', '-')
                            cluster_hosts[laddr]['backends'][_unit] = _laddr

        # NOTE(jamespage) add backend based on get_relation_ip - this
        # will either be the only backend or the fallback if no acls
        # match in the frontend
        # Network spaces aware
        addr = get_relation_ip('cluster')
        cluster_hosts[addr] = {}
        netmask = get_netmask_for_address(addr)
        cluster_hosts[addr] = {
            'network': "{}/{}".format(addr, netmask),
            'backends': collections.OrderedDict([(l_unit,
                                                  addr)])
        }
        for rid in relation_ids('cluster'):
            for unit in sorted(related_units(rid)):
                # API Charms will need to set their private-address with
                # get_relation_ip('cluster')
                _laddr = relation_get('private-address',
                                      rid=rid, unit=unit)
                if _laddr:
                    _unit = unit.replace('/', '-')
                    cluster_hosts[addr]['backends'][_unit] = _laddr

        ctxt = {
            'frontends': cluster_hosts,
            'default_backend': addr
        }

        if config('haproxy-server-timeout'):
            ctxt['haproxy_server_timeout'] = config('haproxy-server-timeout')

        if config('haproxy-client-timeout'):
            ctxt['haproxy_client_timeout'] = config('haproxy-client-timeout')

        if config('haproxy-queue-timeout'):
            ctxt['haproxy_queue_timeout'] = config('haproxy-queue-timeout')

        if config('haproxy-connect-timeout'):
            ctxt['haproxy_connect_timeout'] = config('haproxy-connect-timeout')

        if config('prefer-ipv6'):
            ctxt['local_host'] = 'ip6-localhost'
            ctxt['haproxy_host'] = '::'
        else:
            ctxt['local_host'] = '127.0.0.1'
            ctxt['haproxy_host'] = '0.0.0.0'

        ctxt['ipv6_enabled'] = not is_ipv6_disabled()

        ctxt['stat_port'] = '8888'

        db = kv()
        ctxt['stat_password'] = db.get('stat-password')
        if not ctxt['stat_password']:
            ctxt['stat_password'] = db.set('stat-password',
                                           pwgen(32))
            db.flush()

        for frontend in cluster_hosts:
            if (len(cluster_hosts[frontend]['backends']) > 1 or
                    self.singlenode_mode):
                # Enable haproxy when we have enough peers.
                log('Ensuring haproxy enabled in /etc/default/haproxy.',
                    level=DEBUG)
                with open('/etc/default/haproxy', 'w') as out:
                    out.write('ENABLED=1\n')

                return ctxt

        log('HAProxy context is incomplete, this unit has no peers.',
            level=INFO)
        return {}


class ImageServiceContext(OSContextGenerator):
    interfaces = ['image-service']

    def __call__(self):
        """Obtains the glance API server from the image-service relation.
        Useful in nova and cinder (currently).
        """
        log('Generating template context for image-service.', level=DEBUG)
        rids = relation_ids('image-service')
        if not rids:
            return {}

        for rid in rids:
            for unit in related_units(rid):
                api_server = relation_get('glance-api-server',
                                          rid=rid, unit=unit)
                if api_server:
                    return {'glance_api_servers': api_server}

        log("ImageService context is incomplete. Missing required relation "
            "data.", level=INFO)
        return {}


class ApacheSSLContext(OSContextGenerator):
    """Generates a context for an apache vhost configuration that configures
    HTTPS reverse proxying for one or many endpoints.  Generated context
    looks something like::

        {
            'namespace': 'cinder',
            'private_address': 'iscsi.mycinderhost.com',
            'endpoints': [(8776, 8766), (8777, 8767)]
        }

    The endpoints list consists of a tuples mapping external ports
    to internal ports.
    """
    interfaces = ['https']

    # charms should inherit this context and set external ports
    # and service namespace accordingly.
    external_ports = []
    service_namespace = None
    user = group = 'root'

    def enable_modules(self):
        cmd = ['a2enmod', 'ssl', 'proxy', 'proxy_http', 'headers']
        check_call(cmd)

    def configure_cert(self, cn=None):
        ssl_dir = os.path.join('/etc/apache2/ssl/', self.service_namespace)
        mkdir(path=ssl_dir)
        cert, key = get_cert(cn)
        if cert and key:
            if cn:
                cert_filename = 'cert_{}'.format(cn)
                key_filename = 'key_{}'.format(cn)
            else:
                cert_filename = 'cert'
                key_filename = 'key'

            write_file(path=os.path.join(ssl_dir, cert_filename),
                       content=b64decode(cert), owner=self.user,
                       group=self.group, perms=0o640)
            write_file(path=os.path.join(ssl_dir, key_filename),
                       content=b64decode(key), owner=self.user,
                       group=self.group, perms=0o640)

    def configure_ca(self):
        ca_cert = get_ca_cert()
        if ca_cert:
            install_ca_cert(b64decode(ca_cert))

    def canonical_names(self):
        """Figure out which canonical names clients will access this service.
        """
        cns = []
        for r_id in relation_ids('identity-service'):
            for unit in related_units(r_id):
                rdata = relation_get(rid=r_id, unit=unit)
                for k in rdata:
                    if k.startswith('ssl_key_'):
                        cns.append(k.lstrip('ssl_key_'))

        return sorted(list(set(cns)))

    def get_network_addresses(self):
        """For each network configured, return corresponding address and
           hostnamr or vip (if available).

        Returns a list of tuples of the form:

            [(address_in_net_a, hostname_in_net_a),
             (address_in_net_b, hostname_in_net_b),
             ...]

            or, if no hostnames(s) available:

            [(address_in_net_a, vip_in_net_a),
             (address_in_net_b, vip_in_net_b),
             ...]

            or, if no vip(s) available:

            [(address_in_net_a, address_in_net_a),
             (address_in_net_b, address_in_net_b),
             ...]
        """
        addresses = []
        for net_type in [INTERNAL, ADMIN, PUBLIC]:
            net_config = config(ADDRESS_MAP[net_type]['config'])
            # NOTE(jamespage): Fallback must always be private address
            #                  as this is used to bind services on the
            #                  local unit.
            fallback = local_address(unit_get_fallback="private-address")
            if net_config:
                addr = get_address_in_network(net_config,
                                              fallback)
            else:
                try:
                    addr = network_get_primary_address(
                        ADDRESS_MAP[net_type]['binding']
                    )
                except (NotImplementedError, NoNetworkBinding):
                    addr = fallback

            endpoint = resolve_address(net_type)
            addresses.append((addr, endpoint))

        return sorted(set(addresses))

    def __call__(self):
        if isinstance(self.external_ports, six.string_types):
            self.external_ports = [self.external_ports]

        if not self.external_ports or not https():
            return {}

        use_keystone_ca = True
        for rid in relation_ids('certificates'):
            if related_units(rid):
                use_keystone_ca = False

        if use_keystone_ca:
            self.configure_ca()

        self.enable_modules()

        ctxt = {'namespace': self.service_namespace,
                'endpoints': [],
                'ext_ports': []}

        if use_keystone_ca:
            cns = self.canonical_names()
            if cns:
                for cn in cns:
                    self.configure_cert(cn)
            else:
                # Expect cert/key provided in config (currently assumed that ca
                # uses ip for cn)
                for net_type in (INTERNAL, ADMIN, PUBLIC):
                    cn = resolve_address(endpoint_type=net_type)
                    self.configure_cert(cn)

        addresses = self.get_network_addresses()
        for address, endpoint in addresses:
            for api_port in self.external_ports:
                ext_port = determine_apache_port(api_port,
                                                 singlenode_mode=True)
                int_port = determine_api_port(api_port, singlenode_mode=True)
                portmap = (address, endpoint, int(ext_port), int(int_port))
                ctxt['endpoints'].append(portmap)
                ctxt['ext_ports'].append(int(ext_port))

        ctxt['ext_ports'] = sorted(list(set(ctxt['ext_ports'])))
        return ctxt


class NeutronContext(OSContextGenerator):
    interfaces = []

    @property
    def plugin(self):
        return None

    @property
    def network_manager(self):
        return None

    @property
    def packages(self):
        return neutron_plugin_attribute(self.plugin, 'packages',
                                        self.network_manager)

    @property
    def neutron_security_groups(self):
        return None

    def _ensure_packages(self):
        for pkgs in self.packages:
            ensure_packages(pkgs)

    def ovs_ctxt(self):
        driver = neutron_plugin_attribute(self.plugin, 'driver',
                                          self.network_manager)
        config = neutron_plugin_attribute(self.plugin, 'config',
                                          self.network_manager)
        ovs_ctxt = {'core_plugin': driver,
                    'neutron_plugin': 'ovs',
                    'neutron_security_groups': self.neutron_security_groups,
                    'local_ip': unit_private_ip(),
                    'config': config}

        return ovs_ctxt

    def nuage_ctxt(self):
        driver = neutron_plugin_attribute(self.plugin, 'driver',
                                          self.network_manager)
        config = neutron_plugin_attribute(self.plugin, 'config',
                                          self.network_manager)
        nuage_ctxt = {'core_plugin': driver,
                      'neutron_plugin': 'vsp',
                      'neutron_security_groups': self.neutron_security_groups,
                      'local_ip': unit_private_ip(),
                      'config': config}

        return nuage_ctxt

    def nvp_ctxt(self):
        driver = neutron_plugin_attribute(self.plugin, 'driver',
                                          self.network_manager)
        config = neutron_plugin_attribute(self.plugin, 'config',
                                          self.network_manager)
        nvp_ctxt = {'core_plugin': driver,
                    'neutron_plugin': 'nvp',
                    'neutron_security_groups': self.neutron_security_groups,
                    'local_ip': unit_private_ip(),
                    'config': config}

        return nvp_ctxt

    def n1kv_ctxt(self):
        driver = neutron_plugin_attribute(self.plugin, 'driver',
                                          self.network_manager)
        n1kv_config = neutron_plugin_attribute(self.plugin, 'config',
                                               self.network_manager)
        n1kv_user_config_flags = config('n1kv-config-flags')
        restrict_policy_profiles = config('n1kv-restrict-policy-profiles')
        n1kv_ctxt = {'core_plugin': driver,
                     'neutron_plugin': 'n1kv',
                     'neutron_security_groups': self.neutron_security_groups,
                     'local_ip': unit_private_ip(),
                     'config': n1kv_config,
                     'vsm_ip': config('n1kv-vsm-ip'),
                     'vsm_username': config('n1kv-vsm-username'),
                     'vsm_password': config('n1kv-vsm-password'),
                     'restrict_policy_profiles': restrict_policy_profiles}

        if n1kv_user_config_flags:
            flags = config_flags_parser(n1kv_user_config_flags)
            n1kv_ctxt['user_config_flags'] = flags

        return n1kv_ctxt

    def calico_ctxt(self):
        driver = neutron_plugin_attribute(self.plugin, 'driver',
                                          self.network_manager)
        config = neutron_plugin_attribute(self.plugin, 'config',
                                          self.network_manager)
        calico_ctxt = {'core_plugin': driver,
                       'neutron_plugin': 'Calico',
                       'neutron_security_groups': self.neutron_security_groups,
                       'local_ip': unit_private_ip(),
                       'config': config}

        return calico_ctxt

    def neutron_ctxt(self):
        if https():
            proto = 'https'
        else:
            proto = 'http'

        if is_clustered():
            host = config('vip')
        else:
            host = local_address(unit_get_fallback='private-address')

        ctxt = {'network_manager': self.network_manager,
                'neutron_url': '%s://%s:%s' % (proto, host, '9696')}
        return ctxt

    def pg_ctxt(self):
        driver = neutron_plugin_attribute(self.plugin, 'driver',
                                          self.network_manager)
        config = neutron_plugin_attribute(self.plugin, 'config',
                                          self.network_manager)
        ovs_ctxt = {'core_plugin': driver,
                    'neutron_plugin': 'plumgrid',
                    'neutron_security_groups': self.neutron_security_groups,
                    'local_ip': unit_private_ip(),
                    'config': config}
        return ovs_ctxt

    def midonet_ctxt(self):
        driver = neutron_plugin_attribute(self.plugin, 'driver',
                                          self.network_manager)
        midonet_config = neutron_plugin_attribute(self.plugin, 'config',
                                                  self.network_manager)
        mido_ctxt = {'core_plugin': driver,
                     'neutron_plugin': 'midonet',
                     'neutron_security_groups': self.neutron_security_groups,
                     'local_ip': unit_private_ip(),
                     'config': midonet_config}

        return mido_ctxt

    def __call__(self):
        if self.network_manager not in ['quantum', 'neutron']:
            return {}

        if not self.plugin:
            return {}

        ctxt = self.neutron_ctxt()

        if self.plugin == 'ovs':
            ctxt.update(self.ovs_ctxt())
        elif self.plugin in ['nvp', 'nsx']:
            ctxt.update(self.nvp_ctxt())
        elif self.plugin == 'n1kv':
            ctxt.update(self.n1kv_ctxt())
        elif self.plugin == 'Calico':
            ctxt.update(self.calico_ctxt())
        elif self.plugin == 'vsp':
            ctxt.update(self.nuage_ctxt())
        elif self.plugin == 'plumgrid':
            ctxt.update(self.pg_ctxt())
        elif self.plugin == 'midonet':
            ctxt.update(self.midonet_ctxt())

        alchemy_flags = config('neutron-alchemy-flags')
        if alchemy_flags:
            flags = config_flags_parser(alchemy_flags)
            ctxt['neutron_alchemy_flags'] = flags

        return ctxt


class NeutronPortContext(OSContextGenerator):

    def resolve_ports(self, ports):
        """Resolve NICs not yet bound to bridge(s)

        If hwaddress provided then returns resolved hwaddress otherwise NIC.
        """
        if not ports:
            return None

        hwaddr_to_nic = {}
        hwaddr_to_ip = {}
        extant_nics = list_nics()

        for nic in extant_nics:
            # Ignore virtual interfaces (bond masters will be identified from
            # their slaves)
            if not is_phy_iface(nic):
                continue

            _nic = get_bond_master(nic)
            if _nic:
                log("Replacing iface '%s' with bond master '%s'" % (nic, _nic),
                    level=DEBUG)
                nic = _nic

            hwaddr = get_nic_hwaddr(nic)
            hwaddr_to_nic[hwaddr] = nic
            addresses = get_ipv4_addr(nic, fatal=False)
            addresses += get_ipv6_addr(iface=nic, fatal=False)
            hwaddr_to_ip[hwaddr] = addresses

        resolved = []
        mac_regex = re.compile(r'([0-9A-F]{2}[:-]){5}([0-9A-F]{2})', re.I)
        for entry in ports:
            if re.match(mac_regex, entry):
                # NIC is in known NICs and does NOT have an IP address
                if entry in hwaddr_to_nic and not hwaddr_to_ip[entry]:
                    # If the nic is part of a bridge then don't use it
                    if is_bridge_member(hwaddr_to_nic[entry]):
                        continue

                    # Entry is a MAC address for a valid interface that doesn't
                    # have an IP address assigned yet.
                    resolved.append(hwaddr_to_nic[entry])
            elif entry in extant_nics:
                # If the passed entry is not a MAC address and the interface
                # exists, assume it's a valid interface, and that the user put
                # it there on purpose (we can trust it to be the real external
                # network).
                resolved.append(entry)

        # Ensure no duplicates
        return list(set(resolved))


class OSConfigFlagContext(OSContextGenerator):
    """Provides support for user-defined config flags.

    Users can define a comma-seperated list of key=value pairs
    in the charm configuration and apply them at any point in
    any file by using a template flag.

    Sometimes users might want config flags inserted within a
    specific section so this class allows users to specify the
    template flag name, allowing for multiple template flags
    (sections) within the same context.

    NOTE: the value of config-flags may be a comma-separated list of
          key=value pairs and some Openstack config files support
          comma-separated lists as values.
    """

    def __init__(self, charm_flag='config-flags',
                 template_flag='user_config_flags'):
        """
        :param charm_flag: config flags in charm configuration.
        :param template_flag: insert point for user-defined flags in template
                              file.
        """
        super(OSConfigFlagContext, self).__init__()
        self._charm_flag = charm_flag
        self._template_flag = template_flag

    def __call__(self):
        config_flags = config(self._charm_flag)
        if not config_flags:
            return {}

        return {self._template_flag:
                config_flags_parser(config_flags)}


class LibvirtConfigFlagsContext(OSContextGenerator):
    """
    This context provides support for extending
    the libvirt section through user-defined flags.
    """
    def __call__(self):
        ctxt = {}
        libvirt_flags = config('libvirt-flags')
        if libvirt_flags:
            ctxt['libvirt_flags'] = config_flags_parser(
                libvirt_flags)
        return ctxt


class SubordinateConfigContext(OSContextGenerator):

    """
    Responsible for inspecting relations to subordinates that
    may be exporting required config via a json blob.

    The subordinate interface allows subordinates to export their
    configuration requirements to the principle for multiple config
    files and multiple services.  Ie, a subordinate that has interfaces
    to both glance and nova may export to following yaml blob as json::

        glance:
            /etc/glance/glance-api.conf:
                sections:
                    DEFAULT:
                        - [key1, value1]
            /etc/glance/glance-registry.conf:
                    MYSECTION:
                        - [key2, value2]
        nova:
            /etc/nova/nova.conf:
                sections:
                    DEFAULT:
                        - [key3, value3]


    It is then up to the principle charms to subscribe this context to
    the service+config file it is interestd in.  Configuration data will
    be available in the template context, in glance's case, as::

        ctxt = {
            ... other context ...
            'subordinate_configuration': {
                'DEFAULT': {
                    'key1': 'value1',
                },
                'MYSECTION': {
                    'key2': 'value2',
                },
            }
        }
    """

    def __init__(self, service, config_file, interface):
        """
        :param service     : Service name key to query in any subordinate
                             data found
        :param config_file : Service's config file to query sections
        :param interface   : Subordinate interface to inspect
        """
        self.config_file = config_file
        if isinstance(service, list):
            self.services = service
        else:
            self.services = [service]
        if isinstance(interface, list):
            self.interfaces = interface
        else:
            self.interfaces = [interface]

    def __call__(self):
        ctxt = {'sections': {}}
        rids = []
        for interface in self.interfaces:
            rids.extend(relation_ids(interface))
        for rid in rids:
            for unit in related_units(rid):
                sub_config = relation_get('subordinate_configuration',
                                          rid=rid, unit=unit)
                if sub_config and sub_config != '':
                    try:
                        sub_config = json.loads(sub_config)
                    except Exception:
                        log('Could not parse JSON from '
                            'subordinate_configuration setting from %s'
                            % rid, level=ERROR)
                        continue

                    for service in self.services:
                        if service not in sub_config:
                            log('Found subordinate_configuration on %s but it '
                                'contained nothing for %s service'
                                % (rid, service), level=INFO)
                            continue

                        sub_config = sub_config[service]
                        if self.config_file not in sub_config:
                            log('Found subordinate_configuration on %s but it '
                                'contained nothing for %s'
                                % (rid, self.config_file), level=INFO)
                            continue

                        sub_config = sub_config[self.config_file]
                        for k, v in six.iteritems(sub_config):
                            if k == 'sections':
                                for section, config_list in six.iteritems(v):
                                    log("adding section '%s'" % (section),
                                        level=DEBUG)
                                    if ctxt[k].get(section):
                                        ctxt[k][section].extend(config_list)
                                    else:
                                        ctxt[k][section] = config_list
                            else:
                                ctxt[k] = v
        if self.context_complete(ctxt):
            log("%d section(s) found" % (len(ctxt['sections'])), level=DEBUG)
            return ctxt
        else:
            return {}

    def context_complete(self, ctxt):
        """Overridden here to ensure the context is actually complete.

        :param ctxt: The current context members
        :type ctxt: Dict[str, ANY]
        :returns: True if the context is complete
        :rtype: bool
        """
        if not ctxt.get('sections'):
            return False
        return super(SubordinateConfigContext, self).context_complete(ctxt)


class LogLevelContext(OSContextGenerator):

    def __call__(self):
        ctxt = {}
        ctxt['debug'] = \
            False if config('debug') is None else config('debug')
        ctxt['verbose'] = \
            False if config('verbose') is None else config('verbose')

        return ctxt


class SyslogContext(OSContextGenerator):

    def __call__(self):
        ctxt = {'use_syslog': config('use-syslog')}
        return ctxt


class BindHostContext(OSContextGenerator):

    def __call__(self):
        if config('prefer-ipv6'):
            return {'bind_host': '::'}
        else:
            return {'bind_host': '0.0.0.0'}


MAX_DEFAULT_WORKERS = 4
DEFAULT_MULTIPLIER = 2


def _calculate_workers():
    '''
    Determine the number of worker processes based on the CPU
    count of the unit containing the application.

    Workers will be limited to MAX_DEFAULT_WORKERS in
    container environments where no worker-multipler configuration
    option been set.

    @returns int: number of worker processes to use
    '''
    multiplier = config('worker-multiplier')

    # distinguish an empty config and an explicit config as 0.0
    if multiplier is None:
        multiplier = DEFAULT_MULTIPLIER

    count = int(_num_cpus() * multiplier)
    if count <= 0:
        # assign at least one worker
        count = 1

    if config('worker-multiplier') is None:
        # NOTE(jamespage): Limit unconfigured worker-multiplier
        #                  to MAX_DEFAULT_WORKERS to avoid insane
        #                  worker configuration on large servers
        # Reference: https://pad.lv/1665270
        count = min(count, MAX_DEFAULT_WORKERS)

    return count


def _num_cpus():
    '''
    Compatibility wrapper for calculating the number of CPU's
    a unit has.

    @returns: int: number of CPU cores detected
    '''
    try:
        return psutil.cpu_count()
    except AttributeError:
        return psutil.NUM_CPUS


class WorkerConfigContext(OSContextGenerator):

    def __call__(self):
        ctxt = {"workers": _calculate_workers()}
        return ctxt


class WSGIWorkerConfigContext(WorkerConfigContext):

    def __init__(self, name=None, script=None, admin_script=None,
                 public_script=None, user=None, group=None,
                 process_weight=1.00,
                 admin_process_weight=0.25, public_process_weight=0.75):
        self.service_name = name
        self.user = user or name
        self.group = group or name
        self.script = script
        self.admin_script = admin_script
        self.public_script = public_script
        self.process_weight = process_weight
        self.admin_process_weight = admin_process_weight
        self.public_process_weight = public_process_weight

    def __call__(self):
        total_processes = _calculate_workers()
        ctxt = {
            "service_name": self.service_name,
            "user": self.user,
            "group": self.group,
            "script": self.script,
            "admin_script": self.admin_script,
            "public_script": self.public_script,
            "processes": int(math.ceil(self.process_weight * total_processes)),
            "admin_processes": int(math.ceil(self.admin_process_weight *
                                             total_processes)),
            "public_processes": int(math.ceil(self.public_process_weight *
                                              total_processes)),
            "threads": 1,
        }
        return ctxt


class ZeroMQContext(OSContextGenerator):
    interfaces = ['zeromq-configuration']

    def __call__(self):
        ctxt = {}
        if is_relation_made('zeromq-configuration', 'host'):
            for rid in relation_ids('zeromq-configuration'):
                for unit in related_units(rid):
                    ctxt['zmq_nonce'] = relation_get('nonce', unit, rid)
                    ctxt['zmq_host'] = relation_get('host', unit, rid)
                    ctxt['zmq_redis_address'] = relation_get(
                        'zmq_redis_address', unit, rid)

        return ctxt


class NotificationDriverContext(OSContextGenerator):

    def __init__(self, zmq_relation='zeromq-configuration',
                 amqp_relation='amqp'):
        """
        :param zmq_relation: Name of Zeromq relation to check
        """
        self.zmq_relation = zmq_relation
        self.amqp_relation = amqp_relation

    def __call__(self):
        ctxt = {'notifications': 'False'}
        if is_relation_made(self.amqp_relation):
            ctxt['notifications'] = "True"

        return ctxt


class SysctlContext(OSContextGenerator):
    """This context check if the 'sysctl' option exists on configuration
    then creates a file with the loaded contents"""
    def __call__(self):
        sysctl_dict = config('sysctl')
        if sysctl_dict:
            sysctl_create(sysctl_dict,
                          '/etc/sysctl.d/50-{0}.conf'.format(charm_name()))
        return {'sysctl': sysctl_dict}


class NeutronAPIContext(OSContextGenerator):
    '''
    Inspects current neutron-plugin-api relation for neutron settings. Return
    defaults if it is not present.
    '''
    interfaces = ['neutron-plugin-api']

    def __call__(self):
        self.neutron_defaults = {
            'l2_population': {
                'rel_key': 'l2-population',
                'default': False,
            },
            'overlay_network_type': {
                'rel_key': 'overlay-network-type',
                'default': 'gre',
            },
            'neutron_security_groups': {
                'rel_key': 'neutron-security-groups',
                'default': False,
            },
            'network_device_mtu': {
                'rel_key': 'network-device-mtu',
                'default': None,
            },
            'enable_dvr': {
                'rel_key': 'enable-dvr',
                'default': False,
            },
            'enable_l3ha': {
                'rel_key': 'enable-l3ha',
                'default': False,
            },
            'dns_domain': {
                'rel_key': 'dns-domain',
                'default': None,
            },
            'polling_interval': {
                'rel_key': 'polling-interval',
                'default': 2,
            },
            'rpc_response_timeout': {
                'rel_key': 'rpc-response-timeout',
                'default': 60,
            },
            'report_interval': {
                'rel_key': 'report-interval',
                'default': 30,
            },
            'enable_qos': {
                'rel_key': 'enable-qos',
                'default': False,
            },
            'enable_nsg_logging': {
                'rel_key': 'enable-nsg-logging',
                'default': False,
            },
            'enable_nfg_logging': {
                'rel_key': 'enable-nfg-logging',
                'default': False,
            },
            'enable_port_forwarding': {
                'rel_key': 'enable-port-forwarding',
                'default': False,
            },
            'enable_fwaas': {
                'rel_key': 'enable-fwaas',
                'default': False,
            },
            'global_physnet_mtu': {
                'rel_key': 'global-physnet-mtu',
                'default': 1500,
            },
            'physical_network_mtus': {
                'rel_key': 'physical-network-mtus',
                'default': None,
            },
        }
        ctxt = self.get_neutron_options({})
        for rid in relation_ids('neutron-plugin-api'):
            for unit in related_units(rid):
                rdata = relation_get(rid=rid, unit=unit)
                # The l2-population key is used by the context as a way of
                # checking if the api service on the other end is sending data
                # in a recent format.
                if 'l2-population' in rdata:
                    ctxt.update(self.get_neutron_options(rdata))

        extension_drivers = []

        if ctxt['enable_qos']:
            extension_drivers.append('qos')

        if ctxt['enable_nsg_logging']:
            extension_drivers.append('log')

        ctxt['extension_drivers'] = ','.join(extension_drivers)

        l3_extension_plugins = []

        if ctxt['enable_port_forwarding']:
            l3_extension_plugins.append('port_forwarding')

        if ctxt['enable_fwaas']:
            l3_extension_plugins.append('fwaas_v2')
            if ctxt['enable_nfg_logging']:
                l3_extension_plugins.append('fwaas_v2_log')

        ctxt['l3_extension_plugins'] = l3_extension_plugins

        return ctxt

    def get_neutron_options(self, rdata):
        settings = {}
        for nkey in self.neutron_defaults.keys():
            defv = self.neutron_defaults[nkey]['default']
            rkey = self.neutron_defaults[nkey]['rel_key']
            if rkey in rdata.keys():
                if type(defv) is bool:
                    settings[nkey] = bool_from_string(rdata[rkey])
                else:
                    settings[nkey] = rdata[rkey]
            else:
                settings[nkey] = defv
        return settings


class ExternalPortContext(NeutronPortContext):

    def __call__(self):
        ctxt = {}
        ports = config('ext-port')
        if ports:
            ports = [p.strip() for p in ports.split()]
            ports = self.resolve_ports(ports)
            if ports:
                ctxt = {"ext_port": ports[0]}
                napi_settings = NeutronAPIContext()()
                mtu = napi_settings.get('network_device_mtu')
                if mtu:
                    ctxt['ext_port_mtu'] = mtu

        return ctxt


class DataPortContext(NeutronPortContext):

    def __call__(self):
        ports = config('data-port')
        if ports:
            # Map of {bridge:port/mac}
            portmap = parse_data_port_mappings(ports)
            ports = portmap.keys()
            # Resolve provided ports or mac addresses and filter out those
            # already attached to a bridge.
            resolved = self.resolve_ports(ports)
            # Rebuild port index using resolved and filtered ports.
            normalized = {get_nic_hwaddr(port): port for port in resolved
                          if port not in ports}
            normalized.update({port: port for port in resolved
                               if port in ports})
            if resolved:
                return {normalized[port]: bridge for port, bridge in
                        six.iteritems(portmap) if port in normalized.keys()}

        return None


class PhyNICMTUContext(DataPortContext):

    def __call__(self):
        ctxt = {}
        mappings = super(PhyNICMTUContext, self).__call__()
        if mappings and mappings.keys():
            ports = sorted(mappings.keys())
            napi_settings = NeutronAPIContext()()
            mtu = napi_settings.get('network_device_mtu')
            all_ports = set()
            # If any of ports is a vlan device, its underlying device must have
            # mtu applied first.
            for port in ports:
                for lport in glob.glob("/sys/class/net/%s/lower_*" % port):
                    lport = os.path.basename(lport)
                    all_ports.add(lport.split('_')[1])

            all_ports = list(all_ports)
            all_ports.extend(ports)
            if mtu:
                ctxt["devs"] = '\\n'.join(all_ports)
                ctxt['mtu'] = mtu

        return ctxt


class NetworkServiceContext(OSContextGenerator):

    def __init__(self, rel_name='quantum-network-service'):
        self.rel_name = rel_name
        self.interfaces = [rel_name]

    def __call__(self):
        for rid in relation_ids(self.rel_name):
            for unit in related_units(rid):
                rdata = relation_get(rid=rid, unit=unit)
                ctxt = {
                    'keystone_host': rdata.get('keystone_host'),
                    'service_port': rdata.get('service_port'),
                    'auth_port': rdata.get('auth_port'),
                    'service_tenant': rdata.get('service_tenant'),
                    'service_username': rdata.get('service_username'),
                    'service_password': rdata.get('service_password'),
                    'quantum_host': rdata.get('quantum_host'),
                    'quantum_port': rdata.get('quantum_port'),
                    'quantum_url': rdata.get('quantum_url'),
                    'region': rdata.get('region'),
                    'service_protocol':
                    rdata.get('service_protocol') or 'http',
                    'auth_protocol':
                    rdata.get('auth_protocol') or 'http',
                    'api_version':
                    rdata.get('api_version') or '2.0',
                }
                if self.context_complete(ctxt):
                    return ctxt
        return {}


class InternalEndpointContext(OSContextGenerator):
    """Internal endpoint context.

    This context provides the endpoint type used for communication between
    services e.g. between Nova and Cinder internally. Openstack uses Public
    endpoints by default so this allows admins to optionally use internal
    endpoints.
    """
    def __call__(self):
        return {'use_internal_endpoints': config('use-internal-endpoints')}


class VolumeAPIContext(InternalEndpointContext):
    """Volume API context.

    This context provides information regarding the volume endpoint to use
    when communicating between services. It determines which version of the
    API is appropriate for use.

    This value will be determined in the resulting context dictionary
    returned from calling the VolumeAPIContext object. Information provided
    by this context is as follows:

        volume_api_version: the volume api version to use, currently
            'v2' or 'v3'
        volume_catalog_info: the information to use for a cinder client
            configuration that consumes API endpoints from the keystone
            catalog. This is defined as the type:name:endpoint_type string.
    """
    # FIXME(wolsen) This implementation is based on the provider being able
    # to specify the package version to check but does not guarantee that the
    # volume service api version selected is available. In practice, it is
    # quite likely the volume service *is* providing the v3 volume service.
    # This should be resolved when the service-discovery spec is implemented.
    def __init__(self, pkg):
        """
        Creates a new VolumeAPIContext for use in determining which version
        of the Volume API should be used for communication. A package codename
        should be supplied for determining the currently installed OpenStack
        version.

        :param pkg: the package codename to use in order to determine the
            component version (e.g. nova-common). See
            charmhelpers.contrib.openstack.utils.PACKAGE_CODENAMES for more.
        """
        super(VolumeAPIContext, self).__init__()
        self._ctxt = None
        if not pkg:
            raise ValueError('package name must be provided in order to '
                             'determine current OpenStack version.')
        self.pkg = pkg

    @property
    def ctxt(self):
        if self._ctxt is not None:
            return self._ctxt
        self._ctxt = self._determine_ctxt()
        return self._ctxt

    def _determine_ctxt(self):
        """Determines the Volume API endpoint information.

        Determines the appropriate version of the API that should be used
        as well as the catalog_info string that would be supplied. Returns
        a dict containing the volume_api_version and the volume_catalog_info.
        """
        rel = os_release(self.pkg)
        version = '2'
        if CompareOpenStackReleases(rel) >= 'pike':
            version = '3'

        service_type = 'volumev{version}'.format(version=version)
        service_name = 'cinderv{version}'.format(version=version)
        endpoint_type = 'publicURL'
        if config('use-internal-endpoints'):
            endpoint_type = 'internalURL'
        catalog_info = '{type}:{name}:{endpoint}'.format(
            type=service_type, name=service_name, endpoint=endpoint_type)

        return {
            'volume_api_version': version,
            'volume_catalog_info': catalog_info,
        }

    def __call__(self):
        return self.ctxt


class AppArmorContext(OSContextGenerator):
    """Base class for apparmor contexts."""

    def __init__(self, profile_name=None):
        self._ctxt = None
        self.aa_profile = profile_name
        self.aa_utils_packages = ['apparmor-utils']

    @property
    def ctxt(self):
        if self._ctxt is not None:
            return self._ctxt
        self._ctxt = self._determine_ctxt()
        return self._ctxt

    def _determine_ctxt(self):
        """
        Validate aa-profile-mode settings is disable, enforce, or complain.

        :return ctxt: Dictionary of the apparmor profile or None
        """
        if config('aa-profile-mode') in ['disable', 'enforce', 'complain']:
            ctxt = {'aa_profile_mode': config('aa-profile-mode'),
                    'ubuntu_release': lsb_release()['DISTRIB_RELEASE']}
            if self.aa_profile:
                ctxt['aa_profile'] = self.aa_profile
        else:
            ctxt = None
        return ctxt

    def __call__(self):
        return self.ctxt

    def install_aa_utils(self):
        """
        Install packages required for apparmor configuration.
        """
        log("Installing apparmor utils.")
        ensure_packages(self.aa_utils_packages)

    def manually_disable_aa_profile(self):
        """
        Manually disable an apparmor profile.

        If aa-profile-mode is set to disabled (default) this is required as the
        template has been written but apparmor is yet unaware of the profile
        and aa-disable aa-profile fails. Without this the profile would kick
        into enforce mode on the next service restart.

        """
        profile_path = '/etc/apparmor.d'
        disable_path = '/etc/apparmor.d/disable'
        if not os.path.lexists(os.path.join(disable_path, self.aa_profile)):
            os.symlink(os.path.join(profile_path, self.aa_profile),
                       os.path.join(disable_path, self.aa_profile))

    def setup_aa_profile(self):
        """
        Setup an apparmor profile.
        The ctxt dictionary will contain the apparmor profile mode and
        the apparmor profile name.
        Makes calls out to aa-disable, aa-complain, or aa-enforce to setup
        the apparmor profile.
        """
        self()
        if not self.ctxt:
            log("Not enabling apparmor Profile")
            return
        self.install_aa_utils()
        cmd = ['aa-{}'.format(self.ctxt['aa_profile_mode'])]
        cmd.append(self.ctxt['aa_profile'])
        log("Setting up the apparmor profile for {} in {} mode."
            "".format(self.ctxt['aa_profile'], self.ctxt['aa_profile_mode']))
        try:
            check_call(cmd)
        except CalledProcessError as e:
            # If aa-profile-mode is set to disabled (default) manual
            # disabling is required as the template has been written but
            # apparmor is yet unaware of the profile and aa-disable aa-profile
            # fails. If aa-disable learns to read profile files first this can
            # be removed.
            if self.ctxt['aa_profile_mode'] == 'disable':
                log("Manually disabling the apparmor profile for {}."
                    "".format(self.ctxt['aa_profile']))
                self.manually_disable_aa_profile()
                return
            status_set('blocked', "Apparmor profile {} failed to be set to {}."
                                  "".format(self.ctxt['aa_profile'],
                                            self.ctxt['aa_profile_mode']))
            raise e


class MemcacheContext(OSContextGenerator):
    """Memcache context

    This context provides options for configuring a local memcache client and
    server for both IPv4 and IPv6
    """

    def __init__(self, package=None):
        """
        @param package: Package to examine to extrapolate OpenStack release.
                        Used when charms have no openstack-origin config
                        option (ie subordinates)
        """
        self.package = package

    def __call__(self):
        ctxt = {}
        ctxt['use_memcache'] = enable_memcache(package=self.package)
        if ctxt['use_memcache']:
            # Trusty version of memcached does not support ::1 as a listen
            # address so use host file entry instead
            release = lsb_release()['DISTRIB_CODENAME'].lower()
            if is_ipv6_disabled():
                if CompareHostReleases(release) > 'trusty':
                    ctxt['memcache_server'] = '127.0.0.1'
                else:
                    ctxt['memcache_server'] = 'localhost'
                ctxt['memcache_server_formatted'] = '127.0.0.1'
                ctxt['memcache_port'] = '11211'
                ctxt['memcache_url'] = '{}:{}'.format(
                    ctxt['memcache_server_formatted'],
                    ctxt['memcache_port'])
            else:
                if CompareHostReleases(release) > 'trusty':
                    ctxt['memcache_server'] = '::1'
                else:
                    ctxt['memcache_server'] = 'ip6-localhost'
                ctxt['memcache_server_formatted'] = '[::1]'
                ctxt['memcache_port'] = '11211'
                ctxt['memcache_url'] = 'inet6:{}:{}'.format(
                    ctxt['memcache_server_formatted'],
                    ctxt['memcache_port'])
        return ctxt


class EnsureDirContext(OSContextGenerator):
    '''
    Serves as a generic context to create a directory as a side-effect.

    Useful for software that supports drop-in files (.d) in conjunction
    with config option-based templates. Examples include:
        * OpenStack oslo.policy drop-in files;
        * systemd drop-in config files;
        * other software that supports overriding defaults with .d files

    Another use-case is when a subordinate generates a configuration for
    primary to render in a separate directory.

    Some software requires a user to create a target directory to be
    scanned for drop-in files with a specific format. This is why this
    context is needed to do that before rendering a template.
    '''

    def __init__(self, dirname, **kwargs):
        '''Used merely to ensure that a given directory exists.'''
        self.dirname = dirname
        self.kwargs = kwargs

    def __call__(self):
        mkdir(self.dirname, **self.kwargs)
        return {}


class VersionsContext(OSContextGenerator):
    """Context to return the openstack and operating system versions.

    """
    def __init__(self, pkg='python-keystone'):
        """Initialise context.

        :param pkg: Package to extrapolate openstack version from.
        :type pkg: str
        """
        self.pkg = pkg

    def __call__(self):
        ostack = os_release(self.pkg)
        osystem = lsb_release()['DISTRIB_CODENAME'].lower()
        return {
            'openstack_release': ostack,
            'operating_system_release': osystem}


class LogrotateContext(OSContextGenerator):
    """Common context generator for logrotate."""

    def __init__(self, location, interval, count):
        """
        :param location: Absolute path for the logrotate config file
        :type location: str
        :param interval: The interval for the rotations. Valid values are
                         'daily', 'weekly', 'monthly', 'yearly'
        :type interval: str
        :param count: The logrotate count option configures the 'count' times
                      the log files are being rotated before being
        :type count: int
        """
        self.location = location
        self.interval = interval
        self.count = 'rotate {}'.format(count)

    def __call__(self):
        ctxt = {
            'logrotate_logs_location': self.location,
            'logrotate_interval': self.interval,
            'logrotate_count': self.count,
        }
        return ctxt


class HostInfoContext(OSContextGenerator):
    """Context to provide host information."""

    def __init__(self, use_fqdn_hint_cb=None):
        """Initialize HostInfoContext

        :param use_fqdn_hint_cb: Callback whose return value used to populate
                                 `use_fqdn_hint`
        :type use_fqdn_hint_cb: Callable[[], bool]
        """
        # Store callback used to get hint for whether FQDN should be used

        # Depending on the workload a charm manages, the use of FQDN vs.
        # shortname may be a deploy-time decision, i.e. behaviour can not
        # change on charm upgrade or post-deployment configuration change.

        # The hint is passed on as a flag in the context to allow the decision
        # to be made in the Jinja2 configuration template.
        self.use_fqdn_hint_cb = use_fqdn_hint_cb

    def _get_canonical_name(self, name=None):
        """Get the official FQDN of the host

        The implementation of ``socket.getfqdn()`` in the standard Python
        library does not exhaust all methods of getting the official name
        of a host ref Python issue https://bugs.python.org/issue5004

        This function mimics the behaviour of a call to ``hostname -f`` to
        get the official FQDN but returns an empty string if it is
        unsuccessful.

        :param name: Shortname to get FQDN on
        :type name: Optional[str]
        :returns: The official FQDN for host or empty string ('')
        :rtype: str
        """
        name = name or socket.gethostname()
        fqdn = ''

        if six.PY2:
            exc = socket.error
        else:
            exc = OSError

        try:
            addrs = socket.getaddrinfo(
                name, None, 0, socket.SOCK_DGRAM, 0, socket.AI_CANONNAME)
        except exc:
            pass
        else:
            for addr in addrs:
                if addr[3]:
                    if '.' in addr[3]:
                        fqdn = addr[3]
                    break
        return fqdn

    def __call__(self):
        name = socket.gethostname()
        ctxt = {
            'host_fqdn': self._get_canonical_name(name) or name,
            'host': name,
            'use_fqdn_hint': (
                self.use_fqdn_hint_cb() if self.use_fqdn_hint_cb else False)
        }
        return ctxt


def validate_ovs_use_veth(*args, **kwargs):
    """Validate OVS use veth setting for dhcp agents

    The ovs_use_veth setting is considered immutable as it will break existing
    deployments. Historically, we set ovs_use_veth=True in dhcp_agent.ini. It
    turns out this is no longer necessary. Ideally, all new deployments would
    have this set to False.

    This function validates that the config value does not conflict with
    previously deployed settings in dhcp_agent.ini.

    See LP Bug#1831935 for details.

    :returns: Status state and message
    :rtype: Union[(None, None), (string, string)]
    """
    existing_ovs_use_veth = (
        DHCPAgentContext.get_existing_ovs_use_veth())
    config_ovs_use_veth = DHCPAgentContext.parse_ovs_use_veth()

    # Check settings are set and not None
    if existing_ovs_use_veth is not None and config_ovs_use_veth is not None:
        # Check for mismatch between existing config ini and juju config
        if existing_ovs_use_veth != config_ovs_use_veth:
            # Stop the line to avoid breakage
            msg = (
                "The existing setting for dhcp_agent.ini ovs_use_veth, {}, "
                "does not match the juju config setting, {}. This may lead to "
                "VMs being unable to receive a DHCP IP. Either change the "
                "juju config setting or dhcp agents may need to be recreated."
                .format(existing_ovs_use_veth, config_ovs_use_veth))
            log(msg, ERROR)
            return (
                "blocked",
                "Mismatched existing and configured ovs-use-veth. See log.")

    # Everything is OK
    return None, None


class DHCPAgentContext(OSContextGenerator):

    def __call__(self):
        """Return the DHCPAGentContext.

        Return all DHCP Agent INI related configuration.
        ovs unit is attached to (as a subordinate) and the 'dns_domain' from
        the neutron-plugin-api relations (if one is set).

        :returns: Dictionary context
        :rtype: Dict
        """

        ctxt = {}
        dnsmasq_flags = config('dnsmasq-flags')
        if dnsmasq_flags:
            ctxt['dnsmasq_flags'] = config_flags_parser(dnsmasq_flags)
        ctxt['dns_servers'] = config('dns-servers')

        neutron_api_settings = NeutronAPIContext()()

        ctxt['debug'] = config('debug')
        ctxt['instance_mtu'] = config('instance-mtu')
        ctxt['ovs_use_veth'] = self.get_ovs_use_veth()

        ctxt['enable_metadata_network'] = config('enable-metadata-network')
        ctxt['enable_isolated_metadata'] = config('enable-isolated-metadata')

        if neutron_api_settings.get('dns_domain'):
            ctxt['dns_domain'] = neutron_api_settings.get('dns_domain')

        # Override user supplied config for these plugins as these settings are
        # mandatory
        if config('plugin') in ['nvp', 'nsx', 'n1kv']:
            ctxt['enable_metadata_network'] = True
            ctxt['enable_isolated_metadata'] = True

        ctxt['append_ovs_config'] = False
        cmp_release = CompareOpenStackReleases(
            os_release('neutron-common', base='icehouse'))
        if cmp_release >= 'queens' and config('enable-dpdk'):
            ctxt['append_ovs_config'] = True

        return ctxt

    @staticmethod
    def get_existing_ovs_use_veth():
        """Return existing ovs_use_veth setting from dhcp_agent.ini.

        :returns: Boolean value of existing ovs_use_veth setting or None
        :rtype: Optional[Bool]
        """
        DHCP_AGENT_INI = "/etc/neutron/dhcp_agent.ini"
        existing_ovs_use_veth = None
        # If there is a dhcp_agent.ini file read the current setting
        if os.path.isfile(DHCP_AGENT_INI):
            # config_ini does the right thing and returns None if the setting is
            # commented.
            existing_ovs_use_veth = (
                config_ini(DHCP_AGENT_INI)["DEFAULT"].get("ovs_use_veth"))
        # Convert to Bool if necessary
        if isinstance(existing_ovs_use_veth, six.string_types):
            return bool_from_string(existing_ovs_use_veth)
        return existing_ovs_use_veth

    @staticmethod
    def parse_ovs_use_veth():
        """Parse the ovs-use-veth config setting.

        Parse the string config setting for ovs-use-veth and return a boolean
        or None.

        bool_from_string will raise a ValueError if the string is not falsy or
        truthy.

        :raises: ValueError for invalid input
        :returns: Boolean value of ovs-use-veth or None
        :rtype: Optional[Bool]
        """
        _config = config("ovs-use-veth")
        # An unset parameter returns None. Just in case we will also check for
        # an empty string: "". Ironically, (the problem we are trying to avoid)
        # "False" returns True and "" returns False.
        if _config is None or not _config:
            # Return None
            return
        # bool_from_string handles many variations of true and false strings
        # as well as upper and lowercases including:
        # ['y', 'yes', 'true', 't', 'on', 'n', 'no', 'false', 'f', 'off']
        return bool_from_string(_config)

    def get_ovs_use_veth(self):
        """Return correct ovs_use_veth setting for use in dhcp_agent.ini.

        Get the right value from config or existing dhcp_agent.ini file.
        Existing has precedence. Attempt to default to "False" without
        disrupting existing deployments. Handle existing deployments and
        upgrades safely. See LP Bug#1831935

        :returns: Value to use for ovs_use_veth setting
        :rtype: Bool
        """
        _existing = self.get_existing_ovs_use_veth()
        if _existing is not None:
            return _existing

        _config = self.parse_ovs_use_veth()
        if _config is None:
            # New better default
            return False
        else:
            return _config


EntityMac = collections.namedtuple('EntityMac', ['entity', 'mac'])


def resolve_pci_from_mapping_config(config_key):
    """Resolve local PCI devices from MAC addresses in mapping config.

    Note that this function keeps record of mac->PCI address lookups
    in the local unit db as the devices will disappaear from the system
    once bound.

    :param config_key: Configuration option key to parse data from
    :type config_key: str
    :returns: PCI device address to Tuple(entity, mac) map
    :rtype: collections.OrderedDict[str,Tuple[str,str]]
    """
    devices = pci.PCINetDevices()
    resolved_devices = collections.OrderedDict()
    db = kv()
    # Note that ``parse_data_port_mappings`` returns Dict regardless of input
    for mac, entity in parse_data_port_mappings(config(config_key)).items():
        pcidev = devices.get_device_from_mac(mac)
        if pcidev:
            # NOTE: store mac->pci allocation as post binding
            #       it disappears from PCIDevices.
            db.set(mac, pcidev.pci_address)
            db.flush()

        pci_address = db.get(mac)
        if pci_address:
            resolved_devices[pci_address] = EntityMac(entity, mac)

    return resolved_devices


class DPDKDeviceContext(OSContextGenerator):

    def __init__(self, driver_key=None, bridges_key=None, bonds_key=None):
        """Initialize DPDKDeviceContext.

        :param driver_key: Key to use when retrieving driver config.
        :type driver_key: str
        :param bridges_key: Key to use when retrieving bridge config.
        :type bridges_key: str
        :param bonds_key: Key to use when retrieving bonds config.
        :type bonds_key: str
        """
        self.driver_key = driver_key or 'dpdk-driver'
        self.bridges_key = bridges_key or 'data-port'
        self.bonds_key = bonds_key or 'dpdk-bond-mappings'

    def __call__(self):
        """Populate context.

        :returns: context
        :rtype: Dict[str,Union[str,collections.OrderedDict[str,str]]]
        """
        driver = config(self.driver_key)
        if driver is None:
            return {}
        # Resolve PCI devices for both directly used devices (_bridges)
        # and devices for use in dpdk bonds (_bonds)
        pci_devices = resolve_pci_from_mapping_config(self.bridges_key)
        pci_devices.update(resolve_pci_from_mapping_config(self.bonds_key))
        return {'devices': pci_devices,
                'driver': driver}


class OVSDPDKDeviceContext(OSContextGenerator):

    def __init__(self, bridges_key=None, bonds_key=None):
        """Initialize OVSDPDKDeviceContext.

        :param bridges_key: Key to use when retrieving bridge config.
        :type bridges_key: str
        :param bonds_key: Key to use when retrieving bonds config.
        :type bonds_key: str
        """
        self.bridges_key = bridges_key or 'data-port'
        self.bonds_key = bonds_key or 'dpdk-bond-mappings'

    @staticmethod
    def _parse_cpu_list(cpulist):
        """Parses a linux cpulist for a numa node

        :returns: list of cores
        :rtype: List[int]
        """
        cores = []
        ranges = cpulist.split(',')
        for cpu_range in ranges:
            if "-" in cpu_range:
                cpu_min_max = cpu_range.split('-')
                cores += range(int(cpu_min_max[0]),
                               int(cpu_min_max[1]) + 1)
            else:
                cores.append(int(cpu_range))
        return cores

    def _numa_node_cores(self):
        """Get map of numa node -> cpu core

        :returns: map of numa node -> cpu core
        :rtype: Dict[str,List[int]]
        """
        nodes = {}
        node_regex = '/sys/devices/system/node/node*'
        for node in glob.glob(node_regex):
            index = node.lstrip('/sys/devices/system/node/node')
            with open(os.path.join(node, 'cpulist')) as cpulist:
                nodes[index] = self._parse_cpu_list(cpulist.read().strip())
        return nodes

    def cpu_mask(self):
        """Get hex formatted CPU mask

        The mask is based on using the first config:dpdk-socket-cores
        cores of each NUMA node in the unit.
        :returns: hex formatted CPU mask
        :rtype: str
        """
        return self.cpu_masks()['dpdk_lcore_mask']

    def cpu_masks(self):
        """Get hex formatted CPU masks

        The mask is based on using the first config:dpdk-socket-cores
        cores of each NUMA node in the unit, followed by the
        next config:pmd-socket-cores

        :returns: Dict of hex formatted CPU masks
        :rtype: Dict[str, str]
        """
        num_lcores = config('dpdk-socket-cores')
        pmd_cores = config('pmd-socket-cores')
        lcore_mask = 0
        pmd_mask = 0
        for cores in self._numa_node_cores().values():
            for core in cores[:num_lcores]:
                lcore_mask = lcore_mask | 1 << core
            for core in cores[num_lcores:][:pmd_cores]:
                pmd_mask = pmd_mask | 1 << core
        return {
            'pmd_cpu_mask': format(pmd_mask, '#04x'),
            'dpdk_lcore_mask': format(lcore_mask, '#04x')}

    def socket_memory(self):
        """Formatted list of socket memory configuration per socket.

        :returns: socket memory configuration per socket.
        :rtype: str
        """
        lscpu_out = check_output(
            ['lscpu', '-p=socket']).decode('UTF-8').strip()
        sockets = set()
        for line in lscpu_out.split('\n'):
            try:
                sockets.add(int(line))
            except ValueError:
                # lscpu output is headed by comments so ignore them.
                pass
        sm_size = config('dpdk-socket-memory')
        mem_list = [str(sm_size) for _ in sockets]
        if mem_list:
            return ','.join(mem_list)
        else:
            return str(sm_size)

    def devices(self):
        """List of PCI devices for use by DPDK

        :returns: List of PCI devices for use by DPDK
        :rtype: collections.OrderedDict[str,str]
        """
        pci_devices = resolve_pci_from_mapping_config(self.bridges_key)
        pci_devices.update(resolve_pci_from_mapping_config(self.bonds_key))
        return pci_devices

    def _formatted_whitelist(self, flag):
        """Flag formatted list of devices to whitelist

        :param flag: flag format to use
        :type flag: str
        :rtype: str
        """
        whitelist = []
        for device in self.devices():
            whitelist.append(flag.format(device=device))
        return ' '.join(whitelist)

    def device_whitelist(self):
        """Formatted list of devices to whitelist for dpdk

        using the old style '-w' flag

        :returns: devices to whitelist prefixed by '-w '
        :rtype: str
        """
        return self._formatted_whitelist('-w {device}')

    def pci_whitelist(self):
        """Formatted list of devices to whitelist for dpdk

        using the new style '--pci-whitelist' flag

        :returns: devices to whitelist prefixed by '--pci-whitelist '
        :rtype: str
        """
        return self._formatted_whitelist('--pci-whitelist {device}')

    def __call__(self):
        """Populate context.

        :returns: context
        :rtype: Dict[str,Union[bool,str]]
        """
        ctxt = {}
        whitelist = self.device_whitelist()
        if whitelist:
            ctxt['dpdk_enabled'] = config('enable-dpdk')
            ctxt['device_whitelist'] = self.device_whitelist()
            ctxt['socket_memory'] = self.socket_memory()
            ctxt['cpu_mask'] = self.cpu_mask()
        return ctxt


class BridgePortInterfaceMap(object):
    """Build a map of bridge ports and interfaces from charm configuration.

    NOTE: the handling of this detail in the charm is pre-deprecated.

    The long term goal is for network connectivity detail to be modelled in
    the server provisioning layer (such as MAAS) which in turn will provide
    a Netplan YAML description that will be used to drive Open vSwitch.

    Until we get to that reality the charm will need to configure this
    detail based on application level configuration options.

    There is a established way of mapping interfaces to ports and bridges
    in the ``neutron-openvswitch`` and ``neutron-gateway`` charms and we
    will carry that forward.

    The relationship between bridge, port and interface(s).
             +--------+
             | bridge |
             +--------+
                 |
         +----------------+
         | port aka. bond |
         +----------------+
               |   |
              +-+ +-+
              |i| |i|
              |n| |n|
              |t| |t|
              |0| |N|
              +-+ +-+
    """
    class interface_type(enum.Enum):
        """Supported interface types.

        Supported interface types can be found in the ``iface_types`` column
        in the ``Open_vSwitch`` table on a running system.
        """
        dpdk = 'dpdk'
        internal = 'internal'
        system = 'system'

        def __str__(self):
            """Return string representation of value.

            :returns: string representation of value.
            :rtype: str
            """
            return self.value

    def __init__(self, bridges_key=None, bonds_key=None, enable_dpdk_key=None,
                 global_mtu=None):
        """Initialize map.

        :param bridges_key: Name of bridge:interface/port map config key
                            (default: 'data-port')
        :type bridges_key: Optional[str]
        :param bonds_key: Name of port-name:interface map config key
                          (default: 'dpdk-bond-mappings')
        :type bonds_key: Optional[str]
        :param enable_dpdk_key: Name of DPDK toggle config key
                                (default: 'enable-dpdk')
        :type enable_dpdk_key: Optional[str]
        :param global_mtu: Set a MTU on all interfaces at map initialization.

            The default is to have Open vSwitch get this from the underlying
            interface as set up by bare metal provisioning.

            Note that you can augment the MTU on an individual interface basis
            like this:

            ifdatamap = bpi.get_ifdatamap(bridge, port)
            ifdatamap = {
                port: {
                    **ifdata,
                    **{'mtu-request': my_individual_mtu_map[port]},
                }
                for port, ifdata in ifdatamap.items()
            }
        :type global_mtu: Optional[int]
        """
        bridges_key = bridges_key or 'data-port'
        bonds_key = bonds_key or 'dpdk-bond-mappings'
        enable_dpdk_key = enable_dpdk_key or 'enable-dpdk'
        self._map = collections.defaultdict(
            lambda: collections.defaultdict(dict))
        self._ifname_mac_map = collections.defaultdict(list)
        self._mac_ifname_map = {}
        self._mac_pci_address_map = {}

        # First we iterate over the list of physical interfaces visible to the
        # system and update interface name to mac and mac to interface name map
        for ifname in list_nics():
            if not is_phy_iface(ifname):
                continue
            mac = get_nic_hwaddr(ifname)
            self._ifname_mac_map[ifname] = [mac]
            self._mac_ifname_map[mac] = ifname

            # check if interface is part of a linux bond
            _bond_name = get_bond_master(ifname)
            if _bond_name and _bond_name != ifname:
                log('Add linux bond "{}" to map for physical interface "{}" '
                    'with mac "{}".'.format(_bond_name, ifname, mac),
                    level=DEBUG)
                # for bonds we want to be able to get a list of the mac
                # addresses for the physical interfaces the bond is made up of.
                if self._ifname_mac_map.get(_bond_name):
                    self._ifname_mac_map[_bond_name].append(mac)
                else:
                    self._ifname_mac_map[_bond_name] = [mac]

        # In light of the pre-deprecation notice in the docstring of this
        # class we will expose the ability to configure OVS bonds as a
        # DPDK-only feature, but generally use the data structures internally.
        if config(enable_dpdk_key):
            # resolve PCI address of interfaces listed in the bridges and bonds
            # charm configuration options.  Note that for already bound
            # interfaces the helper will retrieve MAC address from the unit
            # KV store as the information is no longer available in sysfs.
            _pci_bridge_mac = resolve_pci_from_mapping_config(
                bridges_key)
            _pci_bond_mac = resolve_pci_from_mapping_config(
                bonds_key)

            for pci_address, bridge_mac in _pci_bridge_mac.items():
                if bridge_mac.mac in self._mac_ifname_map:
                    # if we already have the interface name in our map it is
                    # visible to the system and therefore not bound to DPDK
                    continue
                ifname = 'dpdk-{}'.format(
                    hashlib.sha1(
                        pci_address.encode('UTF-8')).hexdigest()[:7])
                self._ifname_mac_map[ifname] = [bridge_mac.mac]
                self._mac_ifname_map[bridge_mac.mac] = ifname
                self._mac_pci_address_map[bridge_mac.mac] = pci_address

            for pci_address, bond_mac in _pci_bond_mac.items():
                # for bonds we want to be able to get a list of macs from
                # the bond name and also get at the interface name made up
                # of the hash of the PCI address
                ifname = 'dpdk-{}'.format(
                    hashlib.sha1(
                        pci_address.encode('UTF-8')).hexdigest()[:7])
                self._ifname_mac_map[bond_mac.entity].append(bond_mac.mac)
                self._mac_ifname_map[bond_mac.mac] = ifname
                self._mac_pci_address_map[bond_mac.mac] = pci_address

        config_bridges = config(bridges_key) or ''
        for bridge, ifname_or_mac in (
                pair.split(':', 1)
                for pair in config_bridges.split()):
            if ':' in ifname_or_mac:
                try:
                    ifname = self.ifname_from_mac(ifname_or_mac)
                except KeyError:
                    # The interface is destined for a different unit in the
                    # deployment.
                    continue
                macs = [ifname_or_mac]
            else:
                ifname = ifname_or_mac
                macs = self.macs_from_ifname(ifname_or_mac)

            portname = ifname
            for mac in macs:
                try:
                    pci_address = self.pci_address_from_mac(mac)
                    iftype = self.interface_type.dpdk
                    ifname = self.ifname_from_mac(mac)
                except KeyError:
                    pci_address = None
                    iftype = self.interface_type.system

                self.add_interface(
                    bridge, portname, ifname, iftype, pci_address, global_mtu)

            if not macs:
                # We have not mapped the interface and it is probably some sort
                # of virtual interface. Our user have put it in the config with
                # a purpose so let's carry out their wish. LP: #1884743
                log('Add unmapped interface from config: name "{}" bridge "{}"'
                    .format(ifname, bridge),
                    level=DEBUG)
                self.add_interface(
                    bridge, ifname, ifname, self.interface_type.system, None,
                    global_mtu)

    def __getitem__(self, key):
        """Provide a Dict-like interface, get value of item.

        :param key: Key to look up value from.
        :type key: any
        :returns: Value
        :rtype: any
        """
        return self._map.__getitem__(key)

    def __iter__(self):
        """Provide a Dict-like interface, iterate over keys.

        :returns: Iterator
        :rtype: Iterator[any]
        """
        return self._map.__iter__()

    def __len__(self):
        """Provide a Dict-like interface, measure the length of internal map.

        :returns: Length
        :rtype: int
        """
        return len(self._map)

    def items(self):
        """Provide a Dict-like interface, iterate over items.

        :returns: Key Value pairs
        :rtype: Iterator[any, any]
        """
        return self._map.items()

    def keys(self):
        """Provide a Dict-like interface, iterate over keys.

        :returns: Iterator
        :rtype: Iterator[any]
        """
        return self._map.keys()

    def ifname_from_mac(self, mac):
        """
        :returns: Name of interface
        :rtype: str
        :raises: KeyError
        """
        return (get_bond_master(self._mac_ifname_map[mac]) or
                self._mac_ifname_map[mac])

    def macs_from_ifname(self, ifname):
        """
        :returns: List of hardware address (MAC) of interface
        :rtype: List[str]
        :raises: KeyError
        """
        return self._ifname_mac_map[ifname]

    def pci_address_from_mac(self, mac):
        """
        :param mac: Hardware address (MAC) of interface
        :type mac: str
        :returns: PCI address of device associated with mac
        :rtype: str
        :raises: KeyError
        """
        return self._mac_pci_address_map[mac]

    def add_interface(self, bridge, port, ifname, iftype,
                      pci_address, mtu_request):
        """Add an interface to the map.

        :param bridge: Name of bridge on which the bond will be added
        :type bridge: str
        :param port: Name of port which will represent the bond on bridge
        :type port: str
        :param ifname: Name of interface that will make up the bonded port
        :type ifname: str
        :param iftype: Type of interface
        :type iftype: BridgeBondMap.interface_type
        :param pci_address: PCI address of interface
        :type pci_address: Optional[str]
        :param mtu_request: MTU to request for interface
        :type mtu_request: Optional[int]
        """
        self._map[bridge][port][ifname] = {
            'type': str(iftype),
        }
        if pci_address:
            self._map[bridge][port][ifname].update({
                'pci-address': pci_address,
            })
        if mtu_request is not None:
            self._map[bridge][port][ifname].update({
                'mtu-request': str(mtu_request)
            })

    def get_ifdatamap(self, bridge, port):
        """Get structure suitable for charmhelpers.contrib.network.ovs helpers.

        :param bridge: Name of bridge on which the port will be added
        :type bridge: str
        :param port: Name of port which will represent one or more interfaces
        :type port: str
        """
        for _bridge, _ports in self.items():
            for _port, _interfaces in _ports.items():
                if _bridge == bridge and _port == port:
                    ifdatamap = {}
                    for name, data in _interfaces.items():
                        ifdatamap.update({
                            name: {
                                'type': data['type'],
                            },
                        })
                        if data.get('mtu-request') is not None:
                            ifdatamap[name].update({
                                'mtu_request': data['mtu-request'],
                            })
                        if data.get('pci-address'):
                            ifdatamap[name].update({
                                'options': {
                                    'dpdk-devargs': data['pci-address'],
                                },
                            })
                    return ifdatamap


class BondConfig(object):
    """Container and helpers for bond configuration options.

    Data is put into a dictionary and a convenient config get interface is
    provided.
    """

    DEFAULT_LACP_CONFIG = {
        'mode': 'balance-tcp',
        'lacp': 'active',
        'lacp-time': 'fast'
    }
    ALL_BONDS = 'ALL_BONDS'

    BOND_MODES = ['active-backup', 'balance-slb', 'balance-tcp']
    BOND_LACP = ['active', 'passive', 'off']
    BOND_LACP_TIME = ['fast', 'slow']

    def __init__(self, config_key=None):
        """Parse specified configuration option.

        :param config_key: Configuration key to retrieve data from
                           (default: ``dpdk-bond-config``)
        :type config_key: Optional[str]
        """
        self.config_key = config_key or 'dpdk-bond-config'

        self.lacp_config = {
            self.ALL_BONDS: copy.deepcopy(self.DEFAULT_LACP_CONFIG)
        }

        lacp_config = config(self.config_key)
        if lacp_config:
            lacp_config_map = lacp_config.split()
            for entry in lacp_config_map:
                bond, entry = entry.partition(':')[0:3:2]
                if not bond:
                    bond = self.ALL_BONDS

                mode, entry = entry.partition(':')[0:3:2]
                if not mode:
                    mode = self.DEFAULT_LACP_CONFIG['mode']
                assert mode in self.BOND_MODES, \
                    "Bond mode {} is invalid".format(mode)

                lacp, entry = entry.partition(':')[0:3:2]
                if not lacp:
                    lacp = self.DEFAULT_LACP_CONFIG['lacp']
                assert lacp in self.BOND_LACP, \
                    "Bond lacp {} is invalid".format(lacp)

                lacp_time, entry = entry.partition(':')[0:3:2]
                if not lacp_time:
                    lacp_time = self.DEFAULT_LACP_CONFIG['lacp-time']
                assert lacp_time in self.BOND_LACP_TIME, \
                    "Bond lacp-time {} is invalid".format(lacp_time)

                self.lacp_config[bond] = {
                    'mode': mode,
                    'lacp': lacp,
                    'lacp-time': lacp_time
                }

    def get_bond_config(self, bond):
        """Get the LACP configuration for a bond

        :param bond: the bond name
        :return: a dictionary with the configuration of the bond
        :rtype: Dict[str,Dict[str,str]]
        """
        return self.lacp_config.get(bond, self.lacp_config[self.ALL_BONDS])

    def get_ovs_portdata(self, bond):
        """Get structure suitable for charmhelpers.contrib.network.ovs helpers.

        :param bond: the bond name
        :return: a dictionary with the configuration of the bond
        :rtype: Dict[str,Union[str,Dict[str,str]]]
        """
        bond_config = self.get_bond_config(bond)
        return {
            'bond_mode': bond_config['mode'],
            'lacp': bond_config['lacp'],
            'other_config': {
                'lacp-time': bond_config['lacp-time'],
            },
        }


class SRIOVContext(OSContextGenerator):
    """Provide context for configuring SR-IOV devices."""

    class sriov_config_mode(enum.Enum):
        """Mode in which SR-IOV is configured.

        The configuration option identified by the ``numvfs_key`` parameter
        is overloaded and defines in which mode the charm should interpret
        the other SR-IOV-related configuration options.
        """
        auto = 'auto'
        blanket = 'blanket'
        explicit = 'explicit'

    PCIDeviceNumVFs = collections.namedtuple(
        'PCIDeviceNumVFs', ['device', 'numvfs'])

    def _determine_numvfs(self, device, sriov_numvfs):
        """Determine number of Virtual Functions (VFs) configured for device.

        :param device: Object describing a PCI Network interface card (NIC)/
        :type device: sriov_netplan_shim.pci.PCINetDevice
        :param sriov_numvfs: Number of VFs requested for blanket configuration.
        :type sriov_numvfs: int
        :returns: Number of VFs to configure for device
        :rtype: Optional[int]
        """

        def _get_capped_numvfs(requested):
            """Get a number of VFs that does not exceed individual card limits.

            Depending and make and model of NIC the number of VFs supported
            vary.  Requesting more VFs than a card support would be a fatal
            error, cap the requested number at the total number of VFs each
            individual card supports.

            :param requested: Number of VFs requested
            :type requested: int
            :returns: Number of VFs allowed
            :rtype: int
            """
            actual = min(int(requested), int(device.sriov_totalvfs))
            if actual < int(requested):
                log('Requested VFs ({}) too high for device {}. Falling back '
                    'to value supported by device: {}'
                    .format(requested, device.interface_name,
                            device.sriov_totalvfs),
                    level=WARNING)
            return actual

        if self._sriov_config_mode == self.sriov_config_mode.auto:
            # auto-mode
            #
            # If device mapping configuration is present, return information
            # on cards with mapping.
            #
            # If no device mapping configuration is present, return information
            # for all cards.
            #
            # The maximum number of VFs supported by card will be used.
            if (self._sriov_mapped_devices and
                    device.interface_name not in self._sriov_mapped_devices):
                log('SR-IOV configured in auto mode: No device mapping for {}'
                    .format(device.interface_name),
                    level=DEBUG)
                return
            return _get_capped_numvfs(device.sriov_totalvfs)
        elif self._sriov_config_mode == self.sriov_config_mode.blanket:
            # blanket-mode
            #
            # User has specified a number of VFs that should apply to all
            # cards with support for VFs.
            return _get_capped_numvfs(sriov_numvfs)
        elif self._sriov_config_mode == self.sriov_config_mode.explicit:
            # explicit-mode
            #
            # User has given a list of interface names and associated number of
            # VFs
            if device.interface_name not in self._sriov_config_devices:
                log('SR-IOV configured in explicit mode: No device:numvfs '
                    'pair for device {}, skipping.'
                    .format(device.interface_name),
                    level=DEBUG)
                return
            return _get_capped_numvfs(
                self._sriov_config_devices[device.interface_name])
        else:
            raise RuntimeError('This should not be reached')

    def __init__(self, numvfs_key=None, device_mappings_key=None):
        """Initialize map from PCI devices and configuration options.

        :param numvfs_key: Config key for numvfs (default: 'sriov-numvfs')
        :type numvfs_key: Optional[str]
        :param device_mappings_key: Config key for device mappings
                                    (default: 'sriov-device-mappings')
        :type device_mappings_key: Optional[str]
        :raises: RuntimeError
        """
        numvfs_key = numvfs_key or 'sriov-numvfs'
        device_mappings_key = device_mappings_key or 'sriov-device-mappings'

        devices = pci.PCINetDevices()
        charm_config = config()
        sriov_numvfs = charm_config.get(numvfs_key) or ''
        sriov_device_mappings = charm_config.get(device_mappings_key) or ''

        # create list of devices from sriov_device_mappings config option
        self._sriov_mapped_devices = [
            pair.split(':', 1)[1]
            for pair in sriov_device_mappings.split()
        ]

        # create map of device:numvfs from sriov_numvfs config option
        self._sriov_config_devices = {
            ifname: numvfs for ifname, numvfs in (
                pair.split(':', 1) for pair in sriov_numvfs.split()
                if ':' in sriov_numvfs)
        }

        # determine configuration mode from contents of sriov_numvfs
        if sriov_numvfs == 'auto':
            self._sriov_config_mode = self.sriov_config_mode.auto
        elif sriov_numvfs.isdigit():
            self._sriov_config_mode = self.sriov_config_mode.blanket
        elif ':' in sriov_numvfs:
            self._sriov_config_mode = self.sriov_config_mode.explicit
        else:
            raise RuntimeError('Unable to determine mode of SR-IOV '
                               'configuration.')

        self._map = {
            device.pci_address: self.PCIDeviceNumVFs(
                device, self._determine_numvfs(device, sriov_numvfs))
            for device in devices.pci_devices
            if device.sriov and
            self._determine_numvfs(device, sriov_numvfs) is not None
        }

    def __call__(self):
        """Provide backward compatible SR-IOV context.

        :returns: Map interface name: min(configured, max) virtual functions.
        Example:
           {
               'eth0': 16,
               'eth1': 32,
               'eth2': 64,
           }
        :rtype: Dict[str,int]
        """
        return {
            pcidnvfs.device.interface_name: pcidnvfs.numvfs
            for _, pcidnvfs in self._map.items()
        }

    @property
    def get_map(self):
        """Provide map of configured SR-IOV capable PCI devices.

        :returns: Map PCI-address: (PCIDevice, min(configured, max) VFs.
        Example:
            {
                '0000:81:00.0': self.PCIDeviceNumVFs(<PCIDevice object>, 32),
                '0000:81:00.1': self.PCIDeviceNumVFs(<PCIDevice object>, 32),
            }
        :rtype: Dict[str, self.PCIDeviceNumVFs]
        """
        return self._map


class CephBlueStoreCompressionContext(OSContextGenerator):
    """Ceph BlueStore compression options."""

    # Tuple with Tuples that map configuration option name to CephBrokerRq op
    # property name
    options = (
        ('bluestore-compression-algorithm',
            'compression-algorithm'),
        ('bluestore-compression-mode',
            'compression-mode'),
        ('bluestore-compression-required-ratio',
            'compression-required-ratio'),
        ('bluestore-compression-min-blob-size',
            'compression-min-blob-size'),
        ('bluestore-compression-min-blob-size-hdd',
            'compression-min-blob-size-hdd'),
        ('bluestore-compression-min-blob-size-ssd',
            'compression-min-blob-size-ssd'),
        ('bluestore-compression-max-blob-size',
            'compression-max-blob-size'),
        ('bluestore-compression-max-blob-size-hdd',
            'compression-max-blob-size-hdd'),
        ('bluestore-compression-max-blob-size-ssd',
            'compression-max-blob-size-ssd'),
    )

    def __init__(self):
        """Initialize context by loading values from charm config.

        We keep two maps, one suitable for use with CephBrokerRq's and one
        suitable for template generation.
        """
        charm_config = config()

        # CephBrokerRq op map
        self.op = {}
        # Context exposed for template generation
        self.ctxt = {}
        for config_key, op_key in self.options:
            value = charm_config.get(config_key)
            self.ctxt.update({config_key.replace('-', '_'): value})
            self.op.update({op_key: value})

    def __call__(self):
        """Get context.

        :returns: Context
        :rtype: Dict[str,any]
        """
        return self.ctxt

    def get_op(self):
        """Get values for use in CephBrokerRq op.

        :returns: Context values with CephBrokerRq op property name as key.
        :rtype: Dict[str,any]
        """
        return self.op

    def get_kwargs(self):
        """Get values for use as keyword arguments.

        :returns: Context values with key suitable for use as kwargs to
                  CephBrokerRq add_op_create_*_pool methods.
        :rtype: Dict[str,any]
        """
        return {
            k.replace('-', '_'): v
            for k, v in self.op.items()
        }

    def validate(self):
        """Validate options.

        :raises: AssertionError
        """
        # We slip in a dummy name on class instantiation to allow validation of
        # the other options. It will not affect further use.
        #
        # NOTE: once we retire Python 3.5 we can fold this into a in-line
        # dictionary comprehension in the call to the initializer.
        dummy_op = {'name': 'dummy-name'}
        dummy_op.update(self.op)
        pool = ch_ceph.BasePool('dummy-service', op=dummy_op)
        pool.validate()
