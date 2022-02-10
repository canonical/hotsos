# Copyright 2019 Canonical Limited.
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
import configparser
import glob
import os.path
import subprocess

from charmhelpers.contrib.openstack.audits import (
    audit,
    AuditType,
    # filters
    is_audit_type,
    it_has_config,
)

from charmhelpers.core.hookenv import (
    cached,
)

"""
The Security Guide suggests a specific list of files inside the
config directory for the service having 640 specifically, but
by ensuring the containing directory is 750, only the owner can
write, and only the group can read files within the directory.

By  restricting access to the containing directory, we can more
effectively ensure that there is no accidental leakage if a new
file is added to the service without being added to the security
guide, and to this check.
"""
FILE_ASSERTIONS = {
    'barbican': {
        '/etc/barbican': {'group': 'barbican', 'mode': '750'},
    },
    'ceph-mon': {
        '/var/lib/charm/ceph-mon/ceph.conf':
            {'owner': 'root', 'group': 'root', 'mode': '644'},
        '/etc/ceph/ceph.client.admin.keyring':
            {'owner': 'ceph', 'group': 'ceph'},
        '/etc/ceph/rbdmap': {'mode': '644'},
        '/var/lib/ceph': {'owner': 'ceph', 'group': 'ceph', 'mode': '750'},
        '/var/lib/ceph/bootstrap-*/ceph.keyring':
            {'owner': 'ceph', 'group': 'ceph', 'mode': '600'}
    },
    'ceph-osd': {
        '/var/lib/charm/ceph-osd/ceph.conf':
            {'owner': 'ceph', 'group': 'ceph', 'mode': '644'},
        '/var/lib/ceph': {'owner': 'ceph', 'group': 'ceph', 'mode': '750'},
        '/var/lib/ceph/*': {'owner': 'ceph', 'group': 'ceph', 'mode': '755'},
        '/var/lib/ceph/bootstrap-*/ceph.keyring':
            {'owner': 'ceph', 'group': 'ceph', 'mode': '600'},
        '/var/lib/ceph/radosgw':
            {'owner': 'ceph', 'group': 'ceph', 'mode': '755'},
    },
    'cinder': {
        '/etc/cinder': {'group': 'cinder', 'mode': '750'},
    },
    'glance': {
        '/etc/glance': {'group': 'glance', 'mode': '750'},
    },
    'keystone': {
        '/etc/keystone':
            {'owner': 'keystone', 'group': 'keystone', 'mode': '750'},
    },
    'manilla': {
        '/etc/manila': {'group': 'manilla', 'mode': '750'},
    },
    'neutron-gateway': {
        '/etc/neutron': {'group': 'neutron', 'mode': '750'},
    },
    'neutron-api': {
        '/etc/neutron/': {'group': 'neutron', 'mode': '750'},
    },
    'nova-cloud-controller': {
        '/etc/nova': {'group': 'nova', 'mode': '750'},
    },
    'nova-compute': {
        '/etc/nova/': {'group': 'nova', 'mode': '750'},
    },
    'openstack-dashboard': {
        # From security guide
        '/etc/openstack-dashboard/local_settings.py':
            {'group': 'horizon', 'mode': '640'},
    },
}

Ownership = collections.namedtuple('Ownership', 'owner group mode')


@cached
def _stat(file):
    """
    Get the Ownership information from a file.

    :param file: The path to a file to stat
    :type file: str
    :returns: owner, group, and mode of the specified file
    :rtype: Ownership
    :raises subprocess.CalledProcessError: If the underlying stat fails
    """
    out = subprocess.check_output(
        ['stat', '-c', '%U %G %a', file]).decode('utf-8')
    return Ownership(*out.strip().split(' '))


@cached
def _config_ini(path):
    """
    Parse an ini file

    :param path: The path to a file to parse
    :type file: str
    :returns: Configuration contained in path
    :rtype: Dict
    """
    # When strict is enabled, duplicate options are not allowed in the
    # parsed INI; however, Oslo allows duplicate values. This change
    # causes us to ignore the duplicate values which is acceptable as
    # long as we don't validate any multi-value options
    conf = configparser.ConfigParser(strict=False)
    conf.read(path)
    return dict(conf)


def _validate_file_ownership(owner, group, file_name, optional=False):
    """
    Validate that a specified file is owned by `owner:group`.

    :param owner: Name of the owner
    :type owner: str
    :param group: Name of the group
    :type group: str
    :param file_name: Path to the file to verify
    :type file_name: str
    :param optional: Is this file optional,
                     ie: Should this test fail when it's missing
    :type optional: bool
    """
    try:
        ownership = _stat(file_name)
    except subprocess.CalledProcessError as e:
        print("Error reading file: {}".format(e))
        if not optional:
            assert False, "Specified file does not exist: {}".format(file_name)
    assert owner == ownership.owner, \
        "{} has an incorrect owner: {} should be {}".format(
            file_name, ownership.owner, owner)
    assert group == ownership.group, \
        "{} has an incorrect group: {} should be {}".format(
            file_name, ownership.group, group)
    print("Validate ownership of {}: PASS".format(file_name))


def _validate_file_mode(mode, file_name, optional=False):
    """
    Validate that a specified file has the specified permissions.

    :param mode: file mode that is desires
    :type owner: str
    :param file_name: Path to the file to verify
    :type file_name: str
    :param optional: Is this file optional,
                     ie: Should this test fail when it's missing
    :type optional: bool
    """
    try:
        ownership = _stat(file_name)
    except subprocess.CalledProcessError as e:
        print("Error reading file: {}".format(e))
        if not optional:
            assert False, "Specified file does not exist: {}".format(file_name)
    assert mode == ownership.mode, \
        "{} has an incorrect mode: {} should be {}".format(
            file_name, ownership.mode, mode)
    print("Validate mode of {}: PASS".format(file_name))


@cached
def _config_section(config, section):
    """Read the configuration file and return a section."""
    path = os.path.join(config.get('config_path'), config.get('config_file'))
    conf = _config_ini(path)
    return conf.get(section)


@audit(is_audit_type(AuditType.OpenStackSecurityGuide),
       it_has_config('files'))
def validate_file_ownership(config):
    """Verify that configuration files are owned by the correct user/group."""
    files = config.get('files', {})
    for file_name, options in files.items():
        for key in options.keys():
            if key not in ["owner", "group", "mode"]:
                raise RuntimeError(
                    "Invalid ownership configuration: {}".format(key))
        owner = options.get('owner', config.get('owner', 'root'))
        group = options.get('group', config.get('group', 'root'))
        optional = options.get('optional', config.get('optional', False))
        if '*' in file_name:
            for file in glob.glob(file_name):
                if file not in files.keys():
                    if os.path.isfile(file):
                        _validate_file_ownership(owner, group, file, optional)
        else:
            if os.path.isfile(file_name):
                _validate_file_ownership(owner, group, file_name, optional)


@audit(is_audit_type(AuditType.OpenStackSecurityGuide),
       it_has_config('files'))
def validate_file_permissions(config):
    """Verify that permissions on configuration files are secure enough."""
    files = config.get('files', {})
    for file_name, options in files.items():
        for key in options.keys():
            if key not in ["owner", "group", "mode"]:
                raise RuntimeError(
                    "Invalid ownership configuration: {}".format(key))
        mode = options.get('mode', config.get('permissions', '600'))
        optional = options.get('optional', config.get('optional', False))
        if '*' in file_name:
            for file in glob.glob(file_name):
                if file not in files.keys():
                    if os.path.isfile(file):
                        _validate_file_mode(mode, file, optional)
        else:
            if os.path.isfile(file_name):
                _validate_file_mode(mode, file_name, optional)


@audit(is_audit_type(AuditType.OpenStackSecurityGuide))
def validate_uses_keystone(audit_options):
    """Validate that the service uses Keystone for authentication."""
    section = _config_section(audit_options, 'api') or _config_section(audit_options, 'DEFAULT')
    assert section is not None, "Missing section 'api / DEFAULT'"
    assert section.get('auth_strategy') == "keystone", \
        "Application is not using Keystone"


@audit(is_audit_type(AuditType.OpenStackSecurityGuide))
def validate_uses_tls_for_keystone(audit_options):
    """Verify that TLS is used to communicate with Keystone."""
    section = _config_section(audit_options, 'keystone_authtoken')
    assert section is not None, "Missing section 'keystone_authtoken'"
    assert not section.get('insecure') and \
        "https://" in section.get("auth_uri"), \
        "TLS is not used for Keystone"


@audit(is_audit_type(AuditType.OpenStackSecurityGuide))
def validate_uses_tls_for_glance(audit_options):
    """Verify that TLS is used to communicate with Glance."""
    section = _config_section(audit_options, 'glance')
    assert section is not None, "Missing section 'glance'"
    assert not section.get('insecure') and \
        "https://" in section.get("api_servers"), \
        "TLS is not used for Glance"
