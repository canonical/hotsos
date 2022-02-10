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

import yaml
import logging

from apiclient import maas_client as maas
from .driver import MAASDriver
from .driver import Response

try:
    from urllib2 import HTTPError
except ImportError:
    from urllib3.exceptions import HTTPError

log = logging.getLogger('vmaas.main')
OK = 200


class APIDriver(MAASDriver):
    """
    A MAAS driver implementation which uses the MAAS API.
    """

    def __init__(self, api_url, api_key, *args, **kwargs):
        if api_url[-1] != '/':
            api_url += '/'
        if api_url.find('/api/') < 0:
            api_url = api_url + 'api/2.0/'
        super(APIDriver, self).__init__(api_url, api_key, *args, **kwargs)
        self._client = None
        self._oauth = None

    @property
    def client(self):
        """
        MAAS client

        :rtype: MAASClient
        """
        if self._client:
            return self._client

        self._client = maas.MAASClient(auth=self.oauth,
                                       dispatcher=maas.MAASDispatcher(),
                                       base_url=self.api_url)
        return self._client

    @property
    def oauth(self):
        """
        MAAS OAuth information for interacting with the MAAS API.

        :rtype: MAASOAuth
        """
        if self._oauth:
            return self._oauth

        if self.api_key:
            api_key = self.api_key.split(':')
            self._oauth = maas.MAASOAuth(consumer_key=api_key[0],
                                         resource_token=api_key[1],
                                         resource_secret=api_key[2])
            return self._oauth
        else:
            return None

    def validate_maas(self):
        return self._get('/')

    def _get(self, path, **kwargs):
        """
        Issues a GET request to the MAAS REST API, returning the data
        from the query in the python form of the json data.
        """
        response = self.client.get(path, **kwargs)
        payload = response.read()
        log.debug("Request %s results: [%s] %s", path, response.getcode(),
                  payload)

        code = response.getcode()
        if code == OK:
            return Response(True, yaml.load(payload), code)
        else:
            return Response(False, payload, code)

    def _post(self, path, op='update', **kwargs):
        """
        Issues a POST request to the MAAS REST API.
        """
        try:
            response = self.client.post(path, **kwargs)
            payload = response.read()
            log.debug("Request %s results: [%s] %s", path, response.getcode(),
                      payload)

            code = response.getcode()
            if code == OK:
                return Response(True, yaml.load(payload), code)
            else:
                return Response(False, payload, code)
        except HTTPError as e:
            log.error("Error encountered: %s for %s with params %s",
                      str(e), path, str(kwargs))
            return Response(False, None, None)
        except Exception as e:
            log.error("Post request raised exception: %s", e)
            return Response(False, None, None)

    def _put(self, path, **kwargs):
        """
        Issues a PUT request to the MAAS REST API.
        """
        try:
            response = self.client.put(path, **kwargs)
            payload = response.read()
            log.debug("Request %s results: [%s] %s", path, response.getcode(),
                      payload)
            code = response.getcode()
            if code == OK:
                return Response(True, payload, code)
            else:
                return Response(False, payload, code)
        except HTTPError as e:
            log.error("Error encountered: %s with details: %s for %s with "
                      "params %s", e, e.read(), path, str(kwargs))
            return Response(False, None, None)
        except Exception as e:
            log.error("Put request raised exception: %s", e)
            return Response(False, None, None)

    ###########################################################################
    #  DNS API - http://maas.ubuntu.com/docs2.0/api.html#dnsresource
    ###########################################################################
    def get_dnsresources(self):
        """
        Get a listing of the MAAS dnsresources

        :returns: a list of MAAS dnsresrouce objects
        """
        return self._get('/dnsresources/')

    def update_dnsresource(self, rid, fqdn, ip_address):
        """
        Updates a DNS resource with a new ip_address

        :param rid: The dnsresource_id i.e.
                    /api/2.0/dnsresources/{dnsresource_id}/
        :param fqdn: The fqdn address to update
        :param ip_address: The ip address to update the A record to point to
        :returns: True if the DNS object was updated, False otherwise.
        """
        return self._put('/dnsresources/{}/'.format(rid), fqdn=fqdn,
                         ip_addresses=ip_address)

    def create_dnsresource(self, fqdn, ip_address, address_ttl=None):
        """
        Creates a new DNS resource

        :param fqdn: The fqdn address to update
        :param ip_address: The ip address to update the A record to point to
        :param adress_ttl: DNS time to live
        :returns: True if the DNS object was updated, False otherwise.
        """
        fqdn = bytes(fqdn, encoding='utf-8')
        ip_address = bytes(ip_address, encoding='utf-8')
        if address_ttl:
            return self._post('/dnsresources/',
                              fqdn=fqdn,
                              ip_addresses=ip_address,
                              address_ttl=address_ttl)
        else:
            return self._post('/dnsresources/',
                              fqdn=fqdn,
                              ip_addresses=ip_address)

    ###########################################################################
    #  IP API - http://maas.ubuntu.com/docs2.0/api.html#ip-addresses
    ###########################################################################
    def get_ipaddresses(self):
        """
        Get a dictionary of a given ip_address

        :param ip_address: The ip address to get information for
        :returns: a dictionary for a given ip
        """
        return self._get('/ipaddresses/')

    def create_ipaddress(self, ip_address, hostname=None):
        """
        Creates a new IP resource

        :param ip_address: The ip address to register
        :param hostname: the hostname to register at the same time
        :returns: True if the DNS object was updated, False otherwise.
        """
        if hostname:
            return self._post('/ipaddresses/', op='reserve',
                              ip_addresses=ip_address,
                              hostname=hostname)
        else:
            return self._post('/ipaddresses/', op='reserve',
                              ip_addresses=ip_address)
