# Copyright 2019-2021 Canonical Ltd
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

"""Provide a subset of the ``python-apt`` module API.

Data collection is done through subprocess calls to ``apt-cache`` and
``dpkg-query`` commands.

The main purpose for this module is to avoid dependency on the
``python-apt`` python module.

The indicated python module is a wrapper around the ``apt`` C++ library
which is tightly connected to the version of the distribution it was
shipped on.  It is not developed in a backward/forward compatible manner.

This in turn makes it incredibly hard to distribute as a wheel for a piece
of python software that supports a span of distro releases [0][1].

Upstream feedback like [2] does not give confidence in this ever changing,
so with this we get rid of the dependency.

0: https://github.com/juju-solutions/layer-basic/pull/135
1: https://bugs.launchpad.net/charm-octavia/+bug/1824112
2: https://bugs.debian.org/cgi-bin/bugreport.cgi?bug=845330#10
"""

import locale
import os
import subprocess
import sys


class _container(dict):
    """Simple container for attributes."""
    __getattr__ = dict.__getitem__
    __setattr__ = dict.__setitem__


class Package(_container):
    """Simple container for package attributes."""


class Version(_container):
    """Simple container for version attributes."""


class Cache(object):
    """Simulation of ``apt_pkg`` Cache object."""
    def __init__(self, progress=None):
        pass

    def __contains__(self, package):
        try:
            pkg = self.__getitem__(package)
            return pkg is not None
        except KeyError:
            return False

    def __getitem__(self, package):
        """Get information about a package from apt and dpkg databases.

        :param package: Name of package
        :type package: str
        :returns: Package object
        :rtype: object
        :raises: KeyError, subprocess.CalledProcessError
        """
        apt_result = self._apt_cache_show([package])[package]
        apt_result['name'] = apt_result.pop('package')
        pkg = Package(apt_result)
        dpkg_result = self._dpkg_list([package]).get(package, {})
        current_ver = None
        installed_version = dpkg_result.get('version')
        if installed_version:
            current_ver = Version({'ver_str': installed_version})
        pkg.current_ver = current_ver
        pkg.architecture = dpkg_result.get('architecture')
        return pkg

    def _dpkg_list(self, packages):
        """Get data from system dpkg database for package.

        :param packages: Packages to get data from
        :type packages: List[str]
        :returns: Structured data about installed packages, keys like
                  ``dpkg-query --list``
        :rtype: dict
        :raises: subprocess.CalledProcessError
        """
        pkgs = {}
        cmd = ['dpkg-query', '--list']
        cmd.extend(packages)
        if locale.getlocale() == (None, None):
            # subprocess calls out to locale.getpreferredencoding(False) to
            # determine encoding.  Workaround for Trusty where the
            # environment appears to not be set up correctly.
            locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
        try:
            output = subprocess.check_output(cmd,
                                             stderr=subprocess.STDOUT,
                                             universal_newlines=True)
        except subprocess.CalledProcessError as cp:
            # ``dpkg-query`` may return error and at the same time have
            # produced useful output, for example when asked for multiple
            # packages where some are not installed
            if cp.returncode != 1:
                raise
            output = cp.output
        headings = []
        for line in output.splitlines():
            if line.startswith('||/'):
                headings = line.split()
                headings.pop(0)
                continue
            elif (line.startswith('|') or line.startswith('+') or
                  line.startswith('dpkg-query:')):
                continue
            else:
                data = line.split(None, 4)
                status = data.pop(0)
                if status not in ('ii', 'hi'):
                    continue
                pkg = {}
                pkg.update({k.lower(): v for k, v in zip(headings, data)})
                if 'name' in pkg:
                    pkgs.update({pkg['name']: pkg})
        return pkgs

    def _apt_cache_show(self, packages):
        """Get data from system apt cache for package.

        :param packages: Packages to get data from
        :type packages: List[str]
        :returns: Structured data about package, keys like
                  ``apt-cache show``
        :rtype: dict
        :raises: subprocess.CalledProcessError
        """
        pkgs = {}
        cmd = ['apt-cache', 'show', '--no-all-versions']
        cmd.extend(packages)
        if locale.getlocale() == (None, None):
            # subprocess calls out to locale.getpreferredencoding(False) to
            # determine encoding.  Workaround for Trusty where the
            # environment appears to not be set up correctly.
            locale.setlocale(locale.LC_ALL, 'en_US.UTF-8')
        try:
            output = subprocess.check_output(cmd,
                                             stderr=subprocess.STDOUT,
                                             universal_newlines=True)
            previous = None
            pkg = {}
            for line in output.splitlines():
                if not line:
                    if 'package' in pkg:
                        pkgs.update({pkg['package']: pkg})
                        pkg = {}
                    continue
                if line.startswith(' '):
                    if previous and previous in pkg:
                        pkg[previous] += os.linesep + line.lstrip()
                    continue
                if ':' in line:
                    kv = line.split(':', 1)
                    key = kv[0].lower()
                    if key == 'n':
                        continue
                    previous = key
                    pkg.update({key: kv[1].lstrip()})
        except subprocess.CalledProcessError as cp:
            # ``apt-cache`` returns 100 if none of the packages asked for
            # exist in the apt cache.
            if cp.returncode != 100:
                raise
        return pkgs


class Config(_container):
    def __init__(self):
        super(Config, self).__init__(self._populate())

    def _populate(self):
        cfgs = {}
        cmd = ['apt-config', 'dump']
        output = subprocess.check_output(cmd,
                                         stderr=subprocess.STDOUT,
                                         universal_newlines=True)
        for line in output.splitlines():
            if not line.startswith("CommandLine"):
                k, v = line.split(" ", 1)
                cfgs[k] = v.strip(";").strip("\"")

        return cfgs


# Backwards compatibility with old apt_pkg module
sys.modules[__name__].config = Config()


def init():
    """Compatibility shim that does nothing."""
    pass


def upstream_version(version):
    """Extracts upstream version from a version string.

    Upstream reference: https://salsa.debian.org/apt-team/apt/blob/master/
                                apt-pkg/deb/debversion.cc#L259

    :param version: Version string
    :type version: str
    :returns: Upstream version
    :rtype: str
    """
    if version:
        version = version.split(':')[-1]
        version = version.split('-')[0]
    return version


def version_compare(a, b):
    """Compare the given versions.

    Call out to ``dpkg`` to make sure the code doing the comparison is
    compatible with what the ``apt`` library would do.  Mimic the return
    values.

    Upstream reference:
    https://apt-team.pages.debian.net/python-apt/library/apt_pkg.html
            ?highlight=version_compare#apt_pkg.version_compare

    :param a: version string
    :type a: str
    :param b: version string
    :type b: str
    :returns: >0 if ``a`` is greater than ``b``, 0 if a equals b,
              <0 if ``a`` is smaller than ``b``
    :rtype: int
    :raises: subprocess.CalledProcessError, RuntimeError
    """
    for op in ('gt', 1), ('eq', 0), ('lt', -1):
        try:
            subprocess.check_call(['dpkg', '--compare-versions',
                                   a, op[0], b],
                                  stderr=subprocess.STDOUT,
                                  universal_newlines=True)
            return op[1]
        except subprocess.CalledProcessError as cp:
            if cp.returncode == 1:
                continue
            raise
    else:
        raise RuntimeError('Unable to compare "{}" and "{}", according to '
                           'our logic they are neither greater, equal nor '
                           'less than each other.'.format(a, b))


class PkgVersion():
    """Allow package versions to be compared.

    For example::

        >>> import charmhelpers.fetch as fetch
        >>> (fetch.apt_pkg.PkgVersion('2:20.4.0') <
        ...  fetch.apt_pkg.PkgVersion('2:20.5.0'))
        True
        >>> pkgs = [fetch.apt_pkg.PkgVersion('2:20.4.0'),
        ...         fetch.apt_pkg.PkgVersion('2:21.4.0'),
        ...         fetch.apt_pkg.PkgVersion('2:17.4.0')]
        >>> pkgs.sort()
        >>> pkgs
        [2:17.4.0, 2:20.4.0, 2:21.4.0]
    """

    def __init__(self, version):
        self.version = version

    def __lt__(self, other):
        return version_compare(self.version, other.version) == -1

    def __le__(self, other):
        return self.__lt__(other) or self.__eq__(other)

    def __gt__(self, other):
        return version_compare(self.version, other.version) == 1

    def __ge__(self, other):
        return self.__gt__(other) or self.__eq__(other)

    def __eq__(self, other):
        return version_compare(self.version, other.version) == 0

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return self.version

    def __hash__(self):
        return hash(repr(self))
