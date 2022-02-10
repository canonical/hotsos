import subprocess

from charmhelpers.core.hookenv import cached
from charmhelpers.core.strutils import BasicStringComparator


UBUNTU_RELEASES = (
    'lucid',
    'maverick',
    'natty',
    'oneiric',
    'precise',
    'quantal',
    'raring',
    'saucy',
    'trusty',
    'utopic',
    'vivid',
    'wily',
    'xenial',
    'yakkety',
    'zesty',
    'artful',
    'bionic',
    'cosmic',
    'disco',
    'eoan',
    'focal',
    'groovy',
    'hirsute',
    'impish',
    'jammy',
)


class CompareHostReleases(BasicStringComparator):
    """Provide comparisons of Ubuntu releases.

    Use in the form of

    if CompareHostReleases(release) > 'trusty':
        # do something with mitaka
    """
    _list = UBUNTU_RELEASES


def service_available(service_name):
    """Determine whether a system service is available"""
    try:
        subprocess.check_output(
            ['service', service_name, 'status'],
            stderr=subprocess.STDOUT).decode('UTF-8')
    except subprocess.CalledProcessError as e:
        return b'unrecognized service' not in e.output
    else:
        return True


def add_new_group(group_name, system_group=False, gid=None):
    cmd = ['addgroup']
    if gid:
        cmd.extend(['--gid', str(gid)])
    if system_group:
        cmd.append('--system')
    else:
        cmd.extend([
            '--group',
        ])
    cmd.append(group_name)
    subprocess.check_call(cmd)


def lsb_release():
    """Return /etc/lsb-release in a dict"""
    d = {}
    with open('/etc/lsb-release', 'r') as lsb:
        for l in lsb:
            k, v = l.split('=')
            d[k.strip()] = v.strip()
    return d


def get_distrib_codename():
    """Return the codename of the distribution
    :returns: The codename
    :rtype: str
    """
    return lsb_release()['DISTRIB_CODENAME'].lower()


def cmp_pkgrevno(package, revno, pkgcache=None):
    """Compare supplied revno with the revno of the installed package.

    *  1 => Installed revno is greater than supplied arg
    *  0 => Installed revno is the same as supplied arg
    * -1 => Installed revno is less than supplied arg

    This function imports apt_cache function from charmhelpers.fetch if
    the pkgcache argument is None. Be sure to add charmhelpers.fetch if
    you call this function, or pass an apt_pkg.Cache() instance.
    """
    from charmhelpers.fetch import apt_pkg, get_installed_version
    if not pkgcache:
        current_ver = get_installed_version(package)
    else:
        pkg = pkgcache[package]
        current_ver = pkg.current_ver

    return apt_pkg.version_compare(current_ver.ver_str, revno)


@cached
def arch():
    """Return the package architecture as a string.

    :returns: the architecture
    :rtype: str
    :raises: subprocess.CalledProcessError if dpkg command fails
    """
    return subprocess.check_output(
        ['dpkg', '--print-architecture']
    ).rstrip().decode('UTF-8')
