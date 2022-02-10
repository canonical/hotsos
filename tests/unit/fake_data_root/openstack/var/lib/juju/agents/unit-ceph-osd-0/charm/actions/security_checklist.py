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

import sys

sys.path.append('hooks')

import charmhelpers.contrib.openstack.audits as audits
from charmhelpers.contrib.openstack.audits import (
    openstack_security_guide,
)


# Via the openstack_security_guide above, we are running the following
# security assertions automatically:
#
# - validate-file-ownership
# - validate-file-permissions


def main():
    config = {
        'audit_type': audits.AuditType.OpenStackSecurityGuide,
        'files': openstack_security_guide.FILE_ASSERTIONS['ceph-osd'],
        'excludes': [
            'validate-uses-keystone',
            'validate-uses-tls-for-glance',
            'validate-uses-tls-for-keystone',
        ],
    }
    return audits.action_parse_results(audits.run(config))


if __name__ == "__main__":
    sys.exit(main())
