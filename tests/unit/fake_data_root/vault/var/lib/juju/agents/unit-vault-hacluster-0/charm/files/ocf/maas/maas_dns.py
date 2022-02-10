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

import argparse
import requests_oauthlib
import logging
import sys
import time

import maasclient


# Default MaaS API options
NUM_RETRIES = 5
RETRY_BASE_DELAY = 10
RETRY_CODES = [500]

# the global options that is parsed from the arguments
options = None


class RetriesException(Exception):
    pass


def retry_on_request_error(retries=3, base_delay=0, codes=None):
    """Retry a function that retures a requests response.

    If the response from the target function has an error code in the
    :param:`codes` list then retry the function up to :param:`retries`.  The
    :param:`base_delay`, if not zero, will progressively back off at
    `base_delay`, `base_delay * 2`, `base_delay * 3` ...

    If the decorated function raises an exception, then the decorator DOESN'T
    catch it, and this will bypass any retries.

    In order to enable the decorator to access command line arguments, each of
    the arguments can optionally be a Callable that returns the value, which
    will be evaluated when the function is called.

    :param retries: Number of attempts to run the decorated function.
    :type retries: Option[int, Callable[..., int]]
    :param base_delay: Back off time, which linearly increases by the number of
        retries for each failed request.
    :type base_delay: Option[int, Callable[..., int]]
    :param codes: The codes to detect that force a retry that
        response.status_code may contain.
    :type codes: Option[List[int], Callable(..., List[int]]
    :returns: decorated target function
    :rtype: Callable
    :raises: Exception, if the decorated function raises an exception
    """
    if codes is None:
        codes = [500]

    def inner1(f):

        def inner2(*args, **kwargs):
            if callable(retries):
                _retries = retries()
            else:
                _retries = retries
            num_retries = _retries
            if callable(base_delay):
                _base_delay = base_delay()
            else:
                _base_delay = base_delay
            if callable(codes):
                _codes = codes()
            else:
                _codes = codes
            multiplier = 1
            while True:
                response = f(*args, **kwargs)
                if response.status_code not in _codes:
                    return response
                if _retries <= 0:
                    raise RetriesException(
                        "Command {} failed after {} retries"
                        .format(f.__name__, num_retries))
                delay = _base_delay * multiplier
                multiplier += 1
                logging.debug(
                    "Retrying '{}' {} more times (delay={})"
                    .format(f.__name__, _retries, delay))
                _retries -= 1
                if delay:
                    time.sleep(delay)

        return inner2

    return inner1


def options_retries():
    """Returns options.maas_api_retries value

    It's used as a callable in the retry_on_request_error as follows:

        @retry_on_request_error(retries=options_retries,
                                base_delay=options_base_delay,
                                codes=options_codes)
        def some_function_that_needs_retries_that_returns_Response(...):
            pass

    :returns: options.maas_api_retries
    :rtype: int
    """
    global options
    if options is not None:
        return options.maas_api_retries
    else:
        return NUM_RETRIES


def options_base_delay():
    """Returns options.maas_base_delay

    It's used as a callable in the retry_on_request_error as follows:

        @retry_on_request_error(retries=options_retries,
                                base_delay=options_base_delay,
                                codes=options_codes)
        def some_function_that_needs_retries_that_returns_Response(...):
            pass

    :returns: options.maas_base_delay
    :rtype: int
    """
    global options
    if options is not None:
        return options.maas_base_delay
    else:
        return RETRY_BASE_DELAY


def options_codes():
    """Returns options.maas_retry_codes

    It's used as a callable in the retry_on_request_error as follows:

        @retry_on_request_error(retries=options_retries,
                                base_delay=options_base_delay,
                                codes=options_codes)
        def some_function_that_needs_retries_that_returns_Response(...):
            pass

    :returns: options.maas_retry_codes
    :rtype: List[int]
    """
    global options
    if options is not None:
        return options.maas_retry_codes
    else:
        return RETRY_CODES


class MAASDNS(object):
    def __init__(self, options):
        self.maas = maasclient.MAASClient(options.maas_server,
                                          options.maas_credentials)
        # String representation of the fqdn
        self.fqdn = options.fqdn
        # Dictionary representation of MAAS dnsresource object
        # TODO: Do this as a property
        self.dnsresource = self.get_dnsresource()
        # String representation of the time to live
        self.ttl = str(options.ttl)
        # String representation of the ip
        self.ip = options.ip_address
        self.maas_server = options.maas_server
        self.maas_creds = options.maas_credentials

    def get_dnsresource(self):
        """ Get a dnsresource object """
        dnsresources = self.maas.get_dnsresources()
        self.dnsresource = None
        for dnsresource in dnsresources:
            if dnsresource['fqdn'] == self.fqdn:
                self.dnsresource = dnsresource
        return self.dnsresource

    def get_dnsresource_id(self):
        """ Get a dnsresource ID """
        return self.dnsresource['id']

    @retry_on_request_error(retries=options_retries,
                            base_delay=options_base_delay,
                            codes=options_codes)
    def update_resource(self):
        """ Update a dnsresource record with an IP """
        return self.maas.update_dnsresource(self.dnsresource['id'],
                                            self.dnsresource['fqdn'],
                                            self.ip)

    def create_dnsresource(self):
        """ Create a DNS resource object
        Due to https://bugs.launchpad.net/maas/+bug/1555393
        this is implemented outside of the maas lib.
        """
        dns_url = '{}/api/2.0/dnsresources/?format=json'.format(
            self.maas_server)
        (consumer_key, access_token, token_secret) = self.maas_creds.split(':')

        # The use of PLAINTEXT signature is inline with libmaas
        # https://goo.gl/EJPrM7 but as noted there should be switched
        # to HMAC once it works server-side.
        maas_session = requests_oauthlib.OAuth1Session(
            consumer_key,
            signature_method='PLAINTEXT',
            resource_owner_key=access_token,
            resource_owner_secret=token_secret)
        fqdn_list = self.fqdn.split('.')
        payload = {
            'fqdn': self.fqdn,
            'name': fqdn_list[0],
            'domain': '.'.join(fqdn_list[1:]),
            'address_ttl': self.ttl,
            'ip_addresses': self.ip,
        }

        @retry_on_request_error(retries=options_retries,
                                base_delay=options_base_delay,
                                codes=options_codes)
        def inner_maas_session_post(session, dns_url, payload):
            return session.post(dns_url, data=payload)

        return inner_maas_session_post(maas_session, dns_url, payload)


class MAASIP(object):
    def __init__(self, options):
        self.maas = maasclient.MAASClient(options.maas_server,
                                          options.maas_credentials)
        # String representation of the IP
        self.ip = options.ip_address
        # Dictionary representation of MAAS ipaddresss object
        # TODO: Do this as a property
        self.ipaddress = self.get_ipaddress()

    def get_ipaddress(self):
        """ Get an ipaddresses object """
        ipaddresses = self.maas.get_ipaddresses()
        self.ipaddress = None
        for ipaddress in ipaddresses:
            if ipaddress['ip'] == self.ip:
                self.ipaddress = ipaddress
        return self.ipaddress

    @retry_on_request_error(retries=options_retries,
                            base_delay=options_base_delay,
                            codes=options_codes)
    def create_ipaddress(self, hostname=None):
        """ Create an ipaddresses object
        Due to https://bugs.launchpad.net/maas/+bug/1555393
        This is currently unused
        """
        return self.maas.create_ipaddress(self.ip, hostname)


def setup_logging(logfile, log_level='INFO'):
    logFormatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S")
    rootLogger = logging.getLogger()
    rootLogger.setLevel(log_level)

    consoleHandler = logging.StreamHandler()
    consoleHandler.setFormatter(logFormatter)
    rootLogger.addHandler(consoleHandler)

    try:
        fileLogger = logging.getLogger('file')
        fileLogger.propagate = False

        fileHandler = logging.FileHandler(logfile)
        fileHandler.setFormatter(logFormatter)
        rootLogger.addHandler(fileHandler)
        fileLogger.addHandler(fileHandler)
    except IOError:
        logging.error('Unable to write to logfile: {}'.format(logfile))


def dns_ha():

    parser = argparse.ArgumentParser()
    parser.add_argument('--maas_server', '-s',
                        help='URL to mangage the MAAS server',
                        required=True)
    parser.add_argument('--maas_credentials', '-c',
                        help='MAAS OAUTH credentials',
                        required=True)
    parser.add_argument('--fqdn', '-d',
                        help='Fully Qualified Domain Name',
                        required=True)
    parser.add_argument('--ip_address', '-i',
                        help='IP Address, target of the A record',
                        required=True)
    parser.add_argument('--ttl', '-t',
                        help='DNS Time To Live in seconds',
                        default='')
    parser.add_argument('--logfile', '-l',
                        help='Path to logfile',
                        default='/var/log/{}.log'
                                ''.format(sys.argv[0]
                                          .split('/')[-1]
                                          .split('.')[0]))
    parser.add_argument('--maas_api_retries', '-r',
                        help='The number of times to retry a MaaS API call',
                        type=int,
                        default=3)
    parser.add_argument('--maas_base_delay', '-b',
                        help='The base delay after a failed MaaS API call',
                        type=int,
                        default=10)

    def read_int_list(s):
        try:
            return [int(x.strip()) for x in s.split(',')]
        except TypeError:
            msg = "Can't convert '{}' into a list of integers".format(s)
            return argparse.ArgumentTypeError(msg)

    parser.add_argument('--maas_retry_codes', '-x',
                        help=('The codes to detect to auto-retry, as a '
                              'comma-separated list.'),
                        type=read_int_list,
                        default=[500])
    global options
    options = parser.parse_args()

    setup_logging(options.logfile)
    logging.info("Starting maas_dns")

    dns_obj = MAASDNS(options)
    if not dns_obj.dnsresource:
        dns_obj.create_dnsresource()
    elif dns_obj.dnsresource.get('ip_addresses'):
        # TODO: Handle multiple IPs returned for ip_addresses
        for ip in dns_obj.dnsresource['ip_addresses']:
            if ip.get('ip') != options.ip_address:
                logging.info('Update the dnsresource with IP: {}'
                             ''.format(options.ip_address))
                dns_obj.update_resource()
            else:
                logging.info('IP is the SAME {}, no update required'
                             ''.format(options.ip_address))
    else:
        logging.info('Update the dnsresource with IP: {}'
                     ''.format(options.ip_address))
        dns_obj.update_resource()


def main():
    """Entry point for the script.

    Runs dns_ha(), but wraps it with exception handling so that retries using
    the MaaS API return 2 from the script, and all other errors return 1.
    Otherwise the script returns 0 to indicate that it thinks it succeeded.

    :returns: return code for script
    :rtype: int
    """
    try:
        dns_ha()
    except RetriesException as e:
        logging.error("'{}' failed retries: {}".format(sys.argv[0], str(e)))
        return 1
    except Exception as e:
        logging.error("'{}' failed due to: {}".format(sys.argv[0], str(e)))
        import traceback
        logging.error("Traceback:\n{}".format(traceback.format_exc()))
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
