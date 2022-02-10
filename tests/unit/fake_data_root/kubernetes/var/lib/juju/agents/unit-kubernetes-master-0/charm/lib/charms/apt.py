# Copyright 2015-2020 Canonical Ltd.
#
# This file is part of the Apt layer for Juju.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 3, as
# published by the Free Software Foundation.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranties of
# MERCHANTABILITY, SATISFACTORY QUALITY, or FITNESS FOR A PARTICULAR
# PURPOSE.  See the GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

'''
charms.reactive helpers for dealing with deb packages.

Add apt package sources using add_source(). Queue deb packages for
installation with install(). Configure and work with your software
once the apt.installed.{packagename} flag is set.
'''
import itertools
import re
import subprocess

from charmhelpers import fetch
from charmhelpers.core import hookenv, unitdata
from charms import layer, reactive
from charms.layer import status
from charms.reactive import flags


__all__ = ['add_source', 'update', 'queue_install', 'install_queued', 'installed', 'purge', 'ensure_package_status']


def add_source(source, key=None):
    '''Add an apt source.

    Sets the apt.needs_update flag.

    A source may be either a line that can be added directly to
    sources.list(5), or in the form ppa:<user>/<ppa-name> for adding
    Personal Package Archives, or a distribution component to enable.

    The package signing key should be an ASCII armoured GPG key. While
    GPG key ids are also supported, the retrieval mechanism is insecure.
    There is no need to specify the package signing key for PPAs or for
    the main Ubuntu archives.
    '''
    # Maybe we should remember which sources have been added already
    # so we don't waste time re-adding them. Is this time significant?
    fetch.add_source(source, key)
    reactive.set_flag('apt.needs_update')


def queue_install(packages, options=None):
    """Queue one or more deb packages for install.

    The `apt.installed.{name}` flag is set once the package is installed.

    If a package has already been installed it will not be reinstalled.

    If a package has already been queued it will not be requeued, and
    the install options will not be changed.

    Sets the apt.queued_installs flag.
    """
    if isinstance(packages, str):
        packages = [packages]
    # Filter installed packages.
    store = unitdata.kv()
    queued_packages = store.getrange('apt.install_queue.', strip=True)
    packages = {
        package: options
        for package in packages
        if not (package in queued_packages or reactive.is_flag_set('apt.installed.' + package))
    }
    if packages:
        unitdata.kv().update(packages, prefix='apt.install_queue.')
        reactive.set_flag('apt.queued_installs')


def installed():
    '''Return the set of deb packages completed install'''
    return set(flag.split('.', 2)[2] for flag in flags.get_flags() if flag.startswith('apt.installed.'))


def purge(packages):
    """Purge one or more deb packages from the system"""
    fetch.apt_purge(packages, fatal=True)
    store = unitdata.kv()
    store.unsetrange(packages, prefix='apt.install_queue.')
    for package in packages:
        reactive.clear_flag('apt.installed.{}'.format(package))


def update():
    """Update the apt cache.

    Removes the apt.needs_update flag.
    """
    status.maintenance('Updating apt cache')
    fetch.apt_update(fatal=True)  # Friends don't let friends set fatal=False
    reactive.clear_flag('apt.needs_update')


def install_queued():
    '''Installs queued deb packages.

    Removes the apt.queued_installs flag and sets the apt.installed flag.

    On failure, sets the unit's workload status to 'blocked' and returns
    False. Package installs remain queued.

    On success, sets the apt.installed.{packagename} flag for each
    installed package and returns True.
    '''
    store = unitdata.kv()
    queue = sorted((options, package) for package, options in store.getrange('apt.install_queue.', strip=True).items())

    installed = set()
    for options, batch in itertools.groupby(queue, lambda x: x[0]):
        packages = [b[1] for b in batch]
        try:
            status.maintenance('Installing {}'.format(','.join(packages)))
            fetch.apt_install(packages, options, fatal=True)
            store.unsetrange(packages, prefix='apt.install_queue.')
            installed.update(packages)
        except subprocess.CalledProcessError:
            status.blocked('Unable to install packages {}'.format(','.join(packages)))
            return False  # Without setting reactive flag.

    for package in installed:
        reactive.set_flag('apt.installed.{}'.format(package))
    reactive.clear_flag('apt.queued_installs')

    reset_application_version()

    return True


def get_package_version(package, full_version=False):
    '''Return the version of an installed package.

    If `full_version` is True, returns the full Debian package version.
    Otherwise, returns the shorter 'upstream' version number.
    '''
    # Don't use fetch.get_upstream_version, as it depends on python-apt
    # and not available if the basic layer's use_site_packages option is off.
    cmd = ['dpkg-query', '--show', r'--showformat=${Version}\n', package]
    full = subprocess.check_output(cmd, universal_newlines=True).strip()
    if not full_version:
        # Attempt to strip off Debian style metadata from the end of the
        # version number.
        m = re.search(r'^([\d.a-z]+)', full, re.I)
        if m is not None:
            return m.group(1)
    return full


def reset_application_version():
    '''Set the Juju application version, per settings in layer.yaml'''
    # Reset the application version. We call this after installing
    # packages to initialize the version. We also call this every
    # hook, incase the version has changed (eg. Landscape upgraded
    # the package).
    opts = layer.options().get('apt', {})
    pkg = opts.get('version_package')
    if pkg and pkg in installed():
        ver = get_package_version(pkg, opts.get('full_version', False))
        hookenv.application_version_set(ver)


def ensure_package_status():
    '''Hold or unhold packages per the package_status configuration option.

    All packages installed using this module and handlers are affected.

    An mechanism may be added in the future to override this for a
    subset of installed packages.
    '''
    packages = installed()
    if not packages:
        return
    config = hookenv.config()
    package_status = config.get('package_status') or ''
    changed = reactive.data_changed('apt.package_status', (package_status, sorted(packages)))
    if changed:
        if package_status == 'hold':
            hookenv.log('Holding packages {}'.format(','.join(packages)))
            fetch.apt_hold(packages)
        else:
            hookenv.log('Unholding packages {}'.format(','.join(packages)))
            fetch.apt_unhold(packages)
    reactive.clear_flag('apt.needs_hold')


def status_set(state, message):
    '''DEPRECATED, set the unit's workload status.

    Set state == None to keep the same state and just change the message.
    '''
    if state is None:
        state = hookenv.status_get()[0]
        if state not in ('active', 'waiting', 'blocked'):
            state = 'maintenance'  # Guess
    status.status_set(state, message)
