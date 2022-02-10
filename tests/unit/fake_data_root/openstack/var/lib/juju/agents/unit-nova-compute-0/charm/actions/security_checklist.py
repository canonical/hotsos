#!/usr/bin/env python3
#
# Copyright 2019 Canonical Ltd
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
import configparser
import os
import sys


_path = os.path.dirname(os.path.realpath(__file__))
_hooks = os.path.abspath(os.path.join(_path, '../hooks'))


def _add_path(path):
    if path not in sys.path:
        sys.path.insert(1, path)


_add_path(_hooks)


import charmhelpers.contrib.openstack.audits as audits
from charmhelpers.contrib.openstack.audits import (
    openstack_security_guide,
)


# Via the openstack_security_guide above, we are running the following
# security assertions automatically:
#
# - Check-Compute-01 - validate-file-ownership
# - Check-Compute-02 - validate-file-permissions
# - Check-Compute-03 - validate-uses-keystone
# - Check-Compute-04 - validate-uses-tls-for-keystone
# - Check-Compute-05 - validates-uses-tls-for-glance


@audits.audit(audits.is_audit_type(audits.AuditType.OpenStackSecurityGuide),)
def is_volume_encryption_enabled(audit_options):
    """Validate volume encryption is enabled in Cinder.

    Security Guide Check Name: Check-Block-09

    :param audit_options: Dictionary of options for audit configuration
    :type audit_options: Dict
    :raises: AssertionError if the assertion fails.
    """
    key_manager = audit_options['nova-conf']['key_manager']
    assert key_manager.get('backend') is not None, \
        "key_manager.backend should be set"


def _config_file(path):
    """Read and parse config file at `path` as an ini file.

    :param path: Path of the file
    :type path: List[str]
    :returns: Parsed contents of the file at path
    :rtype Dict:
    """
    conf = configparser.ConfigParser()
    conf.read(os.path.join(*path))
    return dict(conf)


def main():
    config = {
        'config_path': '/etc/nova',
        'config_file': 'nova.conf',
        'audit_type': audits.AuditType.OpenStackSecurityGuide,
        'files': openstack_security_guide.FILE_ASSERTIONS['nova-compute'],
    }
    config['nova-conf'] = _config_file(
        [config['config_path'], config['config_file']])
    return audits.action_parse_results(audits.run(config))


if __name__ == "__main__":
    sys.exit(main())
