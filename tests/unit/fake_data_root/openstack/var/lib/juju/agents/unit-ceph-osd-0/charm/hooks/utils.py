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

import re
import os
import socket
import subprocess
import sys

sys.path.append('lib')
import charms_ceph.utils as ceph

from charmhelpers.core.hookenv import (
    unit_get,
    cached,
    config,
    network_get_primary_address,
    log,
    DEBUG,
    WARNING,
    status_set,
    storage_get,
    storage_list,
    function_get,
)
from charmhelpers.core import unitdata
from charmhelpers.fetch import (
    apt_install,
    filter_installed_packages
)

from charmhelpers.core.host import (
    lsb_release,
    CompareHostReleases,
)

from charmhelpers.contrib.network.ip import (
    get_address_in_network,
    get_ipv6_addr
)

ALL = "all"  # string value representing all "OSD devices"
TEMPLATES_DIR = 'templates'

try:
    import jinja2
except ImportError:
    apt_install(filter_installed_packages(['python3-jinja2']),
                fatal=True)
    import jinja2

try:
    import dns.resolver
except ImportError:
    apt_install(filter_installed_packages(['python3-dnspython']),
                fatal=True)
    import dns.resolver


_bootstrap_keyring = "/var/lib/ceph/bootstrap-osd/ceph.keyring"
_upgrade_keyring = "/var/lib/ceph/osd/ceph.client.osd-upgrade.keyring"


def is_osd_bootstrap_ready():
    """
    Is this machine ready to add OSDs.

    :returns: boolean: Is the OSD bootstrap key present
    """
    return os.path.exists(_bootstrap_keyring)


def import_osd_bootstrap_key(key):
    """
    Ensure that the osd-bootstrap keyring is setup.

    :param key: The cephx key to add to the bootstrap keyring
    :type key: str
    :raises: subprocess.CalledProcessError"""
    if not os.path.exists(_bootstrap_keyring):
        cmd = [
            "sudo",
            "-u",
            ceph.ceph_user(),
            'ceph-authtool',
            _bootstrap_keyring,
            '--create-keyring',
            '--name=client.bootstrap-osd',
            '--add-key={}'.format(key)
        ]
        subprocess.check_call(cmd)


def import_osd_upgrade_key(key):
    """
    Ensure that the osd-upgrade keyring is setup.

    :param key: The cephx key to add to the upgrade keyring
    :type key: str
    :raises: subprocess.CalledProcessError"""
    if not os.path.exists(_upgrade_keyring):
        cmd = [
            "sudo",
            "-u",
            ceph.ceph_user(),
            'ceph-authtool',
            _upgrade_keyring,
            '--create-keyring',
            '--name=client.osd-upgrade',
            '--add-key={}'.format(key)
        ]
        subprocess.check_call(cmd)


def render_template(template_name, context, template_dir=TEMPLATES_DIR):
    """Render Jinja2 template.

    In addition to the template directory specified by the caller the shared
    'templates' directory in the ``charmhelpers.contrib.openstack`` module will
    be searched.

    :param template_name: Name of template file.
    :type template_name: str
    :param context: Template context.
    :type context: Dict[str,any]
    :param template_dir: Primary path to search for templates.
                         (default: contents of the ``TEMPLATES_DIR`` global)
    :type template_dir: Optional[str]
    :returns: The rendered template
    :rtype: str
    """
    templates = jinja2.Environment(
        loader=jinja2.ChoiceLoader((
            jinja2.FileSystemLoader(template_dir),
            jinja2.PackageLoader('charmhelpers.contrib.openstack',
                                 'templates'),
        )))
    template = templates.get_template(template_name)
    return template.render(context)


def enable_pocket(pocket):
    apt_sources = "/etc/apt/sources.list"
    with open(apt_sources, "rt", encoding='UTF-8') as sources:
        lines = sources.readlines()
    with open(apt_sources, "wt", encoding='UTF-8') as sources:
        for line in lines:
            if pocket in line:
                sources.write(re.sub('^# deb', 'deb', line))
            else:
                sources.write(line)


@cached
def get_unit_hostname():
    return socket.gethostname()


@cached
def get_host_ip(hostname=None):
    if config('prefer-ipv6'):
        return get_ipv6_addr()[0]

    hostname = hostname or unit_get('private-address')
    try:
        # Test to see if already an IPv4 address
        socket.inet_aton(hostname)
        return hostname
    except socket.error:
        # This may throw an NXDOMAIN exception; in which case
        # things are badly broken so just let it kill the hook
        answers = dns.resolver.query(hostname, 'A')
        if answers:
            return answers[0].address


@cached
def get_public_addr():
    if config('ceph-public-network'):
        return get_network_addrs('ceph-public-network')[0]

    try:
        return network_get_primary_address('public')
    except NotImplementedError:
        log("network-get not supported", DEBUG)

    return get_host_ip()


@cached
def get_cluster_addr():
    if config('ceph-cluster-network'):
        return get_network_addrs('ceph-cluster-network')[0]

    try:
        return network_get_primary_address('cluster')
    except NotImplementedError:
        log("network-get not supported", DEBUG)

    return get_host_ip()


def get_networks(config_opt='ceph-public-network'):
    """Get all configured networks from provided config option.

    If public network(s) are provided, go through them and return those for
    which we have an address configured.
    """
    networks = config(config_opt)
    if networks:
        networks = networks.split()
        return [n for n in networks if get_address_in_network(n)]

    return []


def get_network_addrs(config_opt):
    """Get all configured public networks addresses.

    If public network(s) are provided, go through them and return the
    addresses we have configured on any of those networks.
    """
    addrs = []
    networks = config(config_opt)
    if networks:
        networks = networks.split()
        addrs = [get_address_in_network(n) for n in networks]
        addrs = [a for a in addrs if a]

    if not addrs:
        if networks:
            msg = ("Could not find an address on any of '%s' - resolve this "
                   "error to retry" % (networks))
            status_set('blocked', msg)
            raise Exception(msg)
        else:
            return [get_host_ip()]

    return addrs


def assert_charm_supports_ipv6():
    """Check whether we are able to support charms ipv6."""
    _release = lsb_release()['DISTRIB_CODENAME'].lower()
    if CompareHostReleases(_release) < "trusty":
        raise Exception("IPv6 is not supported in the charms for Ubuntu "
                        "versions less than Trusty 14.04")


def get_blacklist():
    """Get blacklist stored in the local kv() store"""
    db = unitdata.kv()
    return db.get('osd-blacklist', [])


def get_journal_devices():
    if config('osd-journal'):
        devices = [el.strip() for el in config('osd-journal').split(' ')]
    else:
        devices = []
    storage_ids = storage_list('osd-journals')
    devices.extend((storage_get('location', s) for s in storage_ids))

    # Filter out any devices in the action managed unit-local device blacklist
    _blacklist = get_blacklist()
    return set(device for device in devices
               if device not in _blacklist and os.path.exists(device))


def should_enable_discard(devices):
    """
    Tries to autodetect if we can enable discard on devices and if that
    discard can be asynchronous. We want to enable both options if there's
    any SSDs unless any of them are using SATA <= 3.0, in which case
    discard is supported but is a blocking operation.
    """
    discard_enable = True
    for device in devices:
        # whitelist some devices that do not need checking
        if (device.startswith("/dev/nvme") or
                device.startswith("/dev/vd")):
            continue
        try:
            sata_3_or_less = is_sata30orless(device)
        except subprocess.CalledProcessError:
            sata_3_or_less = True
        if (device.startswith("/dev/") and
                os.path.exists(device) and
                sata_3_or_less):
            discard_enable = False
            log("SSD Discard autodetection: {} is forcing discard off"
                "(sata <= 3.0)".format(device), level=WARNING)
    return discard_enable


def is_sata30orless(device):
    result = subprocess.check_output(["/usr/sbin/smartctl", "-i", device])
    print(result)
    for line in str(result).split("\\n"):
        if re.match(r"SATA Version is: *SATA (1\.|2\.|3\.0)", str(line)):
            return True
    return False


def parse_osds_arguments():
    """Parse OSD IDs from action `osds` argument.

    Fetch action arguments and parse them from comma separated list to
    the set of OSD IDs.

    :return: Set of OSD IDs
    :rtype: set(str)
    """
    raw_arg = function_get("osds")

    if raw_arg is None:
        raise RuntimeError("Action argument \"osds\" is missing")

    # convert OSD IDs from user's input into the set
    args = {osd_id.strip() for osd_id in str(raw_arg).split(',')}

    if ALL in args and len(args) != 1:
        args = {ALL}
        log("keyword \"all\" was found in \"osds\" argument. Dropping other "
            "explicitly defined OSD IDs", WARNING)

    return args
