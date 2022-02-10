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

# Common python helper functions used for OpenStack charms.
from collections import OrderedDict, namedtuple
from functools import partial, wraps

import subprocess
import json
import operator
import os
import sys
import re
import itertools
import functools

import six
import traceback
import uuid
import yaml

from charmhelpers import deprecate

from charmhelpers.contrib.network import ip

from charmhelpers.core import decorators, unitdata

import charmhelpers.contrib.openstack.deferred_events as deferred_events

from charmhelpers.core.hookenv import (
    WORKLOAD_STATES,
    action_fail,
    action_get,
    action_set,
    config,
    expected_peer_units,
    expected_related_units,
    log as juju_log,
    charm_dir,
    INFO,
    ERROR,
    metadata,
    related_units,
    relation_get,
    relation_id,
    relation_ids,
    relation_set,
    service_name as ch_service_name,
    status_set,
    hook_name,
    application_version_set,
    cached,
    leader_set,
    leader_get,
    local_unit,
)

from charmhelpers.core.strutils import (
    BasicStringComparator,
    bool_from_string,
)

from charmhelpers.contrib.storage.linux.lvm import (
    deactivate_lvm_volume_group,
    is_lvm_physical_volume,
    remove_lvm_physical_volume,
)

from charmhelpers.contrib.network.ip import (
    get_ipv6_addr,
    is_ipv6,
    port_has_listener,
)

from charmhelpers.core.host import (
    lsb_release,
    mounts,
    umount,
    service_running,
    service_pause,
    service_resume,
    service_stop,
    service_start,
    restart_on_change_helper,
)

from charmhelpers.fetch import (
    apt_cache,
    apt_install,
    import_key as fetch_import_key,
    add_source as fetch_add_source,
    SourceConfigError,
    GPGKeyError,
    get_upstream_version,
    filter_installed_packages,
    filter_missing_packages,
    ubuntu_apt_pkg as apt,
    OPENSTACK_RELEASES,
    UBUNTU_OPENSTACK_RELEASE,
)

from charmhelpers.fetch.snap import (
    snap_install,
    snap_refresh,
    valid_snap_channel,
)

from charmhelpers.contrib.storage.linux.utils import is_block_device, zap_disk
from charmhelpers.contrib.storage.linux.loopback import ensure_loopback_device
from charmhelpers.contrib.openstack.exceptions import OSContextError, ServiceActionError
from charmhelpers.contrib.openstack.policyd import (
    policyd_status_message_prefix,
    POLICYD_CONFIG_NAME,
)

from charmhelpers.contrib.openstack.ha.utils import (
    expect_ha,
)

CLOUD_ARCHIVE_URL = "http://ubuntu-cloud.archive.canonical.com/ubuntu"
CLOUD_ARCHIVE_KEY_ID = '5EDB1B62EC4926EA'

DISTRO_PROPOSED = ('deb http://archive.ubuntu.com/ubuntu/ %s-proposed '
                   'restricted main multiverse universe')

OPENSTACK_CODENAMES = OrderedDict([
    # NOTE(lourot): 'yyyy.i' isn't actually mapping with any real version
    # number. This just means the i-th version of the year yyyy.
    ('2011.2', 'diablo'),
    ('2012.1', 'essex'),
    ('2012.2', 'folsom'),
    ('2013.1', 'grizzly'),
    ('2013.2', 'havana'),
    ('2014.1', 'icehouse'),
    ('2014.2', 'juno'),
    ('2015.1', 'kilo'),
    ('2015.2', 'liberty'),
    ('2016.1', 'mitaka'),
    ('2016.2', 'newton'),
    ('2017.1', 'ocata'),
    ('2017.2', 'pike'),
    ('2018.1', 'queens'),
    ('2018.2', 'rocky'),
    ('2019.1', 'stein'),
    ('2019.2', 'train'),
    ('2020.1', 'ussuri'),
    ('2020.2', 'victoria'),
    ('2021.1', 'wallaby'),
    ('2021.2', 'xena'),
    ('2022.1', 'yoga'),
])

# The ugly duckling - must list releases oldest to newest
SWIFT_CODENAMES = OrderedDict([
    ('diablo',
        ['1.4.3']),
    ('essex',
        ['1.4.8']),
    ('folsom',
        ['1.7.4']),
    ('grizzly',
        ['1.7.6', '1.7.7', '1.8.0']),
    ('havana',
        ['1.9.0', '1.9.1', '1.10.0']),
    ('icehouse',
        ['1.11.0', '1.12.0', '1.13.0', '1.13.1']),
    ('juno',
        ['2.0.0', '2.1.0', '2.2.0']),
    ('kilo',
        ['2.2.1', '2.2.2']),
    ('liberty',
        ['2.3.0', '2.4.0', '2.5.0']),
    ('mitaka',
        ['2.5.0', '2.6.0', '2.7.0']),
    ('newton',
        ['2.8.0', '2.9.0', '2.10.0']),
    ('ocata',
        ['2.11.0', '2.12.0', '2.13.0']),
    ('pike',
        ['2.13.0', '2.15.0']),
    ('queens',
        ['2.16.0', '2.17.0']),
    ('rocky',
        ['2.18.0', '2.19.0']),
    ('stein',
        ['2.20.0', '2.21.0']),
    ('train',
        ['2.22.0', '2.23.0']),
    ('ussuri',
        ['2.24.0', '2.25.0']),
    ('victoria',
        ['2.25.0', '2.26.0']),
])

# >= Liberty version->codename mapping
PACKAGE_CODENAMES = {
    'nova-common': OrderedDict([
        ('12', 'liberty'),
        ('13', 'mitaka'),
        ('14', 'newton'),
        ('15', 'ocata'),
        ('16', 'pike'),
        ('17', 'queens'),
        ('18', 'rocky'),
        ('19', 'stein'),
        ('20', 'train'),
        ('21', 'ussuri'),
        ('22', 'victoria'),
    ]),
    'neutron-common': OrderedDict([
        ('7', 'liberty'),
        ('8', 'mitaka'),
        ('9', 'newton'),
        ('10', 'ocata'),
        ('11', 'pike'),
        ('12', 'queens'),
        ('13', 'rocky'),
        ('14', 'stein'),
        ('15', 'train'),
        ('16', 'ussuri'),
        ('17', 'victoria'),
    ]),
    'cinder-common': OrderedDict([
        ('7', 'liberty'),
        ('8', 'mitaka'),
        ('9', 'newton'),
        ('10', 'ocata'),
        ('11', 'pike'),
        ('12', 'queens'),
        ('13', 'rocky'),
        ('14', 'stein'),
        ('15', 'train'),
        ('16', 'ussuri'),
        ('17', 'victoria'),
    ]),
    'keystone': OrderedDict([
        ('8', 'liberty'),
        ('9', 'mitaka'),
        ('10', 'newton'),
        ('11', 'ocata'),
        ('12', 'pike'),
        ('13', 'queens'),
        ('14', 'rocky'),
        ('15', 'stein'),
        ('16', 'train'),
        ('17', 'ussuri'),
        ('18', 'victoria'),
    ]),
    'horizon-common': OrderedDict([
        ('8', 'liberty'),
        ('9', 'mitaka'),
        ('10', 'newton'),
        ('11', 'ocata'),
        ('12', 'pike'),
        ('13', 'queens'),
        ('14', 'rocky'),
        ('15', 'stein'),
        ('16', 'train'),
        ('18', 'ussuri'),  # Note this was actually 17.0 - 18.3
        ('19', 'victoria'),  # Note this is really 18.6
    ]),
    'ceilometer-common': OrderedDict([
        ('5', 'liberty'),
        ('6', 'mitaka'),
        ('7', 'newton'),
        ('8', 'ocata'),
        ('9', 'pike'),
        ('10', 'queens'),
        ('11', 'rocky'),
        ('12', 'stein'),
        ('13', 'train'),
        ('14', 'ussuri'),
        ('15', 'victoria'),
    ]),
    'heat-common': OrderedDict([
        ('5', 'liberty'),
        ('6', 'mitaka'),
        ('7', 'newton'),
        ('8', 'ocata'),
        ('9', 'pike'),
        ('10', 'queens'),
        ('11', 'rocky'),
        ('12', 'stein'),
        ('13', 'train'),
        ('14', 'ussuri'),
        ('15', 'victoria'),
    ]),
    'glance-common': OrderedDict([
        ('11', 'liberty'),
        ('12', 'mitaka'),
        ('13', 'newton'),
        ('14', 'ocata'),
        ('15', 'pike'),
        ('16', 'queens'),
        ('17', 'rocky'),
        ('18', 'stein'),
        ('19', 'train'),
        ('20', 'ussuri'),
        ('21', 'victoria'),
    ]),
    'openstack-dashboard': OrderedDict([
        ('8', 'liberty'),
        ('9', 'mitaka'),
        ('10', 'newton'),
        ('11', 'ocata'),
        ('12', 'pike'),
        ('13', 'queens'),
        ('14', 'rocky'),
        ('15', 'stein'),
        ('16', 'train'),
        ('18', 'ussuri'),
        ('19', 'victoria'),
    ]),
}

DEFAULT_LOOPBACK_SIZE = '5G'

DB_SERIES_UPGRADING_KEY = 'cluster-series-upgrading'

DB_MAINTENANCE_KEYS = [DB_SERIES_UPGRADING_KEY]


class CompareOpenStackReleases(BasicStringComparator):
    """Provide comparisons of OpenStack releases.

    Use in the form of

    if CompareOpenStackReleases(release) > 'mitaka':
        # do something with mitaka
    """
    _list = OPENSTACK_RELEASES


def error_out(msg):
    juju_log("FATAL ERROR: %s" % msg, level='ERROR')
    sys.exit(1)


def get_installed_semantic_versioned_packages():
    '''Get a list of installed packages which have OpenStack semantic versioning

    :returns List of installed packages
    :rtype: [pkg1, pkg2, ...]
    '''
    return filter_missing_packages(PACKAGE_CODENAMES.keys())


def get_os_codename_install_source(src):
    '''Derive OpenStack release codename from a given installation source.'''
    ubuntu_rel = lsb_release()['DISTRIB_CODENAME']
    rel = ''
    if src is None:
        return rel
    if src in ['distro', 'distro-proposed', 'proposed']:
        try:
            rel = UBUNTU_OPENSTACK_RELEASE[ubuntu_rel]
        except KeyError:
            e = 'Could not derive openstack release for '\
                'this Ubuntu release: %s' % ubuntu_rel
            error_out(e)
        return rel

    if src.startswith('cloud:'):
        ca_rel = src.split(':')[1]
        ca_rel = ca_rel.split('-')[1].split('/')[0]
        return ca_rel

    # Best guess match based on deb string provided
    if (src.startswith('deb') or
            src.startswith('ppa') or
            src.startswith('snap')):
        for v in OPENSTACK_CODENAMES.values():
            if v in src:
                return v


def get_os_version_install_source(src):
    codename = get_os_codename_install_source(src)
    return get_os_version_codename(codename)


def get_os_codename_version(vers):
    '''Determine OpenStack codename from version number.'''
    try:
        return OPENSTACK_CODENAMES[vers]
    except KeyError:
        e = 'Could not determine OpenStack codename for version %s' % vers
        error_out(e)


def get_os_version_codename(codename, version_map=OPENSTACK_CODENAMES):
    '''Determine OpenStack version number from codename.'''
    for k, v in six.iteritems(version_map):
        if v == codename:
            return k
    e = 'Could not derive OpenStack version for '\
        'codename: %s' % codename
    error_out(e)


def get_os_version_codename_swift(codename):
    '''Determine OpenStack version number of swift from codename.'''
    for k, v in six.iteritems(SWIFT_CODENAMES):
        if k == codename:
            return v[-1]
    e = 'Could not derive swift version for '\
        'codename: %s' % codename
    error_out(e)


def get_swift_codename(version):
    '''Determine OpenStack codename that corresponds to swift version.'''
    codenames = [k for k, v in six.iteritems(SWIFT_CODENAMES) if version in v]

    if len(codenames) > 1:
        # If more than one release codename contains this version we determine
        # the actual codename based on the highest available install source.
        for codename in reversed(codenames):
            releases = UBUNTU_OPENSTACK_RELEASE
            release = [k for k, v in six.iteritems(releases) if codename in v]
            ret = subprocess.check_output(['apt-cache', 'policy', 'swift'])
            if six.PY3:
                ret = ret.decode('UTF-8')
            if codename in ret or release[0] in ret:
                return codename
    elif len(codenames) == 1:
        return codenames[0]

    # NOTE: fallback - attempt to match with just major.minor version
    match = re.match(r'^(\d+)\.(\d+)', version)
    if match:
        major_minor_version = match.group(0)
        for codename, versions in six.iteritems(SWIFT_CODENAMES):
            for release_version in versions:
                if release_version.startswith(major_minor_version):
                    return codename

    return None


def get_os_codename_package(package, fatal=True):
    """Derive OpenStack release codename from an installed package.

    Initially, see if the openstack-release pkg is available (by trying to
    install it) and use it instead.

    If it isn't then it falls back to the existing method of checking the
    version of the package passed and then resolving the version from that
    using lookup tables.

    Note: if possible, charms should use get_installed_os_version() to
    determine the version of the "openstack-release" pkg.

    :param package: the package to test for version information.
    :type package: str
    :param fatal: If True (default), then die via error_out()
    :type fatal: bool
    :returns: the OpenStack release codename (e.g. ussuri)
    :rtype: str
    """

    codename = get_installed_os_version()
    if codename:
        return codename

    if snap_install_requested():
        cmd = ['snap', 'list', package]
        try:
            out = subprocess.check_output(cmd)
            if six.PY3:
                out = out.decode('UTF-8')
        except subprocess.CalledProcessError:
            return None
        lines = out.split('\n')
        for line in lines:
            if package in line:
                # Second item in list is Version
                return line.split()[1]

    cache = apt_cache()

    try:
        pkg = cache[package]
    except Exception:
        if not fatal:
            return None
        # the package is unknown to the current apt cache.
        e = 'Could not determine version of package with no installation '\
            'candidate: %s' % package
        error_out(e)

    if not pkg.current_ver:
        if not fatal:
            return None
        # package is known, but no version is currently installed.
        e = 'Could not determine version of uninstalled package: %s' % package
        error_out(e)

    vers = apt.upstream_version(pkg.current_ver.ver_str)
    if 'swift' in pkg.name:
        # Fully x.y.z match for swift versions
        match = re.match(r'^(\d+)\.(\d+)\.(\d+)', vers)
    else:
        # x.y match only for 20XX.X
        # and ignore patch level for other packages
        match = re.match(r'^(\d+)\.(\d+)', vers)

    if match:
        vers = match.group(0)

    # Generate a major version number for newer semantic
    # versions of openstack projects
    major_vers = vers.split('.')[0]
    # >= Liberty independent project versions
    if (package in PACKAGE_CODENAMES and
            major_vers in PACKAGE_CODENAMES[package]):
        return PACKAGE_CODENAMES[package][major_vers]
    else:
        # < Liberty co-ordinated project versions
        try:
            if 'swift' in pkg.name:
                return get_swift_codename(vers)
            else:
                return OPENSTACK_CODENAMES[vers]
        except KeyError:
            if not fatal:
                return None
            e = 'Could not determine OpenStack codename for version %s' % vers
            error_out(e)


def get_os_version_package(pkg, fatal=True):
    '''Derive OpenStack version number from an installed package.'''
    codename = get_os_codename_package(pkg, fatal=fatal)

    if not codename:
        return None

    if 'swift' in pkg:
        vers_map = SWIFT_CODENAMES
        for cname, version in six.iteritems(vers_map):
            if cname == codename:
                return version[-1]
    else:
        vers_map = OPENSTACK_CODENAMES
        for version, cname in six.iteritems(vers_map):
            if cname == codename:
                return version
    # e = "Could not determine OpenStack version for package: %s" % pkg
    # error_out(e)


def get_installed_os_version():
    """Determine the OpenStack release code name from openstack-release pkg.

    This uses the "openstack-release" pkg (if it exists) to return the
    OpenStack release codename (e.g. usurri, mitaka, ocata, etc.)

    Note, it caches the result so that it is only done once per hook.

    :returns: the OpenStack release codename, if available
    :rtype: Optional[str]
    """
    @cached
    def _do_install():
        apt_install(filter_installed_packages(['openstack-release']),
                    fatal=False, quiet=True)

    _do_install()
    return openstack_release().get('OPENSTACK_CODENAME')


@cached
def openstack_release():
    """Return /etc/os-release in a dict."""
    d = {}
    try:
        with open('/etc/openstack-release', 'r') as lsb:
            for l in lsb:
                s = l.split('=')
                if len(s) != 2:
                    continue
                d[s[0].strip()] = s[1].strip()
    except FileNotFoundError:
        pass
    return d


# Module local cache variable for the os_release.
_os_rel = None


def reset_os_release():
    '''Unset the cached os_release version'''
    global _os_rel
    _os_rel = None


def os_release(package, base=None, reset_cache=False, source_key=None):
    """Returns OpenStack release codename from a cached global.

    If reset_cache then unset the cached os_release version and return the
    freshly determined version.

    If the codename can not be determined from either an installed package or
    the installation source, the earliest release supported by the charm should
    be returned.

    :param package: Name of package to determine release from
    :type package: str
    :param base: Fallback codename if endavours to determine from package fail
    :type base: Optional[str]
    :param reset_cache: Reset any cached codename value
    :type reset_cache: bool
    :param source_key: Name of source configuration option
                       (default: 'openstack-origin')
    :type source_key: Optional[str]
    :returns: OpenStack release codename
    :rtype: str
    """
    source_key = source_key or 'openstack-origin'
    if not base:
        base = UBUNTU_OPENSTACK_RELEASE[lsb_release()['DISTRIB_CODENAME']]
    global _os_rel
    if reset_cache:
        reset_os_release()
    if _os_rel:
        return _os_rel
    _os_rel = (
        get_os_codename_package(package, fatal=False) or
        get_os_codename_install_source(config(source_key)) or
        base)
    return _os_rel


@deprecate("moved to charmhelpers.fetch.import_key()", "2017-07", log=juju_log)
def import_key(keyid):
    """Import a key, either ASCII armored, or a GPG key id.

    @param keyid: the key in ASCII armor format, or a GPG key id.
    @raises SystemExit() via sys.exit() on failure.
    """
    try:
        return fetch_import_key(keyid)
    except GPGKeyError as e:
        error_out("Could not import key: {}".format(str(e)))


def get_source_and_pgp_key(source_and_key):
    """Look for a pgp key ID or ascii-armor key in the given input.

    :param source_and_key: String, "source_spec|keyid" where '|keyid' is
        optional.
    :returns (source_spec, key_id OR None) as a tuple.  Returns None for key_id
        if there was no '|' in the source_and_key string.
    """
    try:
        source, key = source_and_key.split('|', 2)
        return source, key or None
    except ValueError:
        return source_and_key, None


@deprecate("use charmhelpers.fetch.add_source() instead.",
           "2017-07", log=juju_log)
def configure_installation_source(source_plus_key):
    """Configure an installation source.

    The functionality is provided by charmhelpers.fetch.add_source()
    The difference between the two functions is that add_source() signature
    requires the key to be passed directly, whereas this function passes an
    optional key by appending '|<key>' to the end of the source specification
    'source'.

    Another difference from add_source() is that the function calls sys.exit(1)
    if the configuration fails, whereas add_source() raises
    SourceConfigurationError().  Another difference, is that add_source()
    silently fails (with a juju_log command) if there is no matching source to
    configure, whereas this function fails with a sys.exit(1)

    :param source: String_plus_key -- see above for details.

    Note that the behaviour on error is to log the error to the juju log and
    then call sys.exit(1).
    """
    if source_plus_key.startswith('snap'):
        # Do nothing for snap installs
        return
    # extract the key if there is one, denoted by a '|' in the rel
    source, key = get_source_and_pgp_key(source_plus_key)

    # handle the ordinary sources via add_source
    try:
        fetch_add_source(source, key, fail_invalid=True)
    except SourceConfigError as se:
        error_out(str(se))


def config_value_changed(option):
    """
    Determine if config value changed since last call to this function.
    """
    hook_data = unitdata.HookData()
    with hook_data():
        db = unitdata.kv()
        current = config(option)
        saved = db.get(option)
        db.set(option, current)
        if saved is None:
            return False
        return current != saved


def get_endpoint_key(service_name, relation_id, unit_name):
    """Return the key used to refer to an ep changed notification from a unit.

    :param service_name: Service name eg nova, neutron, placement etc
    :type service_name: str
    :param relation_id: The id of the relation the unit is on.
    :type relation_id: str
    :param unit_name: The name of the unit publishing the notification.
    :type unit_name: str
    :returns: The key used to refer to an ep changed notification from a unit
    :rtype: str
    """
    return '{}-{}-{}'.format(
        service_name,
        relation_id.replace(':', '_'),
        unit_name.replace('/', '_'))


def get_endpoint_notifications(service_names, rel_name='identity-service'):
    """Return all notifications for the given services.

    :param service_names: List of service name.
    :type service_name: List
    :param rel_name: Name of the relation to query
    :type rel_name: str
    :returns: A dict containing the source of the notification and its nonce.
    :rtype: Dict[str, str]
    """
    notifications = {}
    for rid in relation_ids(rel_name):
        for unit in related_units(relid=rid):
            ep_changed_json = relation_get(
                rid=rid,
                unit=unit,
                attribute='ep_changed')
            if ep_changed_json:
                ep_changed = json.loads(ep_changed_json)
                for service in service_names:
                    if ep_changed.get(service):
                        key = get_endpoint_key(service, rid, unit)
                        notifications[key] = ep_changed[service]
    return notifications


def endpoint_changed(service_name, rel_name='identity-service'):
    """Whether a new notification has been received for an endpoint.

    :param service_name: Service name eg nova, neutron, placement etc
    :type service_name: str
    :param rel_name: Name of the relation to query
    :type rel_name: str
    :returns: Whether endpoint has changed
    :rtype: bool
    """
    changed = False
    with unitdata.HookData()() as t:
        db = t[0]
        notifications = get_endpoint_notifications(
            [service_name],
            rel_name=rel_name)
        for key, nonce in notifications.items():
            if db.get(key) != nonce:
                juju_log(('New endpoint change notification found: '
                          '{}={}').format(key, nonce),
                         'INFO')
                changed = True
                break
    return changed


def save_endpoint_changed_triggers(service_names, rel_name='identity-service'):
    """Save the endpoint triggers in  db so it can be tracked if they changed.

    :param service_names: List of service name.
    :type service_name: List
    :param rel_name: Name of the relation to query
    :type rel_name: str
    """
    with unitdata.HookData()() as t:
        db = t[0]
        notifications = get_endpoint_notifications(
            service_names,
            rel_name=rel_name)
        for key, nonce in notifications.items():
            db.set(key, nonce)


def save_script_rc(script_path="scripts/scriptrc", **env_vars):
    """
    Write an rc file in the charm-delivered directory containing
    exported environment variables provided by env_vars. Any charm scripts run
    outside the juju hook environment can source this scriptrc to obtain
    updated config information necessary to perform health checks or
    service changes.
    """
    juju_rc_path = "%s/%s" % (charm_dir(), script_path)
    if not os.path.exists(os.path.dirname(juju_rc_path)):
        os.mkdir(os.path.dirname(juju_rc_path))
    with open(juju_rc_path, 'wt') as rc_script:
        rc_script.write(
            "#!/bin/bash\n")
        [rc_script.write('export %s=%s\n' % (u, p))
         for u, p in six.iteritems(env_vars) if u != "script_path"]


def openstack_upgrade_available(package):
    """
    Determines if an OpenStack upgrade is available from installation
    source, based on version of installed package.

    :param package: str: Name of installed package.

    :returns: bool:    : Returns True if configured installation source offers
                         a newer version of package.
    """

    src = config('openstack-origin')
    cur_vers = get_os_version_package(package)
    if not cur_vers:
        # The package has not been installed yet do not attempt upgrade
        return False
    if "swift" in package:
        codename = get_os_codename_install_source(src)
        avail_vers = get_os_version_codename_swift(codename)
    else:
        try:
            avail_vers = get_os_version_install_source(src)
        except Exception:
            avail_vers = cur_vers
    apt.init()
    return apt.version_compare(avail_vers, cur_vers) >= 1


def ensure_block_device(block_device):
    '''
    Confirm block_device, create as loopback if necessary.

    :param block_device: str: Full path of block device to ensure.

    :returns: str: Full path of ensured block device.
    '''
    _none = ['None', 'none', None]
    if (block_device in _none):
        error_out('prepare_storage(): Missing required input: block_device=%s.'
                  % block_device)

    if block_device.startswith('/dev/'):
        bdev = block_device
    elif block_device.startswith('/'):
        _bd = block_device.split('|')
        if len(_bd) == 2:
            bdev, size = _bd
        else:
            bdev = block_device
            size = DEFAULT_LOOPBACK_SIZE
        bdev = ensure_loopback_device(bdev, size)
    else:
        bdev = '/dev/%s' % block_device

    if not is_block_device(bdev):
        error_out('Failed to locate valid block device at %s' % bdev)

    return bdev


def clean_storage(block_device):
    '''
    Ensures a block device is clean.  That is:
        - unmounted
        - any lvm volume groups are deactivated
        - any lvm physical device signatures removed
        - partition table wiped

    :param block_device: str: Full path to block device to clean.
    '''
    for mp, d in mounts():
        if d == block_device:
            juju_log('clean_storage(): %s is mounted @ %s, unmounting.' %
                     (d, mp), level=INFO)
            umount(mp, persist=True)

    if is_lvm_physical_volume(block_device):
        deactivate_lvm_volume_group(block_device)
        remove_lvm_physical_volume(block_device)
    else:
        zap_disk(block_device)


is_ip = ip.is_ip
ns_query = ip.ns_query
get_host_ip = ip.get_host_ip
get_hostname = ip.get_hostname


def get_matchmaker_map(mm_file='/etc/oslo/matchmaker_ring.json'):
    mm_map = {}
    if os.path.isfile(mm_file):
        with open(mm_file, 'r') as f:
            mm_map = json.load(f)
    return mm_map


def sync_db_with_multi_ipv6_addresses(database, database_user,
                                      relation_prefix=None):
    hosts = get_ipv6_addr(dynamic_only=False)

    if config('vip'):
        vips = config('vip').split()
        for vip in vips:
            if vip and is_ipv6(vip):
                hosts.append(vip)

    kwargs = {'database': database,
              'username': database_user,
              'hostname': json.dumps(hosts)}

    if relation_prefix:
        for key in list(kwargs.keys()):
            kwargs["%s_%s" % (relation_prefix, key)] = kwargs[key]
            del kwargs[key]

    for rid in relation_ids('shared-db'):
        relation_set(relation_id=rid, **kwargs)


def os_requires_version(ostack_release, pkg):
    """
    Decorator for hook to specify minimum supported release
    """
    def wrap(f):
        @wraps(f)
        def wrapped_f(*args):
            if os_release(pkg) < ostack_release:
                raise Exception("This hook is not supported on releases"
                                " before %s" % ostack_release)
            f(*args)
        return wrapped_f
    return wrap


def os_workload_status(configs, required_interfaces, charm_func=None):
    """
    Decorator to set workload status based on complete contexts
    """
    def wrap(f):
        @wraps(f)
        def wrapped_f(*args, **kwargs):
            # Run the original function first
            f(*args, **kwargs)
            # Set workload status now that contexts have been
            # acted on
            set_os_workload_status(configs, required_interfaces, charm_func)
        return wrapped_f
    return wrap


def set_os_workload_status(configs, required_interfaces, charm_func=None,
                           services=None, ports=None):
    """Set the state of the workload status for the charm.

    This calls _determine_os_workload_status() to get the new state, message
    and sets the status using status_set()

    @param configs: a templating.OSConfigRenderer() object
    @param required_interfaces: {generic: [specific, specific2, ...]}
    @param charm_func: a callable function that returns state, message. The
                       signature is charm_func(configs) -> (state, message)
    @param services: list of strings OR dictionary specifying services/ports
    @param ports: OPTIONAL list of port numbers.
    @returns state, message: the new workload status, user message
    """
    state, message = _determine_os_workload_status(
        configs, required_interfaces, charm_func, services, ports)
    status_set(state, message)


def _determine_os_workload_status(
        configs, required_interfaces, charm_func=None,
        services=None, ports=None):
    """Determine the state of the workload status for the charm.

    This function returns the new workload status for the charm based
    on the state of the interfaces, the paused state and whether the
    services are actually running and any specified ports are open.

    This checks:

     1. if the unit should be paused, that it is actually paused.  If so the
        state is 'maintenance' + message, else 'broken'.
     2. that the interfaces/relations are complete.  If they are not then
        it sets the state to either 'broken' or 'waiting' and an appropriate
        message.
     3. If all the relation data is set, then it checks that the actual
        services really are running.  If not it sets the state to 'broken'.

    If everything is okay then the state returns 'active'.

    @param configs: a templating.OSConfigRenderer() object
    @param required_interfaces: {generic: [specific, specific2, ...]}
    @param charm_func: a callable function that returns state, message. The
                       signature is charm_func(configs) -> (state, message)
    @param services: list of strings OR dictionary specifying services/ports
    @param ports: OPTIONAL list of port numbers.
    @returns state, message: the new workload status, user message
    """
    state, message = _ows_check_if_paused(services, ports)

    if state is None:
        state, message = _ows_check_generic_interfaces(
            configs, required_interfaces)

    if state != 'maintenance' and charm_func:
        # _ows_check_charm_func() may modify the state, message
        state, message = _ows_check_charm_func(
            state, message, lambda: charm_func(configs))

    if state is None:
        state, message = _ows_check_services_running(services, ports)

    if state is None:
        state = 'active'
        message = "Unit is ready"
        juju_log(message, 'INFO')

    try:
        if config(POLICYD_CONFIG_NAME):
            message = "{} {}".format(policyd_status_message_prefix(), message)
        # Get deferred restarts events that have been triggered by a policy
        # written by this charm.
        deferred_restarts = list(set(
            [e.service
             for e in deferred_events.get_deferred_restarts()
             if e.policy_requestor_name == ch_service_name()]))
        if deferred_restarts:
            svc_msg = "Services queued for restart: {}".format(
                ', '.join(sorted(deferred_restarts)))
            message = "{}. {}".format(message, svc_msg)
        deferred_hooks = deferred_events.get_deferred_hooks()
        if deferred_hooks:
            svc_msg = "Hooks skipped due to disabled auto restarts: {}".format(
                ', '.join(sorted(deferred_hooks)))
            message = "{}. {}".format(message, svc_msg)

    except Exception:
        pass

    return state, message


def _ows_check_if_paused(services=None, ports=None):
    """Check if the unit is supposed to be paused, and if so check that the
    services/ports (if passed) are actually stopped/not being listened to.

    If the unit isn't supposed to be paused, just return None, None

    If the unit is performing a series upgrade, return a message indicating
    this.

    @param services: OPTIONAL services spec or list of service names.
    @param ports: OPTIONAL list of port numbers.
    @returns state, message or None, None
    """
    if is_unit_upgrading_set():
        state, message = check_actually_paused(services=services,
                                               ports=ports)
        if state is None:
            # we're paused okay, so set maintenance and return
            state = "blocked"
            message = ("Ready for do-release-upgrade and reboot. "
                       "Set complete when finished.")
        return state, message

    if is_unit_paused_set():
        state, message = check_actually_paused(services=services,
                                               ports=ports)
        if state is None:
            # we're paused okay, so set maintenance and return
            state = "maintenance"
            message = "Paused. Use 'resume' action to resume normal service."
        return state, message
    return None, None


def _ows_check_generic_interfaces(configs, required_interfaces):
    """Check the complete contexts to determine the workload status.

     - Checks for missing or incomplete contexts
     - juju log details of missing required data.
     - determines the correct workload status
     - creates an appropriate message for status_set(...)

    if there are no problems then the function returns None, None

    @param configs: a templating.OSConfigRenderer() object
    @params required_interfaces: {generic_interface: [specific_interface], }
    @returns state, message or None, None
    """
    incomplete_rel_data = incomplete_relation_data(configs,
                                                   required_interfaces)
    state = None
    message = None
    missing_relations = set()
    incomplete_relations = set()

    for generic_interface, relations_states in incomplete_rel_data.items():
        related_interface = None
        missing_data = {}
        # Related or not?
        for interface, relation_state in relations_states.items():
            if relation_state.get('related'):
                related_interface = interface
                missing_data = relation_state.get('missing_data')
                break
        # No relation ID for the generic_interface?
        if not related_interface:
            juju_log("{} relation is missing and must be related for "
                     "functionality. ".format(generic_interface), 'WARN')
            state = 'blocked'
            missing_relations.add(generic_interface)
        else:
            # Relation ID eists but no related unit
            if not missing_data:
                # Edge case - relation ID exists but departings
                _hook_name = hook_name()
                if (('departed' in _hook_name or 'broken' in _hook_name) and
                        related_interface in _hook_name):
                    state = 'blocked'
                    missing_relations.add(generic_interface)
                    juju_log("{} relation's interface, {}, "
                             "relationship is departed or broken "
                             "and is required for functionality."
                             "".format(generic_interface, related_interface),
                             "WARN")
                # Normal case relation ID exists but no related unit
                # (joining)
                else:
                    juju_log("{} relations's interface, {}, is related but has"
                             " no units in the relation."
                             "".format(generic_interface, related_interface),
                             "INFO")
            # Related unit exists and data missing on the relation
            else:
                juju_log("{} relation's interface, {}, is related awaiting "
                         "the following data from the relationship: {}. "
                         "".format(generic_interface, related_interface,
                                   ", ".join(missing_data)), "INFO")
            if state != 'blocked':
                state = 'waiting'
            if generic_interface not in missing_relations:
                incomplete_relations.add(generic_interface)

    if missing_relations:
        message = "Missing relations: {}".format(", ".join(missing_relations))
        if incomplete_relations:
            message += "; incomplete relations: {}" \
                       "".format(", ".join(incomplete_relations))
        state = 'blocked'
    elif incomplete_relations:
        message = "Incomplete relations: {}" \
                  "".format(", ".join(incomplete_relations))
        state = 'waiting'

    return state, message


def _ows_check_charm_func(state, message, charm_func_with_configs):
    """Run a custom check function for the charm to see if it wants to
    change the state.  This is only run if not in 'maintenance' and
    tests to see if the new state is more important that the previous
    one determined by the interfaces/relations check.

    @param state: the previously determined state so far.
    @param message: the user orientated message so far.
    @param charm_func: a callable function that returns state, message
    @returns state, message strings.
    """
    if charm_func_with_configs:
        charm_state, charm_message = charm_func_with_configs()
        if (charm_state != 'active' and
                charm_state != 'unknown' and
                charm_state is not None):
            state = workload_state_compare(state, charm_state)
            if message:
                charm_message = charm_message.replace("Incomplete relations: ",
                                                      "")
                message = "{}, {}".format(message, charm_message)
            else:
                message = charm_message
    return state, message


def _ows_check_services_running(services, ports):
    """Check that the services that should be running are actually running
    and that any ports specified are being listened to.

    @param services: list of strings OR dictionary specifying services/ports
    @param ports: list of ports
    @returns state, message: strings or None, None
    """
    messages = []
    state = None
    if services is not None:
        services = _extract_services_list_helper(services)
        services_running, running = _check_running_services(services)
        if not all(running):
            messages.append(
                "Services not running that should be: {}"
                .format(", ".join(_filter_tuples(services_running, False))))
            state = 'blocked'
        # also verify that the ports that should be open are open
        # NB, that ServiceManager objects only OPTIONALLY have ports
        map_not_open, ports_open = (
            _check_listening_on_services_ports(services))
        if not all(ports_open):
            # find which service has missing ports. They are in service
            # order which makes it a bit easier.
            message_parts = {service: ", ".join([str(v) for v in open_ports])
                             for service, open_ports in map_not_open.items()}
            message = ", ".join(
                ["{}: [{}]".format(s, sp) for s, sp in message_parts.items()])
            messages.append(
                "Services with ports not open that should be: {}"
                .format(message))
            state = 'blocked'

    if ports is not None:
        # and we can also check ports which we don't know the service for
        ports_open, ports_open_bools = _check_listening_on_ports_list(ports)
        if not all(ports_open_bools):
            messages.append(
                "Ports which should be open, but are not: {}"
                .format(", ".join([str(p) for p, v in ports_open
                                   if not v])))
            state = 'blocked'

    if state is not None:
        message = "; ".join(messages)
        return state, message

    return None, None


def _extract_services_list_helper(services):
    """Extract a OrderedDict of {service: [ports]} of the supplied services
    for use by the other functions.

    The services object can either be:
      - None : no services were passed (an empty dict is returned)
      - a list of strings
      - A dictionary (optionally OrderedDict) {service_name: {'service': ..}}
      - An array of [{'service': service_name, ...}, ...]

    @param services: see above
    @returns OrderedDict(service: [ports], ...)
    """
    if services is None:
        return {}
    if isinstance(services, dict):
        services = services.values()
    # either extract the list of services from the dictionary, or if
    # it is a simple string, use that. i.e. works with mixed lists.
    _s = OrderedDict()
    for s in services:
        if isinstance(s, dict) and 'service' in s:
            _s[s['service']] = s.get('ports', [])
        if isinstance(s, str):
            _s[s] = []
    return _s


def _check_running_services(services):
    """Check that the services dict provided is actually running and provide
    a list of (service, boolean) tuples for each service.

    Returns both a zipped list of (service, boolean) and a list of booleans
    in the same order as the services.

    @param services: OrderedDict of strings: [ports], one for each service to
                     check.
    @returns [(service, boolean), ...], : results for checks
             [boolean]                  : just the result of the service checks
    """
    services_running = [service_running(s) for s in services]
    return list(zip(services, services_running)), services_running


def _check_listening_on_services_ports(services, test=False):
    """Check that the unit is actually listening (has the port open) on the
    ports that the service specifies are open. If test is True then the
    function returns the services with ports that are open rather than
    closed.

    Returns an OrderedDict of service: ports and a list of booleans

    @param services: OrderedDict(service: [port, ...], ...)
    @param test: default=False, if False, test for closed, otherwise open.
    @returns OrderedDict(service: [port-not-open, ...]...), [boolean]
    """
    test = not(not(test))  # ensure test is True or False
    all_ports = list(itertools.chain(*services.values()))
    ports_states = [port_has_listener('0.0.0.0', p) for p in all_ports]
    map_ports = OrderedDict()
    matched_ports = [p for p, opened in zip(all_ports, ports_states)
                     if opened == test]  # essentially opened xor test
    for service, ports in services.items():
        set_ports = set(ports).intersection(matched_ports)
        if set_ports:
            map_ports[service] = set_ports
    return map_ports, ports_states


def _check_listening_on_ports_list(ports):
    """Check that the ports list given are being listened to

    Returns a list of ports being listened to and a list of the
    booleans.

    @param ports: LIST of port numbers.
    @returns [(port_num, boolean), ...], [boolean]
    """
    ports_open = [port_has_listener('0.0.0.0', p) for p in ports]
    return zip(ports, ports_open), ports_open


def _filter_tuples(services_states, state):
    """Return a simple list from a list of tuples according to the condition

    @param services_states: LIST of (string, boolean): service and running
           state.
    @param state: Boolean to match the tuple against.
    @returns [LIST of strings] that matched the tuple RHS.
    """
    return [s for s, b in services_states if b == state]


def workload_state_compare(current_workload_state, workload_state):
    """ Return highest priority of two states"""
    hierarchy = {'unknown': -1,
                 'active': 0,
                 'maintenance': 1,
                 'waiting': 2,
                 'blocked': 3,
                 }

    if hierarchy.get(workload_state) is None:
        workload_state = 'unknown'
    if hierarchy.get(current_workload_state) is None:
        current_workload_state = 'unknown'

    # Set workload_state based on hierarchy of statuses
    if hierarchy.get(current_workload_state) > hierarchy.get(workload_state):
        return current_workload_state
    else:
        return workload_state


def incomplete_relation_data(configs, required_interfaces):
    """Check complete contexts against required_interfaces
    Return dictionary of incomplete relation data.

    configs is an OSConfigRenderer object with configs registered

    required_interfaces is a dictionary of required general interfaces
    with dictionary values of possible specific interfaces.
    Example:
    required_interfaces = {'database': ['shared-db', 'pgsql-db']}

    The interface is said to be satisfied if anyone of the interfaces in the
    list has a complete context.

    Return dictionary of incomplete or missing required contexts with relation
    status of interfaces and any missing data points. Example:
        {'message':
             {'amqp': {'missing_data': ['rabbitmq_password'], 'related': True},
              'zeromq-configuration': {'related': False}},
         'identity':
             {'identity-service': {'related': False}},
         'database':
             {'pgsql-db': {'related': False},
              'shared-db': {'related': True}}}
    """
    complete_ctxts = configs.complete_contexts()
    incomplete_relations = [
        svc_type
        for svc_type, interfaces in required_interfaces.items()
        if not set(interfaces).intersection(complete_ctxts)]
    return {
        i: configs.get_incomplete_context_data(required_interfaces[i])
        for i in incomplete_relations}


def do_action_openstack_upgrade(package, upgrade_callback, configs,
                                force_upgrade=False):
    """Perform action-managed OpenStack upgrade.

    Upgrades packages to the configured openstack-origin version and sets
    the corresponding action status as a result.

    If the charm was installed from source we cannot upgrade it.
    For backwards compatibility a config flag (action-managed-upgrade) must
    be set for this code to run, otherwise a full service level upgrade will
    fire on config-changed.

    @param package: package name for determining if upgrade available
    @param upgrade_callback: function callback to charm's upgrade function
    @param configs: templating object derived from OSConfigRenderer class
    @param force_upgrade: perform dist-upgrade regardless of new openstack

    @return: True if upgrade successful; False if upgrade failed or skipped
    """
    ret = False

    if openstack_upgrade_available(package) or force_upgrade:
        if config('action-managed-upgrade'):
            juju_log('Upgrading OpenStack release')

            try:
                upgrade_callback(configs=configs)
                action_set({'outcome': 'success, upgrade completed.'})
                ret = True
            except Exception:
                action_set({'outcome': 'upgrade failed, see traceback.'})
                action_set({'traceback': traceback.format_exc()})
                action_fail('do_openstack_upgrade resulted in an '
                            'unexpected error')
        else:
            action_set({'outcome': 'action-managed-upgrade config is '
                                   'False, skipped upgrade.'})
    else:
        action_set({'outcome': 'no upgrade available.'})

    return ret


def remote_restart(rel_name, remote_service=None):
    trigger = {
        'restart-trigger': str(uuid.uuid4()),
    }
    if remote_service:
        trigger['remote-service'] = remote_service
    for rid in relation_ids(rel_name):
        # This subordinate can be related to two separate services using
        # different subordinate relations so only issue the restart if
        # the principle is connected down the relation we think it is
        if related_units(relid=rid):
            relation_set(relation_id=rid,
                         relation_settings=trigger,
                         )


def check_actually_paused(services=None, ports=None):
    """Check that services listed in the services object and ports
    are actually closed (not listened to), to verify that the unit is
    properly paused.

    @param services: See _extract_services_list_helper
    @returns status, : string for status (None if okay)
             message : string for problem for status_set
    """
    state = None
    message = None
    messages = []
    if services is not None:
        services = _extract_services_list_helper(services)
        services_running, services_states = _check_running_services(services)
        if any(services_states):
            # there shouldn't be any running so this is a problem
            messages.append("these services running: {}"
                            .format(", ".join(
                                _filter_tuples(services_running, True))))
            state = "blocked"
        ports_open, ports_open_bools = (
            _check_listening_on_services_ports(services, True))
        if any(ports_open_bools):
            message_parts = {service: ", ".join([str(v) for v in open_ports])
                             for service, open_ports in ports_open.items()}
            message = ", ".join(
                ["{}: [{}]".format(s, sp) for s, sp in message_parts.items()])
            messages.append(
                "these service:ports are open: {}".format(message))
            state = 'blocked'
    if ports is not None:
        ports_open, bools = _check_listening_on_ports_list(ports)
        if any(bools):
            messages.append(
                "these ports which should be closed, but are open: {}"
                .format(", ".join([str(p) for p, v in ports_open if v])))
            state = 'blocked'
    if messages:
        message = ("Services should be paused but {}"
                   .format(", ".join(messages)))
    return state, message


def set_unit_paused():
    """Set the unit to a paused state in the local kv() store.
    This does NOT actually pause the unit
    """
    with unitdata.HookData()() as t:
        kv = t[0]
        kv.set('unit-paused', True)


def clear_unit_paused():
    """Clear the unit from a paused state in the local kv() store
    This does NOT actually restart any services - it only clears the
    local state.
    """
    with unitdata.HookData()() as t:
        kv = t[0]
        kv.set('unit-paused', False)


def is_unit_paused_set():
    """Return the state of the kv().get('unit-paused').
    This does NOT verify that the unit really is paused.

    To help with units that don't have HookData() (testing)
    if it excepts, return False
    """
    try:
        with unitdata.HookData()() as t:
            kv = t[0]
            # transform something truth-y into a Boolean.
            return not(not(kv.get('unit-paused')))
    except Exception:
        return False


def is_hook_allowed(hookname, check_deferred_restarts=True):
    """Check if hook can run.

    :param hookname: Name of hook to check..
    :type hookname: str
    :param check_deferred_restarts: Whether to check deferred restarts.
    :type check_deferred_restarts: bool
    """
    permitted = True
    reasons = []
    if is_unit_paused_set():
        reasons.append(
            "Unit is pause or upgrading. Skipping {}".format(hookname))
        permitted = False

    if check_deferred_restarts:
        if deferred_events.is_restart_permitted():
            permitted = True
            deferred_events.clear_deferred_hook(hookname)
        else:
            if not config().changed('enable-auto-restarts'):
                deferred_events.set_deferred_hook(hookname)
            reasons.append("auto restarts are disabled")
            permitted = False
    return permitted, " and ".join(reasons)


def manage_payload_services(action, services=None, charm_func=None):
    """Run an action against all services.

    An optional charm_func() can be called. It should raise an Exception to
    indicate that the function failed. If it was successful it should return
    None or an optional message.

    The signature for charm_func is:
    charm_func() -> message: str

    charm_func() is executed after any services are stopped, if supplied.

    The services object can either be:
      - None : no services were passed (an empty dict is returned)
      - a list of strings
      - A dictionary (optionally OrderedDict) {service_name: {'service': ..}}
      - An array of [{'service': service_name, ...}, ...]

    :param action: Action to run: pause, resume, start or stop.
    :type action: str
    :param services: See above
    :type services: See above
    :param charm_func: function to run for custom charm pausing.
    :type charm_func: f()
    :returns: Status boolean and list of messages
    :rtype: (bool, [])
    :raises: RuntimeError
    """
    actions = {
        'pause': service_pause,
        'resume': service_resume,
        'start': service_start,
        'stop': service_stop}
    action = action.lower()
    if action not in actions.keys():
        raise RuntimeError(
            "action: {} must be one of: {}".format(action,
                                                   ', '.join(actions.keys())))
    services = _extract_services_list_helper(services)
    messages = []
    success = True
    if services:
        for service in services.keys():
            rc = actions[action](service)
            if not rc:
                success = False
                messages.append("{} didn't {} cleanly.".format(service,
                                                               action))
    if charm_func:
        try:
            message = charm_func()
            if message:
                messages.append(message)
        except Exception as e:
            success = False
            messages.append(str(e))
    return success, messages


def make_wait_for_ports_barrier(ports, retry_count=5):
    """Make a function to wait for port shutdowns.

    Create a function which closes over the provided ports. The function will
    retry probing ports until they are closed or the retry count has been reached.

    """
    @decorators.retry_on_predicate(retry_count, operator.not_, base_delay=0.1)
    def retry_port_check():
        _, ports_states = _check_listening_on_ports_list(ports)
        juju_log("Probe ports {}, result: {}".format(ports, ports_states), level="DEBUG")
        return any(ports_states)
    return retry_port_check


def pause_unit(assess_status_func, services=None, ports=None,
               charm_func=None):
    """Pause a unit by stopping the services and setting 'unit-paused'
    in the local kv() store.

    Also checks that the services have stopped and ports are no longer
    being listened to.

    An optional charm_func() can be called that can either raise an
    Exception or return non None, None to indicate that the unit
    didn't pause cleanly.

    The signature for charm_func is:
    charm_func() -> message: string

    charm_func() is executed after any services are stopped, if supplied.

    The services object can either be:
      - None : no services were passed (an empty dict is returned)
      - a list of strings
      - A dictionary (optionally OrderedDict) {service_name: {'service': ..}}
      - An array of [{'service': service_name, ...}, ...]

    @param assess_status_func: (f() -> message: string | None) or None
    @param services: OPTIONAL see above
    @param ports: OPTIONAL list of port
    @param charm_func: function to run for custom charm pausing.
    @returns None
    @raises Exception(message) on an error for action_fail().
    """
    _, messages = manage_payload_services(
        'pause',
        services=services,
        charm_func=charm_func)
    set_unit_paused()

    if assess_status_func:
        message = assess_status_func()
        if message:
            messages.append(message)
    if messages and not is_unit_upgrading_set():
        raise Exception("Couldn't pause: {}".format("; ".join(messages)))


def resume_unit(assess_status_func, services=None, ports=None,
                charm_func=None):
    """Resume a unit by starting the services and clearning 'unit-paused'
    in the local kv() store.

    Also checks that the services have started and ports are being listened to.

    An optional charm_func() can be called that can either raise an
    Exception or return non None to indicate that the unit
    didn't resume cleanly.

    The signature for charm_func is:
    charm_func() -> message: string

    charm_func() is executed after any services are started, if supplied.

    The services object can either be:
      - None : no services were passed (an empty dict is returned)
      - a list of strings
      - A dictionary (optionally OrderedDict) {service_name: {'service': ..}}
      - An array of [{'service': service_name, ...}, ...]

    @param assess_status_func: (f() -> message: string | None) or None
    @param services: OPTIONAL see above
    @param ports: OPTIONAL list of port
    @param charm_func: function to run for custom charm resuming.
    @returns None
    @raises Exception(message) on an error for action_fail().
    """
    _, messages = manage_payload_services(
        'resume',
        services=services,
        charm_func=charm_func)
    clear_unit_paused()
    if assess_status_func:
        message = assess_status_func()
        if message:
            messages.append(message)
    if messages:
        raise Exception("Couldn't resume: {}".format("; ".join(messages)))


def restart_services_action(services=None, when_all_stopped_func=None,
                            deferred_only=None):
    """Manage a service restart request via charm action.

    :param services: Services to be restarted
    :type model_name: List[str]
    :param when_all_stopped_func: Function to call when all services are
                                  stopped.
    :type when_all_stopped_func: Callable[]
    :param model_name: Only restart services which have a deferred restart
                       event.
    :type model_name: bool
    """
    if services and deferred_only:
        raise ValueError(
            "services and deferred_only are mutually exclusive")
    if deferred_only:
        services = list(set(
            [a.service for a in deferred_events.get_deferred_restarts()]))
    _, messages = manage_payload_services(
        'stop',
        services=services,
        charm_func=when_all_stopped_func)
    if messages:
        raise ServiceActionError(
            "Error processing service stop request: {}".format(
                "; ".join(messages)))
    _, messages = manage_payload_services(
        'start',
        services=services)
    if messages:
        raise ServiceActionError(
            "Error processing service start request: {}".format(
                "; ".join(messages)))
    deferred_events.clear_deferred_restarts(services)


def make_assess_status_func(*args, **kwargs):
    """Creates an assess_status_func() suitable for handing to pause_unit()
    and resume_unit().

    This uses the _determine_os_workload_status(...) function to determine
    what the workload_status should be for the unit.  If the unit is
    not in maintenance or active states, then the message is returned to
    the caller.  This is so an action that doesn't result in either a
    complete pause or complete resume can signal failure with an action_fail()
    """
    def _assess_status_func():
        state, message = _determine_os_workload_status(*args, **kwargs)
        status_set(state, message)
        if state not in ['maintenance', 'active']:
            return message
        return None

    return _assess_status_func


def pausable_restart_on_change(restart_map, stopstart=False,
                               restart_functions=None,
                               can_restart_now_f=None,
                               post_svc_restart_f=None,
                               pre_restarts_wait_f=None):
    """A restart_on_change decorator that checks to see if the unit is
    paused. If it is paused then the decorated function doesn't fire.

    This is provided as a helper, as the @restart_on_change(...) decorator
    is in core.host, yet the openstack specific helpers are in this file
    (contrib.openstack.utils).  Thus, this needs to be an optional feature
    for openstack charms (or charms that wish to use the openstack
    pause/resume type features).

    It is used as follows:

        from contrib.openstack.utils import (
            pausable_restart_on_change as restart_on_change)

        @restart_on_change(restart_map, stopstart=<boolean>)
        def some_hook(...):
            pass

    see core.utils.restart_on_change() for more details.

    Note restart_map can be a callable, in which case, restart_map is only
    evaluated at runtime.  This means that it is lazy and the underlying
    function won't be called if the decorated function is never called.  Note,
    retains backwards compatibility for passing a non-callable dictionary.

    :param f: function to decorate.
    :type f: Callable
    :param restart_map: Optionally callable, which then returns the restart_map or
                        the restart map {conf_file: [services]}
    :type restart_map: Union[Callable[[],], Dict[str, List[str,]]
    :param stopstart: whether to stop, start or restart a service
    :type stopstart: booleean
    :param restart_functions: nonstandard functions to use to restart services
                              {svc: func, ...}
    :type restart_functions: Dict[str, Callable[[str], None]]
    :param can_restart_now_f: A function used to check if the restart is
                              permitted.
    :type can_restart_now_f: Callable[[str, List[str]], boolean]
    :param post_svc_restart_f: A function run after a service has
                               restarted.
    :type post_svc_restart_f: Callable[[str], None]
    :param pre_restarts_wait_f: A function called before any restarts.
    :type pre_restarts_wait_f: Callable[None, None]
    :returns: decorator to use a restart_on_change with pausability
    :rtype: decorator


    """
    def wrap(f):
        # py27 compatible nonlocal variable.  When py3 only, replace with
        # nonlocal keyword
        __restart_map_cache = {'cache': None}

        @functools.wraps(f)
        def wrapped_f(*args, **kwargs):
            if is_unit_paused_set():
                return f(*args, **kwargs)
            if __restart_map_cache['cache'] is None:
                __restart_map_cache['cache'] = restart_map() \
                    if callable(restart_map) else restart_map
            # otherwise, normal restart_on_change functionality
            return restart_on_change_helper(
                (lambda: f(*args, **kwargs)),
                __restart_map_cache['cache'],
                stopstart,
                restart_functions,
                can_restart_now_f,
                post_svc_restart_f,
                pre_restarts_wait_f)
        return wrapped_f
    return wrap


def ordered(orderme):
    """Converts the provided dictionary into a collections.OrderedDict.

    The items in the returned OrderedDict will be inserted based on the
    natural sort order of the keys. Nested dictionaries will also be sorted
    in order to ensure fully predictable ordering.

    :param orderme: the dict to order
    :return: collections.OrderedDict
    :raises: ValueError: if `orderme` isn't a dict instance.
    """
    if not isinstance(orderme, dict):
        raise ValueError('argument must be a dict type')

    result = OrderedDict()
    for k, v in sorted(six.iteritems(orderme), key=lambda x: x[0]):
        if isinstance(v, dict):
            result[k] = ordered(v)
        else:
            result[k] = v

    return result


def config_flags_parser(config_flags):
    """Parses config flags string into dict.

    This parsing method supports a few different formats for the config
    flag values to be parsed:

      1. A string in the simple format of key=value pairs, with the possibility
         of specifying multiple key value pairs within the same string. For
         example, a string in the format of 'key1=value1, key2=value2' will
         return a dict of:

             {'key1': 'value1', 'key2': 'value2'}.

      2. A string in the above format, but supporting a comma-delimited list
         of values for the same key. For example, a string in the format of
         'key1=value1, key2=value3,value4,value5' will return a dict of:

             {'key1': 'value1', 'key2': 'value2,value3,value4'}

      3. A string containing a colon character (:) prior to an equal
         character (=) will be treated as yaml and parsed as such. This can be
         used to specify more complex key value pairs. For example,
         a string in the format of 'key1: subkey1=value1, subkey2=value2' will
         return a dict of:

             {'key1', 'subkey1=value1, subkey2=value2'}

    The provided config_flags string may be a list of comma-separated values
    which themselves may be comma-separated list of values.
    """
    # If we find a colon before an equals sign then treat it as yaml.
    # Note: limit it to finding the colon first since this indicates assignment
    # for inline yaml.
    colon = config_flags.find(':')
    equals = config_flags.find('=')
    if colon > 0:
        if colon < equals or equals < 0:
            return ordered(yaml.safe_load(config_flags))

    if config_flags.find('==') >= 0:
        juju_log("config_flags is not in expected format (key=value)",
                 level=ERROR)
        raise OSContextError

    # strip the following from each value.
    post_strippers = ' ,'
    # we strip any leading/trailing '=' or ' ' from the string then
    # split on '='.
    split = config_flags.strip(' =').split('=')
    limit = len(split)
    flags = OrderedDict()
    for i in range(0, limit - 1):
        current = split[i]
        next = split[i + 1]
        vindex = next.rfind(',')
        if (i == limit - 2) or (vindex < 0):
            value = next
        else:
            value = next[:vindex]

        if i == 0:
            key = current
        else:
            # if this not the first entry, expect an embedded key.
            index = current.rfind(',')
            if index < 0:
                juju_log("Invalid config value(s) at index %s" % (i),
                         level=ERROR)
                raise OSContextError
            key = current[index + 1:]

        # Add to collection.
        flags[key.strip(post_strippers)] = value.rstrip(post_strippers)

    return flags


def os_application_version_set(package):
    '''Set version of application for Juju 2.0 and later'''
    application_version = get_upstream_version(package)
    # NOTE(jamespage) if not able to figure out package version, fallback to
    #                 openstack codename version detection.
    if not application_version:
        application_version_set(os_release(package))
    else:
        application_version_set(application_version)


def os_application_status_set(check_function):
    """Run the supplied function and set the application status accordingly.

    :param check_function: Function to run to get app states and messages.
    :type check_function: function
    """
    state, message = check_function()
    status_set(state, message, application=True)


def enable_memcache(source=None, release=None, package=None):
    """Determine if memcache should be enabled on the local unit

    @param release: release of OpenStack currently deployed
    @param package: package to derive OpenStack version deployed
    @returns boolean Whether memcache should be enabled
    """
    _release = None
    if release:
        _release = release
    else:
        _release = os_release(package)
    if not _release:
        _release = get_os_codename_install_source(source)

    return CompareOpenStackReleases(_release) >= 'mitaka'


def token_cache_pkgs(source=None, release=None):
    """Determine additional packages needed for token caching

    @param source: source string for charm
    @param release: release of OpenStack currently deployed
    @returns List of package to enable token caching
    """
    packages = []
    if enable_memcache(source=source, release=release):
        packages.extend(['memcached', 'python-memcache'])
    return packages


def update_json_file(filename, items):
    """Updates the json `filename` with a given dict.
    :param filename: path to json file (e.g. /etc/glance/policy.json)
    :param items: dict of items to update
    """
    if not items:
        return

    with open(filename) as fd:
        policy = json.load(fd)

    # Compare before and after and if nothing has changed don't write the file
    # since that could cause unnecessary service restarts.
    before = json.dumps(policy, indent=4, sort_keys=True)
    policy.update(items)
    after = json.dumps(policy, indent=4, sort_keys=True)
    if before == after:
        return

    with open(filename, "w") as fd:
        fd.write(after)


@cached
def snap_install_requested():
    """ Determine if installing from snaps

    If openstack-origin is of the form snap:track/channel[/branch]
    and channel is in SNAPS_CHANNELS return True.
    """
    origin = config('openstack-origin') or ""
    if not origin.startswith('snap:'):
        return False

    _src = origin[5:]
    if '/' in _src:
        channel = _src.split('/')[1]
    else:
        # Handle snap:track with no channel
        channel = 'stable'
    return valid_snap_channel(channel)


def get_snaps_install_info_from_origin(snaps, src, mode='classic'):
    """Generate a dictionary of snap install information from origin

    @param snaps: List of snaps
    @param src: String of openstack-origin or source of the form
        snap:track/channel
    @param mode: String classic, devmode or jailmode
    @returns: Dictionary of snaps with channels and modes
    """

    if not src.startswith('snap:'):
        juju_log("Snap source is not a snap origin", 'WARN')
        return {}

    _src = src[5:]
    channel = '--channel={}'.format(_src)

    return {snap: {'channel': channel, 'mode': mode}
            for snap in snaps}


def install_os_snaps(snaps, refresh=False):
    """Install OpenStack snaps from channel and with mode

    @param snaps: Dictionary of snaps with channels and modes of the form:
        {'snap_name': {'channel': 'snap_channel',
                       'mode': 'snap_mode'}}
        Where channel is a snapstore channel and mode is --classic, --devmode
        or --jailmode.
    @param post_snap_install: Callback function to run after snaps have been
    installed
    """

    def _ensure_flag(flag):
        if flag.startswith('--'):
            return flag
        return '--{}'.format(flag)

    if refresh:
        for snap in snaps.keys():
            snap_refresh(snap,
                         _ensure_flag(snaps[snap]['channel']),
                         _ensure_flag(snaps[snap]['mode']))
    else:
        for snap in snaps.keys():
            snap_install(snap,
                         _ensure_flag(snaps[snap]['channel']),
                         _ensure_flag(snaps[snap]['mode']))


def set_unit_upgrading():
    """Set the unit to a upgrading state in the local kv() store.
    """
    with unitdata.HookData()() as t:
        kv = t[0]
        kv.set('unit-upgrading', True)


def clear_unit_upgrading():
    """Clear the unit from a upgrading state in the local kv() store
    """
    with unitdata.HookData()() as t:
        kv = t[0]
        kv.set('unit-upgrading', False)


def is_unit_upgrading_set():
    """Return the state of the kv().get('unit-upgrading').

    To help with units that don't have HookData() (testing)
    if it excepts, return False
    """
    try:
        with unitdata.HookData()() as t:
            kv = t[0]
            # transform something truth-y into a Boolean.
            return not(not(kv.get('unit-upgrading')))
    except Exception:
        return False


def series_upgrade_prepare(pause_unit_helper=None, configs=None):
    """ Run common series upgrade prepare tasks.

    :param pause_unit_helper: function: Function to pause unit
    :param configs: OSConfigRenderer object: Configurations
    :returns None:
    """
    set_unit_upgrading()
    if pause_unit_helper and configs:
        if not is_unit_paused_set():
            pause_unit_helper(configs)


def series_upgrade_complete(resume_unit_helper=None, configs=None):
    """ Run common series upgrade complete tasks.

    :param resume_unit_helper: function: Function to resume unit
    :param configs: OSConfigRenderer object: Configurations
    :returns None:
    """
    clear_unit_paused()
    clear_unit_upgrading()
    if configs:
        configs.write_all()
        if resume_unit_helper:
            resume_unit_helper(configs)


def is_db_initialised():
    """Check leader storage to see if database has been initialised.

    :returns: Whether DB has been initialised
    :rtype: bool
    """
    db_initialised = None
    if leader_get('db-initialised') is None:
        juju_log(
            'db-initialised key missing, assuming db is not initialised',
            'DEBUG')
        db_initialised = False
    else:
        db_initialised = bool_from_string(leader_get('db-initialised'))
    juju_log('Database initialised: {}'.format(db_initialised), 'DEBUG')
    return db_initialised


def set_db_initialised():
    """Add flag to leader storage to indicate database has been initialised.
    """
    juju_log('Setting db-initialised to True', 'DEBUG')
    leader_set({'db-initialised': True})


def is_db_maintenance_mode(relid=None):
    """Check relation data from notifications of db in maintenance mode.

    :returns: Whether db has notified it is in maintenance mode.
    :rtype: bool
    """
    juju_log('Checking for maintenance notifications', 'DEBUG')
    if relid:
        r_ids = [relid]
    else:
        r_ids = relation_ids('shared-db')
    rids_units = [(r, u) for r in r_ids for u in related_units(r)]
    notifications = []
    for r_id, unit in rids_units:
        settings = relation_get(unit=unit, rid=r_id)
        for key, value in settings.items():
            if value and key in DB_MAINTENANCE_KEYS:
                juju_log(
                    'Unit: {}, Key: {}, Value: {}'.format(unit, key, value),
                    'DEBUG')
                try:
                    notifications.append(bool_from_string(value))
                except ValueError:
                    juju_log(
                        'Could not discern bool from {}'.format(value),
                        'WARN')
                    pass
    return True in notifications


@cached
def container_scoped_relations():
    """Get all the container scoped relations

    :returns: List of relation names
    :rtype: List
    """
    md = metadata()
    relations = []
    for relation_type in ('provides', 'requires', 'peers'):
        for relation in md.get(relation_type, []):
            if md[relation_type][relation].get('scope') == 'container':
                relations.append(relation)
    return relations


def container_scoped_relation_get(attribute=None):
    """Get relation data from all container scoped relations.

    :param attribute: Name of attribute to get
    :type attribute: Optional[str]
    :returns: Iterator with relation data
    :rtype: Iterator[Optional[any]]
    """
    for endpoint_name in container_scoped_relations():
        for rid in relation_ids(endpoint_name):
            for unit in related_units(rid):
                yield relation_get(
                    attribute=attribute,
                    unit=unit,
                    rid=rid)


def is_db_ready(use_current_context=False, rel_name=None):
    """Check remote database is ready to be used.

    Database relations are expected to provide a list of 'allowed' units to
    confirm that the database is ready for use by those units.

    If db relation has provided this information and local unit is a member,
    returns True otherwise False.

    :param use_current_context: Whether to limit checks to current hook
                                context.
    :type use_current_context: bool
    :param rel_name: Name of relation to check
    :type rel_name: string
    :returns: Whether remote db is ready.
    :rtype: bool
    :raises: Exception
    """
    key = 'allowed_units'

    rel_name = rel_name or 'shared-db'
    this_unit = local_unit()

    if use_current_context:
        if relation_id() in relation_ids(rel_name):
            rids_units = [(None, None)]
        else:
            raise Exception("use_current_context=True but not in {} "
                            "rel hook contexts (currently in {})."
                            .format(rel_name, relation_id()))
    else:
        rids_units = [(r_id, u)
                      for r_id in relation_ids(rel_name)
                      for u in related_units(r_id)]

    for rid, unit in rids_units:
        allowed_units = relation_get(rid=rid, unit=unit, attribute=key)
        if allowed_units and this_unit in allowed_units.split():
            juju_log("This unit ({}) is in allowed unit list from {}".format(
                this_unit,
                unit), 'DEBUG')
            return True

    juju_log("This unit was not found in any allowed unit list")
    return False


def is_expected_scale(peer_relation_name='cluster'):
    """Query juju goal-state to determine whether our peer- and dependency-
    relations are at the expected scale.

    Useful for deferring per unit per relation housekeeping work until we are
    ready to complete it successfully and without unnecessary repetiton.

    Always returns True if version of juju used does not support goal-state.

    :param peer_relation_name: Name of peer relation
    :type rel_name: string
    :returns: True or False
    :rtype: bool
    """
    def _get_relation_id(rel_type):
        return next((rid for rid in relation_ids(reltype=rel_type)), None)

    Relation = namedtuple('Relation', 'rel_type rel_id')
    peer_rid = _get_relation_id(peer_relation_name)
    # Units with no peers should still have a peer relation.
    if not peer_rid:
        juju_log('Not at expected scale, no peer relation found', 'DEBUG')
        return False
    expected_relations = [
        Relation(rel_type='shared-db', rel_id=_get_relation_id('shared-db'))]
    if expect_ha():
        expected_relations.append(
            Relation(
                rel_type='ha',
                rel_id=_get_relation_id('ha')))
    juju_log(
        'Checking scale of {} relations'.format(
            ','.join([r.rel_type for r in expected_relations])),
        'DEBUG')
    try:
        if (len(related_units(relid=peer_rid)) <
                len(list(expected_peer_units()))):
            return False
        for rel in expected_relations:
            if not rel.rel_id:
                juju_log(
                    'Expected to find {} relation, but it is missing'.format(
                        rel.rel_type),
                    'DEBUG')
                return False
            # Goal state returns every unit even for container scoped
            # relations but the charm only ever has a relation with
            # the local unit.
            if rel.rel_type in container_scoped_relations():
                expected_count = 1
            else:
                expected_count = len(
                    list(expected_related_units(reltype=rel.rel_type)))
            if len(related_units(relid=rel.rel_id)) < expected_count:
                juju_log(
                    ('Not at expected scale, not enough units on {} '
                     'relation'.format(rel.rel_type)),
                    'DEBUG')
                return False
    except NotImplementedError:
        return True
    juju_log('All checks have passed, unit is at expected scale', 'DEBUG')
    return True


def get_peer_key(unit_name):
    """Get the peer key for this unit.

    The peer key is the key a unit uses to publish its status down the peer
    relation

    :param unit_name: Name of unit
    :type unit_name: string
    :returns: Peer key for given unit
    :rtype: string
    """
    return 'unit-state-{}'.format(unit_name.replace('/', '-'))


UNIT_READY = 'READY'
UNIT_NOTREADY = 'NOTREADY'
UNIT_UNKNOWN = 'UNKNOWN'
UNIT_STATES = [UNIT_READY, UNIT_NOTREADY, UNIT_UNKNOWN]


def inform_peers_unit_state(state, relation_name='cluster'):
    """Inform peers of the state of this unit.

    :param state: State of unit to publish
    :type state: string
    :param relation_name: Name of relation to publish state on
    :type relation_name: string
    """
    if state not in UNIT_STATES:
        raise ValueError(
            "Setting invalid state {} for unit".format(state))
    this_unit = local_unit()
    for r_id in relation_ids(relation_name):
        juju_log('Telling peer behind relation {} that {} is {}'.format(
            r_id, this_unit, state), 'DEBUG')
        relation_set(relation_id=r_id,
                     relation_settings={
                         get_peer_key(this_unit): state})


def get_peers_unit_state(relation_name='cluster'):
    """Get the state of all peers.

    :param relation_name: Name of relation to check peers on.
    :type relation_name: string
    :returns: Unit states keyed on unit name.
    :rtype: dict
    :raises: ValueError
    """
    r_ids = relation_ids(relation_name)
    rids_units = [(r, u) for r in r_ids for u in related_units(r)]
    unit_states = {}
    for r_id, unit in rids_units:
        settings = relation_get(unit=unit, rid=r_id)
        unit_states[unit] = settings.get(get_peer_key(unit), UNIT_UNKNOWN)
        if unit_states[unit] not in UNIT_STATES:
            raise ValueError(
                "Unit in unknown state {}".format(unit_states[unit]))
    return unit_states


def are_peers_ready(relation_name='cluster'):
    """Check if all peers are ready.

    :param relation_name: Name of relation to check peers on.
    :type relation_name: string
    :returns: Whether all units are ready.
    :rtype: bool
    """
    unit_states = get_peers_unit_state(relation_name).values()
    juju_log('{} peers are in the following states: {}'.format(
        relation_name, unit_states), 'DEBUG')
    return all(state == UNIT_READY for state in unit_states)


def inform_peers_if_ready(check_unit_ready_func, relation_name='cluster'):
    """Inform peers if this unit is ready.

    The check function should return a tuple (state, message). A state
    of 'READY' indicates the unit is READY.

    :param check_unit_ready_func: Function to run to check readiness
    :type check_unit_ready_func: function
    :param relation_name: Name of relation to check peers on.
    :type relation_name: string
    """
    unit_ready, msg = check_unit_ready_func()
    if unit_ready:
        state = UNIT_READY
    else:
        state = UNIT_NOTREADY
    juju_log('Telling peers this unit is: {}'.format(state), 'DEBUG')
    inform_peers_unit_state(state, relation_name)


def check_api_unit_ready(check_db_ready=True):
    """Check if this unit is ready.

    :param check_db_ready: Include checks of database readiness.
    :type check_db_ready: bool
    :returns: Whether unit state is ready and status message
    :rtype: (bool, str)
    """
    unit_state, msg = get_api_unit_status(check_db_ready=check_db_ready)
    return unit_state == WORKLOAD_STATES.ACTIVE, msg


def get_api_unit_status(check_db_ready=True):
    """Return a workload status and message for this unit.

    :param check_db_ready: Include checks of database readiness.
    :type check_db_ready: bool
    :returns: Workload state and message
    :rtype: (bool, str)
    """
    unit_state = WORKLOAD_STATES.ACTIVE
    msg = 'Unit is ready'
    if is_db_maintenance_mode():
        unit_state = WORKLOAD_STATES.MAINTENANCE
        msg = 'Database in maintenance mode.'
    elif is_unit_paused_set():
        unit_state = WORKLOAD_STATES.BLOCKED
        msg = 'Unit paused.'
    elif check_db_ready and not is_db_ready():
        unit_state = WORKLOAD_STATES.WAITING
        msg = 'Allowed_units list provided but this unit not present'
    elif not is_db_initialised():
        unit_state = WORKLOAD_STATES.WAITING
        msg = 'Database not initialised'
    elif not is_expected_scale():
        unit_state = WORKLOAD_STATES.WAITING
        msg = 'Charm and its dependencies not yet at expected scale'
    juju_log(msg, 'DEBUG')
    return unit_state, msg


def check_api_application_ready():
    """Check if this application is ready.

    :returns: Whether application state is ready and status message
    :rtype: (bool, str)
    """
    app_state, msg = get_api_application_status()
    return app_state == WORKLOAD_STATES.ACTIVE, msg


def get_api_application_status():
    """Return a workload status and message for this application.

    :returns: Workload state and message
    :rtype: (bool, str)
    """
    app_state, msg = get_api_unit_status()
    if app_state == WORKLOAD_STATES.ACTIVE:
        if are_peers_ready():
            msg = 'Application Ready'
        else:
            app_state = WORKLOAD_STATES.WAITING
            msg = 'Some units are not ready'
    juju_log(msg, 'DEBUG')
    return app_state, msg


def sequence_status_check_functions(*functions):
    """Sequence the functions passed so that they all get a chance to run as
    the charm status check functions.

    :param *functions: a list of functions that return (state, message)
    :type *functions: List[Callable[[OSConfigRender], (str, str)]]
    :returns: the Callable that takes configs and returns (state, message)
    :rtype: Callable[[OSConfigRender], (str, str)]
    """
    def _inner_sequenced_functions(configs):
        state, message = 'unknown', ''
        for f in functions:
            new_state, new_message = f(configs)
            state = workload_state_compare(state, new_state)
            if message:
                message = "{}, {}".format(message, new_message)
            else:
                message = new_message
        return state, message

    return _inner_sequenced_functions


SubordinatePackages = namedtuple('SubordinatePackages', ['install', 'purge'])


def get_subordinate_release_packages(os_release, package_type='deb'):
    """Iterate over subordinate relations and get package information.

    :param os_release: OpenStack release to look for
    :type os_release: str
    :param package_type: Package type (one of 'deb' or 'snap')
    :type package_type: str
    :returns: Packages to install and packages to purge or None
    :rtype: SubordinatePackages[set,set]
    """
    install = set()
    purge = set()

    for rdata in container_scoped_relation_get('releases-packages-map'):
        rp_map = json.loads(rdata or '{}')
        # The map provided by subordinate has OpenStack release name as key.
        # Find package information from subordinate matching requested release
        # or the most recent release prior to requested release by sorting the
        # keys in reverse order. This follows established patterns in our
        # charms for templates and reactive charm implementations, i.e. as long
        # as nothing has changed the definitions for the prior OpenStack
        # release is still valid.
        for release in sorted(rp_map.keys(), reverse=True):
            if (CompareOpenStackReleases(release) <= os_release and
                    package_type in rp_map[release]):
                for name, container in (
                        ('install', install),
                        ('purge', purge)):
                    for pkg in rp_map[release][package_type].get(name, []):
                        container.add(pkg)
                break
    return SubordinatePackages(install, purge)


def get_subordinate_services():
    """Iterate over subordinate relations and get service information.

    In a similar fashion as with get_subordinate_release_packages(),
    principle charms can retrieve a list of services advertised by their
    subordinate charms. This is useful to know about subordinate services when
    pausing, resuming or upgrading a principle unit.

    :returns: Name of all services advertised by all subordinates
    :rtype: Set[str]
    """
    services = set()
    for rdata in container_scoped_relation_get('services'):
        services |= set(json.loads(rdata or '[]'))
    return services


os_restart_on_change = partial(
    pausable_restart_on_change,
    can_restart_now_f=deferred_events.check_and_record_restart_request,
    post_svc_restart_f=deferred_events.process_svc_restart)


def restart_services_action_helper(all_services):
    """Helper to run the restart-services action.

    NOTE: all_services is all services that could be restarted but
          depending on the action arguments it may be a subset of
          these that are actually restarted.

    :param all_services: All services that could be restarted
    :type all_services: List[str]
    """
    deferred_only = action_get("deferred-only")
    services = action_get("services")
    if services:
        services = services.split()
    else:
        services = all_services
    if deferred_only:
        restart_services_action(deferred_only=True)
    else:
        restart_services_action(services=services)


def show_deferred_events_action_helper():
    """Helper to run the show-deferred-restarts action."""
    restarts = []
    for event in deferred_events.get_deferred_events():
        restarts.append('{} {} {}'.format(
            str(event.timestamp),
            event.service.ljust(40),
            event.reason))
    restarts.sort()
    output = {
        'restarts': restarts,
        'hooks': deferred_events.get_deferred_hooks()}
    action_set({'output': "{}".format(
        yaml.dump(output, default_flow_style=False))})
