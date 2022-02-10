import os
import sys
import re
import shutil
from distutils.version import LooseVersion
from pkg_resources import Requirement
from glob import glob
from subprocess import check_call, check_output, CalledProcessError
from time import sleep

from charms import layer
from charms.layer.execd import execd_preinstall


def _get_subprocess_env():
    env = os.environ.copy()
    env['LANG'] = env.get('LANG', 'C.UTF-8')
    return env


def get_series():
    """
    Return series for a few known OS:es.
    Tested as of 2019 november:
    * centos6, centos7, rhel6.
    * bionic
    """
    series = ""

    # Looking for content in /etc/os-release
    # works for ubuntu + some centos
    if os.path.isfile('/etc/os-release'):
        d = {}
        with open('/etc/os-release', 'r') as rel:
            for l in rel:
                if not re.match(r'^\s*$', l):
                    k, v = l.split('=')
                    d[k.strip()] = v.strip().replace('"', '')
            series = "{ID}{VERSION_ID}".format(**d)

    # Looking for content in /etc/redhat-release
    # works for redhat enterprise systems
    elif os.path.isfile('/etc/redhat-release'):
        with open('/etc/redhat-release', 'r') as redhatlsb:
            # CentOS Linux release 7.7.1908 (Core)
            line = redhatlsb.readline()
            release = int(line.split("release")[1].split()[0][0])
            series = "centos" + str(release)

    # Looking for content in /etc/lsb-release
    # works for ubuntu
    elif os.path.isfile('/etc/lsb-release'):
        d = {}
        with open('/etc/lsb-release', 'r') as lsb:
            for l in lsb:
                k, v = l.split('=')
                d[k.strip()] = v.strip()
            series = d['DISTRIB_CODENAME']

    # This is what happens if we cant figure out the OS.
    else:
        series = "unknown"
    return series


def bootstrap_charm_deps():
    """
    Set up the base charm dependencies so that the reactive system can run.
    """
    # execd must happen first, before any attempt to install packages or
    # access the network, because sites use this hook to do bespoke
    # configuration and install secrets so the rest of this bootstrap
    # and the charm itself can actually succeed. This call does nothing
    # unless the operator has created and populated $JUJU_CHARM_DIR/exec.d.
    execd_preinstall()
    # ensure that $JUJU_CHARM_DIR/bin is on the path, for helper scripts

    series = get_series()

    # OMG?! is build-essentials needed?
    ubuntu_packages = ['python3-pip',
                       'python3-setuptools',
                       'python3-yaml',
                       'python3-dev',
                       'python3-wheel',
                       'build-essential']

    # I'm not going to "yum group info "Development Tools"
    # omitting above madness
    centos_packages = ['python3-pip',
                       'python3-setuptools',
                       'python3-devel',
                       'python3-wheel']

    packages_needed = []
    if 'centos' in series:
        packages_needed = centos_packages
    else:
        packages_needed = ubuntu_packages

    charm_dir = os.environ['JUJU_CHARM_DIR']
    os.environ['PATH'] += ':%s' % os.path.join(charm_dir, 'bin')
    venv = os.path.abspath('../.venv')
    vbin = os.path.join(venv, 'bin')
    vpip = os.path.join(vbin, 'pip')
    vpy = os.path.join(vbin, 'python')
    hook_name = os.path.basename(sys.argv[0])
    is_bootstrapped = os.path.exists('wheelhouse/.bootstrapped')
    is_charm_upgrade = hook_name == 'upgrade-charm'
    is_series_upgrade = hook_name == 'post-series-upgrade'
    is_post_upgrade = os.path.exists('wheelhouse/.upgraded')
    is_upgrade = (not is_post_upgrade and
                  (is_charm_upgrade or is_series_upgrade))
    if is_bootstrapped and not is_upgrade:
        # older subordinates might have downgraded charm-env, so we should
        # restore it if necessary
        install_or_update_charm_env()
        activate_venv()
        # the .upgrade file prevents us from getting stuck in a loop
        # when re-execing to activate the venv; at this point, we've
        # activated the venv, so it's safe to clear it
        if is_post_upgrade:
            os.unlink('wheelhouse/.upgraded')
        return
    if os.path.exists(venv):
        try:
            # focal installs or upgrades prior to PR 160 could leave the venv
            # in a broken state which would prevent subsequent charm upgrades
            _load_installed_versions(vpip)
        except CalledProcessError:
            is_broken_venv = True
        else:
            is_broken_venv = False
        if is_upgrade or is_broken_venv:
            # All upgrades should do a full clear of the venv, rather than
            # just updating it, to bring in updates to Python itself
            shutil.rmtree(venv)
    if is_upgrade:
        if os.path.exists('wheelhouse/.bootstrapped'):
            os.unlink('wheelhouse/.bootstrapped')
    # bootstrap wheelhouse
    if os.path.exists('wheelhouse'):
        pre_eoan = series in ('ubuntu12.04', 'precise',
                              'ubuntu14.04', 'trusty',
                              'ubuntu16.04', 'xenial',
                              'ubuntu18.04', 'bionic')
        pydistutils_lines = [
            "[easy_install]\n",
            "find_links = file://{}/wheelhouse/\n".format(charm_dir),
            "no_index=True\n",
            "index_url=\n",   # deliberately nothing here; disables it.
        ]
        if pre_eoan:
            pydistutils_lines.append("allow_hosts = ''\n")
        with open('/root/.pydistutils.cfg', 'w') as fp:
            # make sure that easy_install also only uses the wheelhouse
            # (see https://github.com/pypa/pip/issues/410)
            fp.writelines(pydistutils_lines)
        if 'centos' in series:
            yum_install(packages_needed)
        else:
            apt_install(packages_needed)
        from charms.layer import options
        cfg = options.get('basic')
        # include packages defined in layer.yaml
        if 'centos' in series:
            yum_install(cfg.get('packages', []))
        else:
            apt_install(cfg.get('packages', []))
        # if we're using a venv, set it up
        if cfg.get('use_venv'):
            if not os.path.exists(venv):
                series = get_series()
                if series in ('ubuntu12.04', 'precise',
                              'ubuntu14.04', 'trusty'):
                    apt_install(['python-virtualenv'])
                elif 'centos' in series:
                    yum_install(['python-virtualenv'])
                else:
                    apt_install(['virtualenv'])
                cmd = ['virtualenv', '-ppython3', '--never-download', venv]
                if cfg.get('include_system_packages'):
                    cmd.append('--system-site-packages')
                check_call(cmd, env=_get_subprocess_env())
            os.environ['PATH'] = ':'.join([vbin, os.environ['PATH']])
            pip = vpip
        else:
            pip = 'pip3'
            # save a copy of system pip to prevent `pip3 install -U pip`
            # from changing it
            if os.path.exists('/usr/bin/pip'):
                shutil.copy2('/usr/bin/pip', '/usr/bin/pip.save')
        pre_install_pkgs = ['pip', 'setuptools', 'setuptools-scm']
        # we bundle these packages to work around bugs in older versions (such
        # as https://github.com/pypa/pip/issues/56), but if the system already
        # provided a newer version, downgrading it can cause other problems
        _update_if_newer(pip, pre_install_pkgs)
        # install the rest of the wheelhouse deps (extract the pkg names into
        # a set so that we can ignore the pre-install packages and let pip
        # choose the best version in case there are multiple from layer
        # conflicts)
        _versions = _load_wheelhouse_versions()
        _pkgs = _versions.keys() - set(pre_install_pkgs)
        # add back the versions such that each package in pkgs is
        # <package_name>==<version>.
        # This ensures that pip 20.3.4+ will install the packages from the
        # wheelhouse without (erroneously) flagging an error.
        pkgs = _add_back_versions(_pkgs, _versions)
        reinstall_flag = '--force-reinstall'
        if not cfg.get('use_venv', True) and pre_eoan:
            reinstall_flag = '--ignore-installed'
        check_call([pip, 'install', '-U', reinstall_flag, '--no-index',
                    '--no-cache-dir', '-f', 'wheelhouse'] + list(pkgs),
                   env=_get_subprocess_env())
        # re-enable installation from pypi
        os.remove('/root/.pydistutils.cfg')

        # install pyyaml for centos7, since, unlike the ubuntu image, the
        # default image for centos doesn't include pyyaml; see the discussion:
        # https://discourse.jujucharms.com/t/charms-for-centos-lets-begin
        if 'centos' in series:
            check_call([pip, 'install', '-U', 'pyyaml'],
                       env=_get_subprocess_env())

        # install python packages from layer options
        if cfg.get('python_packages'):
            check_call([pip, 'install', '-U'] + cfg.get('python_packages'),
                       env=_get_subprocess_env())
        if not cfg.get('use_venv'):
            # restore system pip to prevent `pip3 install -U pip`
            # from changing it
            if os.path.exists('/usr/bin/pip.save'):
                shutil.copy2('/usr/bin/pip.save', '/usr/bin/pip')
                os.remove('/usr/bin/pip.save')
        # setup wrappers to ensure envs are used for scripts
        install_or_update_charm_env()
        for wrapper in ('charms.reactive', 'charms.reactive.sh',
                        'chlp', 'layer_option'):
            src = os.path.join('/usr/local/sbin', 'charm-env')
            dst = os.path.join('/usr/local/sbin', wrapper)
            if not os.path.exists(dst):
                os.symlink(src, dst)
        if cfg.get('use_venv'):
            shutil.copy2('bin/layer_option', vbin)
        else:
            shutil.copy2('bin/layer_option', '/usr/local/bin/')
        # re-link the charm copy to the wrapper in case charms
        # call bin/layer_option directly (as was the old pattern)
        os.remove('bin/layer_option')
        os.symlink('/usr/local/sbin/layer_option', 'bin/layer_option')
        # flag us as having already bootstrapped so we don't do it again
        open('wheelhouse/.bootstrapped', 'w').close()
        if is_upgrade:
            # flag us as having already upgraded so we don't do it again
            open('wheelhouse/.upgraded', 'w').close()
        # Ensure that the newly bootstrapped libs are available.
        # Note: this only seems to be an issue with namespace packages.
        # Non-namespace-package libs (e.g., charmhelpers) are available
        # without having to reload the interpreter. :/
        reload_interpreter(vpy if cfg.get('use_venv') else sys.argv[0])


def _load_installed_versions(pip):
    pip_freeze = check_output([pip, 'freeze']).decode('utf8')
    versions = {}
    for pkg_ver in pip_freeze.splitlines():
        try:
            req = Requirement.parse(pkg_ver)
        except ValueError:
            continue
        versions.update({
            req.project_name: LooseVersion(ver)
            for op, ver in req.specs if op == '=='
        })
    return versions


def _load_wheelhouse_versions():
    versions = {}
    for wheel in glob('wheelhouse/*'):
        pkg, ver = os.path.basename(wheel).rsplit('-', 1)
        # nb: LooseVersion ignores the file extension
        versions[pkg.replace('_', '-')] = LooseVersion(ver)
    return versions


def _add_back_versions(pkgs, versions):
    """Add back the version strings to each of the packages.

    The versions are LooseVersion() from _load_wheelhouse_versions().  This
    function strips the ".zip" or ".tar.gz" from the end of the version string
    and adds it back to the package in the form of <package_name>==<version>

    If a package name is not a key in the versions dictionary, then it is
    returned in the list unchanged.

    :param pkgs: A list of package names
    :type pkgs: List[str]
    :param versions: A map of package to LooseVersion
    :type versions: Dict[str, LooseVersion]
    :returns: A list of (maybe) versioned packages
    :rtype: List[str]
    """
    def _strip_ext(s):
        """Strip an extension (if it exists) from the string

        :param s: the string to strip an extension off if it exists
        :type s: str
        :returns: string without an extension of .zip or .tar.gz
        :rtype: str
        """
        for ending in [".zip", ".tar.gz"]:
            if s.endswith(ending):
                return s[:-len(ending)]
        return s

    def _maybe_add_version(pkg):
        """Maybe add back the version number to a package if it exists.

        Adds the version number, if the package exists in the lexically
        captured `versions` dictionary, in the form <pkg>==<version>.  Strips
        the extension if it exists.

        :param pkg: the package name to (maybe) add the version number to.
        :type pkg: str
        """
        try:
            return "{}=={}".format(pkg, _strip_ext(str(versions[pkg])))
        except KeyError:
            pass
        return pkg

    return [_maybe_add_version(pkg) for pkg in pkgs]


def _update_if_newer(pip, pkgs):
    installed = _load_installed_versions(pip)
    wheelhouse = _load_wheelhouse_versions()
    for pkg in pkgs:
        if pkg not in installed or wheelhouse[pkg] > installed[pkg]:
            check_call([pip, 'install', '-U', '--no-index', '-f', 'wheelhouse',
                        pkg], env=_get_subprocess_env())


def install_or_update_charm_env():
    # On Trusty python3-pkg-resources is not installed
    try:
        from pkg_resources import parse_version
    except ImportError:
        apt_install(['python3-pkg-resources'])
        from pkg_resources import parse_version

    try:
        installed_version = parse_version(
            check_output(['/usr/local/sbin/charm-env',
                          '--version']).decode('utf8'))
    except (CalledProcessError, FileNotFoundError):
        installed_version = parse_version('0.0.0')
    try:
        bundled_version = parse_version(
            check_output(['bin/charm-env',
                          '--version']).decode('utf8'))
    except (CalledProcessError, FileNotFoundError):
        bundled_version = parse_version('0.0.0')
    if installed_version < bundled_version:
        shutil.copy2('bin/charm-env', '/usr/local/sbin/')


def activate_venv():
    """
    Activate the venv if enabled in ``layer.yaml``.

    This is handled automatically for normal hooks, but actions might
    need to invoke this manually, using something like:

        # Load modules from $JUJU_CHARM_DIR/lib
        import sys
        sys.path.append('lib')

        from charms.layer.basic import activate_venv
        activate_venv()

    This will ensure that modules installed in the charm's
    virtual environment are available to the action.
    """
    from charms.layer import options
    venv = os.path.abspath('../.venv')
    vbin = os.path.join(venv, 'bin')
    vpy = os.path.join(vbin, 'python')
    use_venv = options.get('basic', 'use_venv')
    if use_venv and '.venv' not in sys.executable:
        # activate the venv
        os.environ['PATH'] = ':'.join([vbin, os.environ['PATH']])
        reload_interpreter(vpy)
    layer.patch_options_interface()
    layer.import_layer_libs()


def reload_interpreter(python):
    """
    Reload the python interpreter to ensure that all deps are available.

    Newly installed modules in namespace packages sometimes seemt to
    not be picked up by Python 3.
    """
    os.execve(python, [python] + list(sys.argv), os.environ)


def apt_install(packages):
    """
    Install apt packages.

    This ensures a consistent set of options that are often missed but
    should really be set.
    """
    if isinstance(packages, (str, bytes)):
        packages = [packages]

    env = _get_subprocess_env()

    if 'DEBIAN_FRONTEND' not in env:
        env['DEBIAN_FRONTEND'] = 'noninteractive'

    cmd = ['apt-get',
           '--option=Dpkg::Options::=--force-confold',
           '--assume-yes',
           'install']
    for attempt in range(3):
        try:
            check_call(cmd + packages, env=env)
        except CalledProcessError:
            if attempt == 2:  # third attempt
                raise
            try:
                # sometimes apt-get update needs to be run
                check_call(['apt-get', 'update'], env=env)
            except CalledProcessError:
                # sometimes it's a dpkg lock issue
                pass
            sleep(5)
        else:
            break


def yum_install(packages):
    """ Installs packages with yum.
        This function largely  mimics the apt_install function for consistency.
    """
    if packages:
        env = os.environ.copy()
        cmd = ['yum', '-y', 'install']
        for attempt in range(3):
            try:
                check_call(cmd + packages, env=env)
            except CalledProcessError:
                if attempt == 2:
                    raise
                try:
                    check_call(['yum', 'update'], env=env)
                except CalledProcessError:
                    pass
                sleep(5)
            else:
                break
    else:
        pass


def init_config_states():
    import yaml
    from charmhelpers.core import hookenv
    from charms.reactive import set_state
    from charms.reactive import toggle_state
    config = hookenv.config()
    config_defaults = {}
    config_defs = {}
    config_yaml = os.path.join(hookenv.charm_dir(), 'config.yaml')
    if os.path.exists(config_yaml):
        with open(config_yaml) as fp:
            config_defs = yaml.safe_load(fp).get('options', {})
            config_defaults = {key: value.get('default')
                               for key, value in config_defs.items()}
    for opt in config_defs.keys():
        if config.changed(opt):
            set_state('config.changed')
            set_state('config.changed.{}'.format(opt))
        toggle_state('config.set.{}'.format(opt), config.get(opt))
        toggle_state('config.default.{}'.format(opt),
                     config.get(opt) == config_defaults[opt])


def clear_config_states():
    from charmhelpers.core import hookenv, unitdata
    from charms.reactive import remove_state
    config = hookenv.config()
    remove_state('config.changed')
    for opt in config.keys():
        remove_state('config.changed.{}'.format(opt))
        remove_state('config.set.{}'.format(opt))
        remove_state('config.default.{}'.format(opt))
    unitdata.kv().flush()
