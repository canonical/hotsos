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
import grp
import os
import pwd
import re
import sys

import rabbit_utils
import ssl_utils

from charmhelpers.contrib.ssl.service import ServiceCA
from charmhelpers.core.host import is_container, cmp_pkgrevno
from charmhelpers.fetch import apt_install
from charmhelpers.core.hookenv import (
    open_port,
    close_port,
    config,
    leader_get,
    log,
    service_name,
    relation_ids,
    DEBUG,
    WARNING,
    ERROR,
)

try:
    import psutil
except ImportError:
    apt_install('python3-psutil', fatal=True)
    import psutil


SSL_KEY_FILE = "/etc/rabbitmq/rabbit-server-privkey.pem"
SSL_CERT_FILE = "/etc/rabbitmq/rabbit-server-cert.pem"
SSL_CA_FILE = "/etc/rabbitmq/rabbit-server-ca.pem"
RABBITMQ_CTL = '/usr/sbin/rabbitmqctl'
ENV_CONF = '/etc/rabbitmq/rabbitmq-env.conf'

# Rabbimq docs recommend min. 12 threads per core (see LP: #1693561)
# NOTE(hopem): these defaults give us roughly the same as the default shipped
#              with the version of rabbitmq in ubuntu xenial (3.5.7) - see
#              https://tinyurl.com/rabbitmq-3-5-7 for exact value. Note that
#              this default has increased with newer versions so we should
#              track this and keep the charm up-to-date.
DEFAULT_MULTIPLIER = 24
MAX_DEFAULT_THREADS = DEFAULT_MULTIPLIER * 2


def convert_from_base64(v):
    """Speculatively convert the string `v` from base64 encoding if it is
    base64 encoded.

    Rabbit originally supported pem encoded key/cert in config, play
    nice on upgrades as we now expect base64 encoded key/cert/ca.

    :param v: the string to maybe convert
    :type v: str
    :returns: string that may have been converted from base64 encoding.
    :rtype: str
    """
    if not v:
        return v
    if v.startswith('-----BEGIN'):
        return v
    try:
        return base64.b64decode(v).decode('utf-8')
    except TypeError:
        return v


class RabbitMQSSLContext(object):

    def enable_ssl(self, ssl_key, ssl_cert, ssl_port,
                   ssl_ca=None, ssl_only=False, ssl_client=None):

        if not os.path.exists(RABBITMQ_CTL):
            log('Deferring SSL configuration, RabbitMQ not yet installed')
            return {}

        uid = pwd.getpwnam("root").pw_uid
        gid = grp.getgrnam("rabbitmq").gr_gid

        for contents, path in (
                (ssl_key, SSL_KEY_FILE),
                (ssl_cert, SSL_CERT_FILE),
                (ssl_ca, SSL_CA_FILE)):

            if not contents:
                continue

            with open(path, 'w') as fh:
                fh.write(contents)

            if path == SSL_CA_FILE:
                # the CA can be world readable and it will allow clients to
                # verify the certificate offered by rabbit.
                os.chmod(path, 0o644)
            else:
                os.chmod(path, 0o640)

            os.chown(path, uid, gid)

        data = {
            "ssl_port": ssl_port,
            "ssl_cert_file": SSL_CERT_FILE,
            "ssl_key_file": SSL_KEY_FILE,
            "ssl_client": ssl_client,
            "ssl_ca_file": "",
            "ssl_only": ssl_only,
            "tls13": (
                cmp_pkgrevno('erlang-base', '23.0') >= 0 and
                cmp_pkgrevno('rabbitmq-server', '3.8.11') >= 0
            ),
        }

        if ssl_ca:
            data["ssl_ca_file"] = SSL_CA_FILE

        return data

    def __call__(self):
        """
        The legacy config support adds some additional complications.

        ssl_enabled = True, ssl = off -> ssl enabled
        ssl_enabled = False, ssl = on -> ssl enabled
        """
        ssl_mode, external_ca = ssl_utils.get_ssl_mode()
        ctxt = {
            'ssl_mode': ssl_mode,
        }
        if ssl_mode == 'off':
            close_port(config('ssl_port'))
            ssl_utils.reconfigure_client_ssl()
            return ctxt

        if ssl_mode == ssl_utils.CERTS_FROM_RELATION:
            relation_certs = ssl_utils.get_relation_cert_data()
            ctxt['ssl_mode'] = 'on'
            ssl_key = convert_from_base64(relation_certs['key'])
            ssl_cert = convert_from_base64(relation_certs['cert'])
            ssl_ca = convert_from_base64(relation_certs['ca'])
            ssl_port = config('ssl_port')
        else:

            ssl_key = convert_from_base64(config('ssl_key'))
            ssl_cert = convert_from_base64(config('ssl_cert'))
            ssl_ca = convert_from_base64(config('ssl_ca'))
            ssl_port = config('ssl_port')

            # If external managed certs then we need all the fields.
            if (ssl_mode in ('on', 'only') and any((ssl_key, ssl_cert)) and
                    not all((ssl_key, ssl_cert))):
                log('If ssl_key or ssl_cert are specified both are required.',
                    level=ERROR)
                sys.exit(1)

            if not external_ca:
                ssl_cert, ssl_key, ssl_ca = ServiceCA.get_service_cert()

        ctxt.update(self.enable_ssl(
            ssl_key, ssl_cert, ssl_port, ssl_ca,
            ssl_only=(ssl_mode == "only"), ssl_client=False
        ))
        ssl_utils.reconfigure_client_ssl(True)
        open_port(ssl_port)

        return ctxt


class RabbitMQClusterContext(object):

    def __call__(self):
        ctxt = {'cluster_partition_handling':
                (leader_get(rabbit_utils.CLUSTER_MODE_KEY) or
                    rabbit_utils.CLUSTER_MODE_FOR_INSTALL),
                'mnesia_table_loading_retry_timeout':
                config('mnesia-table-loading-retry-timeout'),
                'mnesia_table_loading_retry_limit':
                config('mnesia-table-loading-retry-limit')}

        if config('connection-backlog'):
            ctxt['connection_backlog'] = config('connection-backlog')

        if cmp_pkgrevno('rabbitmq-server', '3.6') >= 0:
            ctxt['queue_master_locator'] = config('queue-master-locator')

        return ctxt


class RabbitMQEnvContext(object):

    def calculate_threads(self):
        """
        Determine the number of erl vm threads in pool based in cpu resources
        available.

        Number of threads will be limited to MAX_DEFAULT_WORKERS in
        container environments where no worker-multipler configuration
        option been set.

        @returns int: number of io threads to allocate
        """

        try:
            num_cpus = psutil.cpu_count()
        except AttributeError:
            num_cpus = psutil.NUM_CPUS

        multiplier = (config('erl-vm-io-thread-multiplier') or
                      DEFAULT_MULTIPLIER)

        log("Calculating erl vm io thread pool size based on num_cpus={} and "
            "multiplier={}".format(num_cpus, multiplier), DEBUG)

        count = int(num_cpus * multiplier)
        if multiplier > 0 and count == 0:
            count = 1

        if config('erl-vm-io-thread-multiplier') is None and is_container():
            # NOTE(hopem): Limit unconfigured erl-vm-io-thread-multiplier
            #              to MAX_DEFAULT_THREADS to avoid insane pool
            #              configuration in LXD containers on large servers.
            count = min(count, MAX_DEFAULT_THREADS)

        log("erl vm io thread pool size = {} (capped={})"
            .format(count, is_container()), DEBUG)

        return count

    def __call__(self):
        """Write rabbitmq-env.conf according to charm config.

        We never overwrite RABBITMQ_NODENAME to ensure that we don't break
        clustered rabbitmq.
        """
        blacklist = ['RABBITMQ_NODENAME']

        context = {'settings': {}}
        key = 'RABBITMQ_SERVER_ADDITIONAL_ERL_ARGS'
        context['settings'][key] = "'+A {}'".format(self.calculate_threads())

        if config('prefer-ipv6'):
            key = 'RABBITMQ_SERVER_START_ARGS'
            context['settings'][key] = "'-proto_dist inet6_tcp'"

        # TODO: this is legacy HA and should be removed since it is now
        # deprecated.
        if relation_ids('ha'):
            if not config('ha-vip-only'):
                # TODO: do we need to remove this setting if it already exists
                # and the above is false?
                context['settings']['RABBITMQ_NODENAME'] = \
                    '{}@localhost'.format(service_name())

        if os.path.exists(ENV_CONF):
            for line in open(ENV_CONF).readlines():
                if re.search(r'^\s*#', line) or not line.strip('\n'):
                    # ignore commented or blank lines
                    continue

                _line = line.partition("=")
                key = _line[0].strip()
                val = _line[2].strip()

                if _line[1] != "=":
                    log("Unable to parse line '{}' from {}".format(line,
                                                                   ENV_CONF),
                        WARNING)
                    continue

                if key in blacklist:
                    # Keep original
                    log("Leaving {} setting untouched".format(key), DEBUG)
                    context['settings'][key] = val

        return context
