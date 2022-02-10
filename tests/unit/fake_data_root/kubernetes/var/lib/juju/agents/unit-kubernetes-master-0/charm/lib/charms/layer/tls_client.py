# Copyright 2016-2017 Canonical Ltd.
#
# This file is part of the tls-client layer for Juju.
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

from charmhelpers.core.hookenv import log
from charmhelpers.core import unitdata

from charms.reactive import remove_state
from charms.reactive import endpoint_from_flag


def reset_certificate_write_flag(cert_type):
    """
    Reset the certificate written flag so notification will work on the next
    write cert_type must be 'server', 'client', or 'ca' to indicate type of
    certificate
    """
    if cert_type not in ['server', 'client', 'ca']:
        log('Unknown certificate type!')
    else:
        remove_state('tls_client.{0}.certificate.written'.format(cert_type))


def request_server_cert(common_name, sans=None, crt_path=None, key_path=None):
    tls = endpoint_from_flag('certificates.available')
    tls.request_server_cert(common_name, sans)
    if not crt_path and not key_path:
        return
    kv = unitdata.kv()
    cert_paths = kv.get('layer.tls-client.cert-paths', {})
    cert_paths.setdefault('server', {})[common_name] = {
        'crt': str(crt_path),
        'key': str(key_path),
    }
    kv.set('layer.tls-client.cert-paths', cert_paths)


def request_client_cert(common_name, sans=None, crt_path=None, key_path=None):
    tls = endpoint_from_flag('certificates.available')
    tls.request_client_cert(common_name, sans)
    if not crt_path and not key_path:
        return
    kv = unitdata.kv()
    cert_paths = kv.get('layer.tls-client.cert-paths', {})
    cert_paths.setdefault('client', {})[common_name] = {
        'crt': str(crt_path),
        'key': str(key_path),
    }
    kv.set('layer.tls-client.cert-paths', cert_paths)
