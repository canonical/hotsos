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

from collections import OrderedDict
import os
import platform
import re
import six
import subprocess
import sys
import time

from charmhelpers import deprecate
from charmhelpers.core.host import get_distrib_codename, get_system_env

from charmhelpers.core.hookenv import (
    log,
    DEBUG,
    WARNING,
    env_proxy_settings,
)
from charmhelpers.fetch import SourceConfigError, GPGKeyError
from charmhelpers.fetch import ubuntu_apt_pkg

PROPOSED_POCKET = (
    "# Proposed\n"
    "deb http://archive.ubuntu.com/ubuntu {}-proposed main universe "
    "multiverse restricted\n")
PROPOSED_PORTS_POCKET = (
    "# Proposed\n"
    "deb http://ports.ubuntu.com/ubuntu-ports {}-proposed main universe "
    "multiverse restricted\n")
# Only supports 64bit and ppc64 at the moment.
ARCH_TO_PROPOSED_POCKET = {
    'x86_64': PROPOSED_POCKET,
    'ppc64le': PROPOSED_PORTS_POCKET,
    'aarch64': PROPOSED_PORTS_POCKET,
    's390x': PROPOSED_PORTS_POCKET,
}
CLOUD_ARCHIVE_URL = "http://ubuntu-cloud.archive.canonical.com/ubuntu"
CLOUD_ARCHIVE_KEY_ID = '5EDB1B62EC4926EA'
CLOUD_ARCHIVE = """# Ubuntu Cloud Archive
deb http://ubuntu-cloud.archive.canonical.com/ubuntu {} main
"""
CLOUD_ARCHIVE_POCKETS = {
    # Folsom
    'folsom': 'precise-updates/folsom',
    'folsom/updates': 'precise-updates/folsom',
    'precise-folsom': 'precise-updates/folsom',
    'precise-folsom/updates': 'precise-updates/folsom',
    'precise-updates/folsom': 'precise-updates/folsom',
    'folsom/proposed': 'precise-proposed/folsom',
    'precise-folsom/proposed': 'precise-proposed/folsom',
    'precise-proposed/folsom': 'precise-proposed/folsom',
    # Grizzly
    'grizzly': 'precise-updates/grizzly',
    'grizzly/updates': 'precise-updates/grizzly',
    'precise-grizzly': 'precise-updates/grizzly',
    'precise-grizzly/updates': 'precise-updates/grizzly',
    'precise-updates/grizzly': 'precise-updates/grizzly',
    'grizzly/proposed': 'precise-proposed/grizzly',
    'precise-grizzly/proposed': 'precise-proposed/grizzly',
    'precise-proposed/grizzly': 'precise-proposed/grizzly',
    # Havana
    'havana': 'precise-updates/havana',
    'havana/updates': 'precise-updates/havana',
    'precise-havana': 'precise-updates/havana',
    'precise-havana/updates': 'precise-updates/havana',
    'precise-updates/havana': 'precise-updates/havana',
    'havana/proposed': 'precise-proposed/havana',
    'precise-havana/proposed': 'precise-proposed/havana',
    'precise-proposed/havana': 'precise-proposed/havana',
    # Icehouse
    'icehouse': 'precise-updates/icehouse',
    'icehouse/updates': 'precise-updates/icehouse',
    'precise-icehouse': 'precise-updates/icehouse',
    'precise-icehouse/updates': 'precise-updates/icehouse',
    'precise-updates/icehouse': 'precise-updates/icehouse',
    'icehouse/proposed': 'precise-proposed/icehouse',
    'precise-icehouse/proposed': 'precise-proposed/icehouse',
    'precise-proposed/icehouse': 'precise-proposed/icehouse',
    # Juno
    'juno': 'trusty-updates/juno',
    'juno/updates': 'trusty-updates/juno',
    'trusty-juno': 'trusty-updates/juno',
    'trusty-juno/updates': 'trusty-updates/juno',
    'trusty-updates/juno': 'trusty-updates/juno',
    'juno/proposed': 'trusty-proposed/juno',
    'trusty-juno/proposed': 'trusty-proposed/juno',
    'trusty-proposed/juno': 'trusty-proposed/juno',
    # Kilo
    'kilo': 'trusty-updates/kilo',
    'kilo/updates': 'trusty-updates/kilo',
    'trusty-kilo': 'trusty-updates/kilo',
    'trusty-kilo/updates': 'trusty-updates/kilo',
    'trusty-updates/kilo': 'trusty-updates/kilo',
    'kilo/proposed': 'trusty-proposed/kilo',
    'trusty-kilo/proposed': 'trusty-proposed/kilo',
    'trusty-proposed/kilo': 'trusty-proposed/kilo',
    # Liberty
    'liberty': 'trusty-updates/liberty',
    'liberty/updates': 'trusty-updates/liberty',
    'trusty-liberty': 'trusty-updates/liberty',
    'trusty-liberty/updates': 'trusty-updates/liberty',
    'trusty-updates/liberty': 'trusty-updates/liberty',
    'liberty/proposed': 'trusty-proposed/liberty',
    'trusty-liberty/proposed': 'trusty-proposed/liberty',
    'trusty-proposed/liberty': 'trusty-proposed/liberty',
    # Mitaka
    'mitaka': 'trusty-updates/mitaka',
    'mitaka/updates': 'trusty-updates/mitaka',
    'trusty-mitaka': 'trusty-updates/mitaka',
    'trusty-mitaka/updates': 'trusty-updates/mitaka',
    'trusty-updates/mitaka': 'trusty-updates/mitaka',
    'mitaka/proposed': 'trusty-proposed/mitaka',
    'trusty-mitaka/proposed': 'trusty-proposed/mitaka',
    'trusty-proposed/mitaka': 'trusty-proposed/mitaka',
    # Newton
    'newton': 'xenial-updates/newton',
    'newton/updates': 'xenial-updates/newton',
    'xenial-newton': 'xenial-updates/newton',
    'xenial-newton/updates': 'xenial-updates/newton',
    'xenial-updates/newton': 'xenial-updates/newton',
    'newton/proposed': 'xenial-proposed/newton',
    'xenial-newton/proposed': 'xenial-proposed/newton',
    'xenial-proposed/newton': 'xenial-proposed/newton',
    # Ocata
    'ocata': 'xenial-updates/ocata',
    'ocata/updates': 'xenial-updates/ocata',
    'xenial-ocata': 'xenial-updates/ocata',
    'xenial-ocata/updates': 'xenial-updates/ocata',
    'xenial-updates/ocata': 'xenial-updates/ocata',
    'ocata/proposed': 'xenial-proposed/ocata',
    'xenial-ocata/proposed': 'xenial-proposed/ocata',
    'xenial-proposed/ocata': 'xenial-proposed/ocata',
    # Pike
    'pike': 'xenial-updates/pike',
    'xenial-pike': 'xenial-updates/pike',
    'xenial-pike/updates': 'xenial-updates/pike',
    'xenial-updates/pike': 'xenial-updates/pike',
    'pike/proposed': 'xenial-proposed/pike',
    'xenial-pike/proposed': 'xenial-proposed/pike',
    'xenial-proposed/pike': 'xenial-proposed/pike',
    # Queens
    'queens': 'xenial-updates/queens',
    'xenial-queens': 'xenial-updates/queens',
    'xenial-queens/updates': 'xenial-updates/queens',
    'xenial-updates/queens': 'xenial-updates/queens',
    'queens/proposed': 'xenial-proposed/queens',
    'xenial-queens/proposed': 'xenial-proposed/queens',
    'xenial-proposed/queens': 'xenial-proposed/queens',
    # Rocky
    'rocky': 'bionic-updates/rocky',
    'bionic-rocky': 'bionic-updates/rocky',
    'bionic-rocky/updates': 'bionic-updates/rocky',
    'bionic-updates/rocky': 'bionic-updates/rocky',
    'rocky/proposed': 'bionic-proposed/rocky',
    'bionic-rocky/proposed': 'bionic-proposed/rocky',
    'bionic-proposed/rocky': 'bionic-proposed/rocky',
    # Stein
    'stein': 'bionic-updates/stein',
    'bionic-stein': 'bionic-updates/stein',
    'bionic-stein/updates': 'bionic-updates/stein',
    'bionic-updates/stein': 'bionic-updates/stein',
    'stein/proposed': 'bionic-proposed/stein',
    'bionic-stein/proposed': 'bionic-proposed/stein',
    'bionic-proposed/stein': 'bionic-proposed/stein',
    # Train
    'train': 'bionic-updates/train',
    'bionic-train': 'bionic-updates/train',
    'bionic-train/updates': 'bionic-updates/train',
    'bionic-updates/train': 'bionic-updates/train',
    'train/proposed': 'bionic-proposed/train',
    'bionic-train/proposed': 'bionic-proposed/train',
    'bionic-proposed/train': 'bionic-proposed/train',
    # Ussuri
    'ussuri': 'bionic-updates/ussuri',
    'bionic-ussuri': 'bionic-updates/ussuri',
    'bionic-ussuri/updates': 'bionic-updates/ussuri',
    'bionic-updates/ussuri': 'bionic-updates/ussuri',
    'ussuri/proposed': 'bionic-proposed/ussuri',
    'bionic-ussuri/proposed': 'bionic-proposed/ussuri',
    'bionic-proposed/ussuri': 'bionic-proposed/ussuri',
    # Victoria
    'victoria': 'focal-updates/victoria',
    'focal-victoria': 'focal-updates/victoria',
    'focal-victoria/updates': 'focal-updates/victoria',
    'focal-updates/victoria': 'focal-updates/victoria',
    'victoria/proposed': 'focal-proposed/victoria',
    'focal-victoria/proposed': 'focal-proposed/victoria',
    'focal-proposed/victoria': 'focal-proposed/victoria',
    # Wallaby
    'wallaby': 'focal-updates/wallaby',
    'focal-wallaby': 'focal-updates/wallaby',
    'focal-wallaby/updates': 'focal-updates/wallaby',
    'focal-updates/wallaby': 'focal-updates/wallaby',
    'wallaby/proposed': 'focal-proposed/wallaby',
    'focal-wallaby/proposed': 'focal-proposed/wallaby',
    'focal-proposed/wallaby': 'focal-proposed/wallaby',
    # Xena
    'xena': 'focal-updates/xena',
    'focal-xena': 'focal-updates/xena',
    'focal-xena/updates': 'focal-updates/xena',
    'focal-updates/xena': 'focal-updates/xena',
    'xena/proposed': 'focal-proposed/xena',
    'focal-xena/proposed': 'focal-proposed/xena',
    'focal-proposed/xena': 'focal-proposed/xena',
    # Yoga
    'yoga': 'focal-updates/yoga',
    'focal-yoga': 'focal-updates/yoga',
    'focal-yoga/updates': 'focal-updates/yoga',
    'focal-updates/yoga': 'focal-updates/yoga',
    'yoga/proposed': 'focal-proposed/yoga',
    'focal-yoga/proposed': 'focal-proposed/yoga',
    'focal-proposed/yoga': 'focal-proposed/yoga',
}


OPENSTACK_RELEASES = (
    'diablo',
    'essex',
    'folsom',
    'grizzly',
    'havana',
    'icehouse',
    'juno',
    'kilo',
    'liberty',
    'mitaka',
    'newton',
    'ocata',
    'pike',
    'queens',
    'rocky',
    'stein',
    'train',
    'ussuri',
    'victoria',
    'wallaby',
    'xena',
    'yoga',
)


UBUNTU_OPENSTACK_RELEASE = OrderedDict([
    ('oneiric', 'diablo'),
    ('precise', 'essex'),
    ('quantal', 'folsom'),
    ('raring', 'grizzly'),
    ('saucy', 'havana'),
    ('trusty', 'icehouse'),
    ('utopic', 'juno'),
    ('vivid', 'kilo'),
    ('wily', 'liberty'),
    ('xenial', 'mitaka'),
    ('yakkety', 'newton'),
    ('zesty', 'ocata'),
    ('artful', 'pike'),
    ('bionic', 'queens'),
    ('cosmic', 'rocky'),
    ('disco', 'stein'),
    ('eoan', 'train'),
    ('focal', 'ussuri'),
    ('groovy', 'victoria'),
    ('hirsute', 'wallaby'),
    ('impish', 'xena'),
    ('jammy', 'yoga'),
])


APT_NO_LOCK = 100  # The return code for "couldn't acquire lock" in APT.
CMD_RETRY_DELAY = 10  # Wait 10 seconds between command retries.
CMD_RETRY_COUNT = 10  # Retry a failing fatal command X times.


def filter_installed_packages(packages):
    """Return a list of packages that require installation."""
    cache = apt_cache()
    _pkgs = []
    for package in packages:
        try:
            p = cache[package]
            p.current_ver or _pkgs.append(package)
        except KeyError:
            log('Package {} has no installation candidate.'.format(package),
                level='WARNING')
            _pkgs.append(package)
    return _pkgs


def filter_missing_packages(packages):
    """Return a list of packages that are installed.

    :param packages: list of packages to evaluate.
    :returns list: Packages that are installed.
    """
    return list(
        set(packages) -
        set(filter_installed_packages(packages))
    )


def apt_cache(*_, **__):
    """Shim returning an object simulating the apt_pkg Cache.

    :param _: Accept arguments for compatibility, not used.
    :type _: any
    :param __: Accept keyword arguments for compatibility, not used.
    :type __: any
    :returns:Object used to interrogate the system apt and dpkg databases.
    :rtype:ubuntu_apt_pkg.Cache
    """
    if 'apt_pkg' in sys.modules:
        # NOTE(fnordahl): When our consumer use the upstream ``apt_pkg`` module
        # in conjunction with the apt_cache helper function, they may expect us
        # to call ``apt_pkg.init()`` for them.
        #
        # Detect this situation, log a warning and make the call to
        # ``apt_pkg.init()`` to avoid the consumer Python interpreter from
        # crashing with a segmentation fault.
        @deprecate(
            'Support for use of upstream ``apt_pkg`` module in conjunction'
            'with charm-helpers is deprecated since 2019-06-25',
            date=None, log=lambda x: log(x, level=WARNING))
        def one_shot_log():
            pass

        one_shot_log()
        sys.modules['apt_pkg'].init()
    return ubuntu_apt_pkg.Cache()


def apt_install(packages, options=None, fatal=False, quiet=False):
    """Install one or more packages.

    :param packages: Package(s) to install
    :type packages: Option[str, List[str]]
    :param options: Options to pass on to apt-get
    :type options: Option[None, List[str]]
    :param fatal: Whether the command's output should be checked and
                  retried.
    :type fatal: bool
    :param quiet: if True (default), suppress log message to stdout/stderr
    :type quiet: bool
    :raises: subprocess.CalledProcessError
    """
    if options is None:
        options = ['--option=Dpkg::Options::=--force-confold']

    cmd = ['apt-get', '--assume-yes']
    cmd.extend(options)
    cmd.append('install')
    if isinstance(packages, six.string_types):
        cmd.append(packages)
    else:
        cmd.extend(packages)
    if not quiet:
        log("Installing {} with options: {}"
            .format(packages, options))
    _run_apt_command(cmd, fatal, quiet=quiet)


def apt_upgrade(options=None, fatal=False, dist=False):
    """Upgrade all packages.

    :param options: Options to pass on to apt-get
    :type options: Option[None, List[str]]
    :param fatal: Whether the command's output should be checked and
                  retried.
    :type fatal: bool
    :param dist: Whether ``dist-upgrade`` should be used over ``upgrade``
    :type dist: bool
    :raises: subprocess.CalledProcessError
    """
    if options is None:
        options = ['--option=Dpkg::Options::=--force-confold']

    cmd = ['apt-get', '--assume-yes']
    cmd.extend(options)
    if dist:
        cmd.append('dist-upgrade')
    else:
        cmd.append('upgrade')
    log("Upgrading with options: {}".format(options))
    _run_apt_command(cmd, fatal)


def apt_update(fatal=False):
    """Update local apt cache."""
    cmd = ['apt-get', 'update']
    _run_apt_command(cmd, fatal)


def apt_purge(packages, fatal=False):
    """Purge one or more packages.

    :param packages: Package(s) to install
    :type packages: Option[str, List[str]]
    :param fatal: Whether the command's output should be checked and
                  retried.
    :type fatal: bool
    :raises: subprocess.CalledProcessError
    """
    cmd = ['apt-get', '--assume-yes', 'purge']
    if isinstance(packages, six.string_types):
        cmd.append(packages)
    else:
        cmd.extend(packages)
    log("Purging {}".format(packages))
    _run_apt_command(cmd, fatal)


def apt_autoremove(purge=True, fatal=False):
    """Purge one or more packages.
    :param purge: Whether the ``--purge`` option should be passed on or not.
    :type purge: bool
    :param fatal: Whether the command's output should be checked and
                  retried.
    :type fatal: bool
    :raises: subprocess.CalledProcessError
    """
    cmd = ['apt-get', '--assume-yes', 'autoremove']
    if purge:
        cmd.append('--purge')
    _run_apt_command(cmd, fatal)


def apt_mark(packages, mark, fatal=False):
    """Flag one or more packages using apt-mark."""
    log("Marking {} as {}".format(packages, mark))
    cmd = ['apt-mark', mark]
    if isinstance(packages, six.string_types):
        cmd.append(packages)
    else:
        cmd.extend(packages)

    if fatal:
        subprocess.check_call(cmd, universal_newlines=True)
    else:
        subprocess.call(cmd, universal_newlines=True)


def apt_hold(packages, fatal=False):
    return apt_mark(packages, 'hold', fatal=fatal)


def apt_unhold(packages, fatal=False):
    return apt_mark(packages, 'unhold', fatal=fatal)


def import_key(key):
    """Import an ASCII Armor key.

    A Radix64 format keyid is also supported for backwards
    compatibility. In this case Ubuntu keyserver will be
    queried for a key via HTTPS by its keyid. This method
    is less preferable because https proxy servers may
    require traffic decryption which is equivalent to a
    man-in-the-middle attack (a proxy server impersonates
    keyserver TLS certificates and has to be explicitly
    trusted by the system).

    :param key: A GPG key in ASCII armor format,
                  including -----SCRUBBED markers or a keyid.
    :type key: (bytes, str)
    :raises: GPGKeyError if the key could not be imported
    """
    key = key.strip()
    if '-' in key or '\n' in key:
        # Send everything not obviously a keyid to GPG to import, as
        # we trust its validation better than our own. eg. handling
        # comments before the key.
        log("PGP key found (looks like ASCII Armor format)", level=DEBUG)
        if ('-----SCRUBBED PGP PUBLIC KEY BLOCK-----' in key):
            log("Writing provided PGP key in the binary format", level=DEBUG)
            if six.PY3:
                key_bytes = key.encode('utf-8')
            else:
                key_bytes = key
            key_name = _get_keyid_by_gpg_key(key_bytes)
            key_gpg = _dearmor_gpg_key(key_bytes)
            _write_apt_gpg_keyfile(key_name=key_name, key_material=key_gpg)
        else:
            raise GPGKeyError("ASCII armor markers missing from GPG key")
    else:
        log("PGP key found (looks like Radix64 format)", level=WARNING)
        log("SECURELY importing PGP key from keyserver; "
            "full key not provided.", level=WARNING)
        # as of bionic add-apt-repository uses curl with an HTTPS keyserver URL
        # to retrieve GPG keys. `apt-key adv` command is deprecated as is
        # apt-key in general as noted in its manpage. See lp:1433761 for more
        # history. Instead, /etc/apt/trusted.gpg.d is used directly to drop
        # gpg
        key_asc = _get_key_by_keyid(key)
        # write the key in GPG format so that apt-key list shows it
        key_gpg = _dearmor_gpg_key(key_asc)
        _write_apt_gpg_keyfile(key_name=key, key_material=key_gpg)


def _get_keyid_by_gpg_key(key_material):
    """Get a GPG key fingerprint by GPG key material.
    Gets a GPG key fingerprint (40-digit, 160-bit) by the ASCII armor-encoded
    or binary GPG key material. Can be used, for example, to generate file
    names for keys passed via charm options.

    :param key_material: ASCII armor-encoded or binary GPG key material
    :type key_material: bytes
    :raises: GPGKeyError if invalid key material has been provided
    :returns: A GPG key fingerprint
    :rtype: str
    """
    # Use the same gpg command for both Xenial and Bionic
    cmd = 'gpg --with-colons --with-fingerprint'
    ps = subprocess.Popen(cmd.split(),
                          stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE,
                          stdin=subprocess.PIPE)
    out, err = ps.communicate(input=key_material)
    if six.PY3:
        out = out.decode('utf-8')
        err = err.decode('utf-8')
    if 'gpg: no valid OpenPGP data found.' in err:
        raise GPGKeyError('Invalid GPG key material provided')
    # from gnupg2 docs: fpr :: Fingerprint (fingerprint is in field 10)
    return re.search(r"^fpr:{9}([0-9A-F]{40}):$", out, re.MULTILINE).group(1)


def _get_key_by_keyid(keyid):
    """Get a key via HTTPS from the Ubuntu keyserver.
    Different key ID formats are supported by SKS keyservers (the longer ones
    are more secure, see "dead beef attack" and https://evil32.com/). Since
    HTTPS is used, if SSLBump-like HTTPS proxies are in place, they will
    impersonate keyserver.ubuntu.com and generate a certificate with
    keyserver.ubuntu.com in the CN field or in SubjAltName fields of a
    certificate. If such proxy behavior is expected it is necessary to add the
    CA certificate chain containing the intermediate CA of the SSLBump proxy to
    every machine that this code runs on via ca-certs cloud-init directive (via
    cloudinit-userdata model-config) or via other means (such as through a
    custom charm option). Also note that DNS resolution for the hostname in a
    URL is done at a proxy server - not at the client side.

    8-digit (32 bit) key ID
    https://keyserver.ubuntu.com/pks/lookup?search=0x4652B4E6
    16-digit (64 bit) key ID
    https://keyserver.ubuntu.com/pks/lookup?search=0x6E85A86E4652B4E6
    40-digit key ID:
    https://keyserver.ubuntu.com/pks/lookup?search=0x35F77D63B5CEC106C577ED856E85A86E4652B4E6

    :param keyid: An 8, 16 or 40 hex digit keyid to find a key for
    :type keyid: (bytes, str)
    :returns: A key material for the specified GPG key id
    :rtype: (str, bytes)
    :raises: subprocess.CalledProcessError
    """
    # options=mr - machine-readable output (disables html wrappers)
    keyserver_url = ('https://keyserver.ubuntu.com'
                     '/pks/lookup?op=get&options=mr&exact=on&search=0x{}')
    curl_cmd = ['curl', keyserver_url.format(keyid)]
    # use proxy server settings in order to retrieve the key
    return subprocess.check_output(curl_cmd,
                                   env=env_proxy_settings(['https']))


def _dearmor_gpg_key(key_asc):
    """Converts a GPG key in the ASCII armor format to the binary format.

    :param key_asc: A GPG key in ASCII armor format.
    :type key_asc: (str, bytes)
    :returns: A GPG key in binary format
    :rtype: (str, bytes)
    :raises: GPGKeyError
    """
    ps = subprocess.Popen(['gpg', '--dearmor'],
                          stdout=subprocess.PIPE,
                          stderr=subprocess.PIPE,
                          stdin=subprocess.PIPE)
    out, err = ps.communicate(input=key_asc)
    # no need to decode output as it is binary (invalid utf-8), only error
    if six.PY3:
        err = err.decode('utf-8')
    if 'gpg: no valid OpenPGP data found.' in err:
        raise GPGKeyError('Invalid GPG key material. Check your network setup'
                          ' (MTU, routing, DNS) and/or proxy server settings'
                          ' as well as destination keyserver status.')
    else:
        return out


def _write_apt_gpg_keyfile(key_name, key_material):
    """Writes GPG key material into a file at a provided path.

    :param key_name: A key name to use for a key file (could be a fingerprint)
    :type key_name: str
    :param key_material: A GPG key material (binary)
    :type key_material: (str, bytes)
    """
    with open('/etc/apt/trusted.gpg.d/{}.gpg'.format(key_name),
              'wb') as keyf:
        keyf.write(key_material)


def add_source(source, key=None, fail_invalid=False):
    """Add a package source to this system.

    @param source: a URL or sources.list entry, as supported by
    add-apt-repository(1). Examples::

        ppa:charmers/example
        deb https://stub:key@private.example.com/ubuntu trusty main

    In addition:
        'proposed:' may be used to enable the standard 'proposed'
        pocket for the release.
        'cloud:' may be used to activate official cloud archive pockets,
        such as 'cloud:icehouse'
        'distro' may be used as a noop

    Full list of source specifications supported by the function are:

    'distro': A NOP; i.e. it has no effect.
    'proposed': the proposed deb spec [2] is wrtten to
      /etc/apt/sources.list/proposed
    'distro-proposed': adds <version>-proposed to the debs [2]
    'ppa:<ppa-name>': add-apt-repository --yes <ppa_name>
    'deb <deb-spec>': add-apt-repository --yes deb <deb-spec>
    'http://....': add-apt-repository --yes http://...
    'cloud-archive:<spec>': add-apt-repository -yes cloud-archive:<spec>
    'cloud:<release>[-staging]': specify a Cloud Archive pocket <release> with
      optional staging version.  If staging is used then the staging PPA [2]
      with be used.  If staging is NOT used then the cloud archive [3] will be
      added, and the 'ubuntu-cloud-keyring' package will be added for the
      current distro.
    '<openstack-version>': translate to cloud:<release> based on the current
      distro version (i.e. for 'ussuri' this will either be 'bionic-ussuri' or
      'distro'.
    '<openstack-version>/proposed': as above, but for proposed.

    Otherwise the source is not recognised and this is logged to the juju log.
    However, no error is raised, unless sys_error_on_exit is True.

    [1] deb http://ubuntu-cloud.archive.canonical.com/ubuntu {} main
        where {} is replaced with the derived pocket name.
    [2] deb http://archive.ubuntu.com/ubuntu {}-proposed \
        main universe multiverse restricted
        where {} is replaced with the lsb_release codename (e.g. xenial)
    [3] deb http://ubuntu-cloud.archive.canonical.com/ubuntu <pocket>
        to /etc/apt/sources.list.d/cloud-archive-list

    @param key: A key to be added to the system's APT keyring and used
    to verify the signatures on packages. Ideally, this should be an
    ASCII format GPG public key including the block headers. A GPG key
    id may also be used, but be aware that only insecure protocols are
    available to retrieve the actual public key from a public keyserver
    placing your Juju environment at risk. ppa and cloud archive keys
    are securely added automatically, so should not be provided.

    @param fail_invalid: (boolean) if True, then the function raises a
    SourceConfigError is there is no matching installation source.

    @raises SourceConfigError() if for cloud:<pocket>, the <pocket> is not a
    valid pocket in CLOUD_ARCHIVE_POCKETS
    """
    # extract the OpenStack versions from the CLOUD_ARCHIVE_POCKETS; can't use
    # the list in contrib.openstack.utils as it might not be included in
    # classic charms and would break everything.  Having OpenStack specific
    # code in this file is a bit of an antipattern, anyway.
    os_versions_regex = "({})".format("|".join(OPENSTACK_RELEASES))

    _mapping = OrderedDict([
        (r"^distro$", lambda: None),  # This is a NOP
        (r"^(?:proposed|distro-proposed)$", _add_proposed),
        (r"^cloud-archive:(.*)$", _add_apt_repository),
        (r"^((?:deb |http:|https:|ppa:).*)$", _add_apt_repository),
        (r"^cloud:(.*)-(.*)\/staging$", _add_cloud_staging),
        (r"^cloud:(.*)-(.*)$", _add_cloud_distro_check),
        (r"^cloud:(.*)$", _add_cloud_pocket),
        (r"^snap:.*-(.*)-(.*)$", _add_cloud_distro_check),
        (r"^{}\/proposed$".format(os_versions_regex),
         _add_bare_openstack_proposed),
        (r"^{}$".format(os_versions_regex), _add_bare_openstack),
    ])
    if source is None:
        source = ''
    for r, fn in six.iteritems(_mapping):
        m = re.match(r, source)
        if m:
            if key:
                # Import key before adding the source which depends on it,
                # as refreshing packages could fail otherwise.
                try:
                    import_key(key)
                except GPGKeyError as e:
                    raise SourceConfigError(str(e))
            # call the associated function with the captured groups
            # raises SourceConfigError on error.
            fn(*m.groups())
            break
    else:
        # nothing matched.  log an error and maybe sys.exit
        err = "Unknown source: {!r}".format(source)
        log(err)
        if fail_invalid:
            raise SourceConfigError(err)


def _add_proposed():
    """Add the PROPOSED_POCKET as /etc/apt/source.list.d/proposed.list

    Uses get_distrib_codename to determine the correct stanza for
    the deb line.

    For Intel architectures PROPOSED_POCKET is used for the release, but for
    other architectures PROPOSED_PORTS_POCKET is used for the release.
    """
    release = get_distrib_codename()
    arch = platform.machine()
    if arch not in six.iterkeys(ARCH_TO_PROPOSED_POCKET):
        raise SourceConfigError("Arch {} not supported for (distro-)proposed"
                                .format(arch))
    with open('/etc/apt/sources.list.d/proposed.list', 'w') as apt:
        apt.write(ARCH_TO_PROPOSED_POCKET[arch].format(release))


def _add_apt_repository(spec):
    """Add the spec using add_apt_repository

    :param spec: the parameter to pass to add_apt_repository
    :type spec: str
    """
    if '{series}' in spec:
        series = get_distrib_codename()
        spec = spec.replace('{series}', series)
    _run_with_retries(['add-apt-repository', '--yes', spec],
                      cmd_env=env_proxy_settings(['https', 'http', 'no_proxy'])
                      )


def _add_cloud_pocket(pocket):
    """Add a cloud pocket as /etc/apt/sources.d/cloud-archive.list

    Note that this overwrites the existing file if there is one.

    This function also converts the simple pocket in to the actual pocket using
    the CLOUD_ARCHIVE_POCKETS mapping.

    :param pocket: string representing the pocket to add a deb spec for.
    :raises: SourceConfigError if the cloud pocket doesn't exist or the
        requested release doesn't match the current distro version.
    """
    apt_install(filter_installed_packages(['ubuntu-cloud-keyring']),
                fatal=True)
    if pocket not in CLOUD_ARCHIVE_POCKETS:
        raise SourceConfigError(
            'Unsupported cloud: source option %s' %
            pocket)
    actual_pocket = CLOUD_ARCHIVE_POCKETS[pocket]
    with open('/etc/apt/sources.list.d/cloud-archive.list', 'w') as apt:
        apt.write(CLOUD_ARCHIVE.format(actual_pocket))


def _add_cloud_staging(cloud_archive_release, openstack_release):
    """Add the cloud staging repository which is in
    ppa:ubuntu-cloud-archive/<openstack_release>-staging

    This function checks that the cloud_archive_release matches the current
    codename for the distro that charm is being installed on.

    :param cloud_archive_release: string, codename for the release.
    :param openstack_release: String, codename for the openstack release.
    :raises: SourceConfigError if the cloud_archive_release doesn't match the
        current version of the os.
    """
    _verify_is_ubuntu_rel(cloud_archive_release, openstack_release)
    ppa = 'ppa:ubuntu-cloud-archive/{}-staging'.format(openstack_release)
    cmd = 'add-apt-repository -y {}'.format(ppa)
    _run_with_retries(cmd.split(' '))


def _add_cloud_distro_check(cloud_archive_release, openstack_release):
    """Add the cloud pocket, but also check the cloud_archive_release against
    the current distro, and use the openstack_release as the full lookup.

    This just calls _add_cloud_pocket() with the openstack_release as pocket
    to get the correct cloud-archive.list for dpkg to work with.

    :param cloud_archive_release:String, codename for the distro release.
    :param openstack_release: String, spec for the release to look up in the
        CLOUD_ARCHIVE_POCKETS
    :raises: SourceConfigError if this is the wrong distro, or the pocket spec
        doesn't exist.
    """
    _verify_is_ubuntu_rel(cloud_archive_release, openstack_release)
    _add_cloud_pocket("{}-{}".format(cloud_archive_release, openstack_release))


def _verify_is_ubuntu_rel(release, os_release):
    """Verify that the release is in the same as the current ubuntu release.

    :param release: String, lowercase for the release.
    :param os_release: String, the os_release being asked for
    :raises: SourceConfigError if the release is not the same as the ubuntu
        release.
    """
    ubuntu_rel = get_distrib_codename()
    if release != ubuntu_rel:
        raise SourceConfigError(
            'Invalid Cloud Archive release specified: {}-{} on this Ubuntu'
            'version ({})'.format(release, os_release, ubuntu_rel))


def _add_bare_openstack(openstack_release):
    """Add cloud or distro based on the release given.

    The spec given is, say, 'ussuri', but this could apply cloud:bionic-ussuri
    or 'distro' depending on whether the ubuntu release is bionic or focal.

    :param openstack_release: the OpenStack codename to determine the release
        for.
    :type openstack_release: str
    :raises: SourceConfigError
    """
    # TODO(ajkavanagh) - surely this means we should be removing cloud archives
    # if they exist?
    __add_bare_helper(openstack_release, "{}-{}", lambda: None)


def _add_bare_openstack_proposed(openstack_release):
    """Add cloud of distro but with proposed.

    The spec given is, say, 'ussuri' but this could apply
    cloud:bionic-ussuri/proposed or 'distro/proposed' depending on whether the
    ubuntu release is bionic or focal.

    :param openstack_release: the OpenStack codename to determine the release
        for.
    :type openstack_release: str
    :raises: SourceConfigError
    """
    __add_bare_helper(openstack_release, "{}-{}/proposed", _add_proposed)


def __add_bare_helper(openstack_release, pocket_format, final_function):
    """Helper for _add_bare_openstack[_proposed]

    The bulk of the work between the two functions is exactly the same except
    for the pocket format and the function that is run if it's the distro
    version.

    :param openstack_release: the OpenStack codename.  e.g. ussuri
    :type openstack_release: str
    :param pocket_format: the pocket formatter string to construct a pocket str
        from the openstack_release and the current ubuntu version.
    :type pocket_format: str
    :param final_function: the function to call if it is the distro version.
    :type final_function: Callable
    :raises SourceConfigError on error
    """
    ubuntu_version = get_distrib_codename()
    possible_pocket = pocket_format.format(ubuntu_version, openstack_release)
    if possible_pocket in CLOUD_ARCHIVE_POCKETS:
        _add_cloud_pocket(possible_pocket)
        return
    # Otherwise it's almost certainly the distro version; verify that it
    # exists.
    try:
        assert UBUNTU_OPENSTACK_RELEASE[ubuntu_version] == openstack_release
    except KeyError:
        raise SourceConfigError(
            "Invalid ubuntu version {} isn't known to this library"
            .format(ubuntu_version))
    except AssertionError:
        raise SourceConfigError(
            'Invalid OpenStack release specified: {} for Ubuntu version {}'
            .format(openstack_release, ubuntu_version))
    final_function()


def _run_with_retries(cmd, max_retries=CMD_RETRY_COUNT, retry_exitcodes=(1,),
                      retry_message="", cmd_env=None, quiet=False):
    """Run a command and retry until success or max_retries is reached.

    :param cmd: The apt command to run.
    :type cmd: str
    :param max_retries: The number of retries to attempt on a fatal
                        command. Defaults to CMD_RETRY_COUNT.
    :type max_retries: int
    :param retry_exitcodes: Optional additional exit codes to retry.
                            Defaults to retry on exit code 1.
    :type retry_exitcodes: tuple
    :param retry_message: Optional log prefix emitted during retries.
    :type retry_message: str
    :param: cmd_env: Environment variables to add to the command run.
    :type cmd_env: Option[None, Dict[str, str]]
    :param quiet: if True, silence the output of the command from stdout and
        stderr
    :type quiet: bool
    """
    env = get_apt_dpkg_env()
    if cmd_env:
        env.update(cmd_env)

    kwargs = {}
    if quiet:
        devnull = os.devnull if six.PY2 else subprocess.DEVNULL
        kwargs['stdout'] = devnull
        kwargs['stderr'] = devnull

    if not retry_message:
        retry_message = "Failed executing '{}'".format(" ".join(cmd))
    retry_message += ". Will retry in {} seconds".format(CMD_RETRY_DELAY)

    retry_count = 0
    result = None

    retry_results = (None,) + retry_exitcodes
    while result in retry_results:
        try:
            result = subprocess.check_call(cmd, env=env, **kwargs)
        except subprocess.CalledProcessError as e:
            retry_count = retry_count + 1
            if retry_count > max_retries:
                raise
            result = e.returncode
            log(retry_message)
            time.sleep(CMD_RETRY_DELAY)


def _run_apt_command(cmd, fatal=False, quiet=False):
    """Run an apt command with optional retries.

    :param cmd: The apt command to run.
    :type cmd: str
    :param fatal: Whether the command's output should be checked and
                  retried.
    :type fatal: bool
    :param quiet: if True, silence the output of the command from stdout and
        stderr
    :type quiet: bool
    """
    if fatal:
        _run_with_retries(
            cmd, retry_exitcodes=(1, APT_NO_LOCK,),
            retry_message="Couldn't acquire DPKG lock",
            quiet=quiet)
    else:
        kwargs = {}
        if quiet:
            devnull = os.devnull if six.PY2 else subprocess.DEVNULL
            kwargs['stdout'] = devnull
            kwargs['stderr'] = devnull
        subprocess.call(cmd, env=get_apt_dpkg_env(), **kwargs)


def get_upstream_version(package):
    """Determine upstream version based on installed package

    @returns None (if not installed) or the upstream version
    """
    cache = apt_cache()
    try:
        pkg = cache[package]
    except Exception:
        # the package is unknown to the current apt cache.
        return None

    if not pkg.current_ver:
        # package is known, but no version is currently installed.
        return None

    return ubuntu_apt_pkg.upstream_version(pkg.current_ver.ver_str)


def get_installed_version(package):
    """Determine installed version of a package

    @returns None (if not installed) or the installed version as
    Version object
    """
    cache = apt_cache()
    dpkg_result = cache._dpkg_list([package]).get(package, {})
    current_ver = None
    installed_version = dpkg_result.get('version')

    if installed_version:
        current_ver = ubuntu_apt_pkg.Version({'ver_str': installed_version})
    return current_ver


def get_apt_dpkg_env():
    """Get environment suitable for execution of APT and DPKG tools.

    We keep this in a helper function instead of in a global constant to
    avoid execution on import of the library.
    :returns: Environment suitable for execution of APT and DPKG tools.
    :rtype: Dict[str, str]
    """
    # The fallback is used in the event of ``/etc/environment`` not containing
    # avalid PATH variable.
    return {'DEBIAN_FRONTEND': 'noninteractive',
            'PATH': get_system_env('PATH', '/usr/sbin:/usr/bin:/sbin:/bin')}
