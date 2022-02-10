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

import logging

from .apidriver import APIDriver

log = logging.getLogger('vmaas.main')


class MAASException(Exception):
    pass


class MAASDriverException(Exception):
    pass


class MAASClient(object):
    """
    A wrapper for the python maas client which makes using the API a bit
    more user friendly.
    """

    def __init__(self, api_url, api_key, **kwargs):
        self.driver = self._get_driver(api_url, api_key, **kwargs)

    def _get_driver(self, api_url, api_key, **kwargs):
        return APIDriver(api_url, api_key)

    def _validate_maas(self):
        try:
            self.driver.validate_maas()
            logging.info("Validated MAAS API")
            return True
        except Exception as e:
            logging.error("MAAS API validation has failed. "
                          "Check maas_url and maas_credentials. Error: {}"
                          "".format(e))
            return False

    ###########################################################################
    #  DNS API - http://maas.ubuntu.com/docs2.0/api.html#dnsresource
    ###########################################################################
    def get_dnsresources(self):
        """
        Get a listing of DNS resources which are currently defined.

        DNS object is a dictionary of the form:
        {'fqdn': 'keystone.maas',
         'resource_records': [],
         'address_ttl': None,
         'resource_uri': '/MAAS/api/2.0/dnsresources/1/',
         'ip_addresses': [],
         'id': 1}

        :returns: a list of DNS objects
        :rtype: List[Dict[str, Any]]
        """
        resp = self.driver.get_dnsresources()
        if resp.ok:
            return resp.data
        return []

    def update_dnsresource(self, rid, fqdn, ip_address):
        """
        Updates a DNS resource with a new ip_address

        :param rid: The dnsresource_id i.e.
                    /api/2.0/dnsresources/{dnsresource_id}/
        :param fqdn: The fqdn address to update
        :param ip_address: The ip address to update the A record to point to
        :returns: the response from the requests method
        :rtype: maasclient.driver.Response
        """
        return self.driver.update_dnsresource(rid, fqdn, ip_address)

    def create_dnsresource(self, fqdn, ip_address, address_ttl=None):
        """
        Creates a new DNS resource

        :param fqdn: The fqdn address to update
        :param ip_address: The ip address to update the A record to point to
        :param adress_ttl: DNS time to live
        :returns: the response from the requests method
        :rtype: maasclient.driver.Response
        """
        return self.driver.create_dnsresource(fqdn, ip_address, address_ttl)

    ###########################################################################
    #  IP API - http://maas.ubuntu.com/docs2.0/api.html#ip-address
    ###########################################################################
    def get_ipaddresses(self):
        """
        Get a list of ip addresses

        :returns: a list of ip address dictionaries
        :rtype: List[str]
        """
        resp = self.driver.get_ipaddresses()
        if resp.ok:
            return resp.data
        return []

    def create_ipaddress(self, ip_address, hostname=None):
        """
        Creates a new IP resource

        :param ip_address: The ip address to register
        :param hostname: the hostname to register at the same time
        :returns: the response from the requests method
        :rtype: maasclient.driver.Response
        """
        return self.driver.create_ipaddress(ip_address, hostname)
