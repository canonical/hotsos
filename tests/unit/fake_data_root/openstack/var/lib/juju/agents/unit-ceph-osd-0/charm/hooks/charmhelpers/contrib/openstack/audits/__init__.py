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

"""OpenStack Security Audit code"""

import collections
from enum import Enum
import traceback

from charmhelpers.core.host import cmp_pkgrevno
import charmhelpers.contrib.openstack.utils as openstack_utils
import charmhelpers.core.hookenv as hookenv


class AuditType(Enum):
    OpenStackSecurityGuide = 1


_audits = {}

Audit = collections.namedtuple('Audit', 'func filters')


def audit(*args):
    """Decorator to register an audit.

    These are used to generate audits that can be run on a
    deployed system that matches the given configuration

    :param args: List of functions to filter tests against
    :type args: List[Callable[Dict]]
    """
    def wrapper(f):
        test_name = f.__name__
        if _audits.get(test_name):
            raise RuntimeError(
                "Test name '{}' used more than once"
                .format(test_name))
        non_callables = [fn for fn in args if not callable(fn)]
        if non_callables:
            raise RuntimeError(
                "Configuration includes non-callable filters: {}"
                .format(non_callables))
        _audits[test_name] = Audit(func=f, filters=args)
        return f
    return wrapper


def is_audit_type(*args):
    """This audit is included in the specified kinds of audits.

    :param *args: List of AuditTypes to include this audit in
    :type args: List[AuditType]
    :rtype: Callable[Dict]
    """
    def _is_audit_type(audit_options):
        if audit_options.get('audit_type') in args:
            return True
        else:
            return False
    return _is_audit_type


def since_package(pkg, pkg_version):
    """This audit should be run after the specified package version (incl).

    :param pkg: Package name to compare
    :type pkg: str
    :param release: The package version
    :type release: str
    :rtype: Callable[Dict]
    """
    def _since_package(audit_options=None):
        return cmp_pkgrevno(pkg, pkg_version) >= 0

    return _since_package


def before_package(pkg, pkg_version):
    """This audit should be run before the specified package version (excl).

    :param pkg: Package name to compare
    :type pkg: str
    :param release: The package version
    :type release: str
    :rtype: Callable[Dict]
    """
    def _before_package(audit_options=None):
        return not since_package(pkg, pkg_version)()

    return _before_package


def since_openstack_release(pkg, release):
    """This audit should run after the specified OpenStack version (incl).

    :param pkg: Package name to compare
    :type pkg: str
    :param release: The OpenStack release codename
    :type release: str
    :rtype: Callable[Dict]
    """
    def _since_openstack_release(audit_options=None):
        _release = openstack_utils.get_os_codename_package(pkg)
        return openstack_utils.CompareOpenStackReleases(_release) >= release

    return _since_openstack_release


def before_openstack_release(pkg, release):
    """This audit should run before the specified OpenStack version (excl).

    :param pkg: Package name to compare
    :type pkg: str
    :param release: The OpenStack release codename
    :type release: str
    :rtype: Callable[Dict]
    """
    def _before_openstack_release(audit_options=None):
        return not since_openstack_release(pkg, release)()

    return _before_openstack_release


def it_has_config(config_key):
    """This audit should be run based on specified config keys.

    :param config_key: Config key to look for
    :type config_key: str
    :rtype: Callable[Dict]
    """
    def _it_has_config(audit_options):
        return audit_options.get(config_key) is not None

    return _it_has_config


def run(audit_options):
    """Run the configured audits with the specified audit_options.

    :param audit_options: Configuration for the audit
    :type audit_options: Config

    :rtype: Dict[str, str]
    """
    errors = {}
    results = {}
    for name, audit in sorted(_audits.items()):
        result_name = name.replace('_', '-')
        if result_name in audit_options.get('excludes', []):
            print(
                "Skipping {} because it is"
                "excluded in audit config"
                .format(result_name))
            continue
        if all(p(audit_options) for p in audit.filters):
            try:
                audit.func(audit_options)
                print("{}: PASS".format(name))
                results[result_name] = {
                    'success': True,
                }
            except AssertionError as e:
                print("{}: FAIL ({})".format(name, e))
                results[result_name] = {
                    'success': False,
                    'message': e,
                }
            except Exception as e:
                print("{}: ERROR ({})".format(name, e))
                errors[name] = e
                results[result_name] = {
                    'success': False,
                    'message': e,
                }
    for name, error in errors.items():
        print("=" * 20)
        print("Error in {}: ".format(name))
        traceback.print_tb(error.__traceback__)
        print()
    return results


def action_parse_results(result):
    """Parse the result of `run` in the context of an action.

    :param result: The result of running the security-checklist
        action on a unit
    :type result: Dict[str, Dict[str, str]]
    :rtype: int
    """
    passed = True
    for test, result in result.items():
        if result['success']:
            hookenv.action_set({test: 'PASS'})
        else:
            hookenv.action_set({test: 'FAIL - {}'.format(result['message'])})
            passed = False
    if not passed:
        hookenv.action_fail("One or more tests failed")
    return 0 if passed else 1
