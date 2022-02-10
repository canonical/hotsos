# Copyright 2016-2019 Canonical Ltd.
#
# This file is part of the Snap layer for Juju.
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
"""
charms.reactive helpers for dealing with Snap packages.
"""
from collections import OrderedDict
from distutils.version import LooseVersion
import os.path
from os import uname
import shutil
import subprocess
from textwrap import dedent
import time
from urllib.request import urlretrieve

from charmhelpers.core import hookenv, host
from charmhelpers.core.hookenv import ERROR
from charmhelpers.core.host import write_file
from charms import layer
from charms import reactive
from charms.layer import snap
from charms.reactive import register_trigger, when, when_not, toggle_flag
from charms.reactive.helpers import data_changed


class UnsatisfiedMinimumVersionError(Exception):
    def __init__(self, desired, actual):
        super().__init__()
        self.desired = desired
        self.actual = actual

    def __str__(self):
        return "Could not install snapd >= {0.desired}, got {0.actual}".format(self)


class InvalidBundleError(Exception):
    pass


def sorted_snap_opts():
    opts = layer.options("snap")
    opts = sorted(opts.items(), key=lambda item: item[0] != "core")
    opts = OrderedDict(opts)
    return opts


def install():
    # Do nothing if we don't have kernel support yet
    if not kernel_supported():
        return

    opts = sorted_snap_opts()
    # supported-architectures is EXPERIMENTAL and undocumented.
    # It probably should live in the base layer, blocking the charm
    # during bootstrap if the arch is unsupported.
    arch = uname().machine
    for snapname, snap_opts in opts.items():
        supported_archs = snap_opts.pop("supported-architectures", None)
        if supported_archs and arch not in supported_archs:
            # Note that this does *not* error. The charm will need to
            # cope with the snaps it requested never getting installed,
            # likely by doing its own check on supported-architectures.
            hookenv.log(
                "Snap {} not supported on {!r} architecture" "".format(snapname, arch),
                ERROR,
            )
            continue
        installed_flag = "snap.installed.{}".format(snapname)
        if not reactive.is_flag_set(installed_flag):
            snap.install(snapname, **snap_opts)
    if data_changed("snap.install.opts", opts):
        snap.connect_all()


def check_refresh_available():
    # Do nothing if we don't have kernel support yet
    if not kernel_supported():
        return

    available_refreshes = snap.get_available_refreshes()
    for snapname in snap.get_installed_snaps():
        toggle_flag(snap.get_refresh_available_flag(snapname), snapname in available_refreshes)


def refresh():
    # Do nothing if we don't have kernel support yet
    if not kernel_supported():
        return

    opts = sorted_snap_opts()
    # supported-architectures is EXPERIMENTAL and undocumented.
    # It probably should live in the base layer, blocking the charm
    # during bootstrap if the arch is unsupported.
    arch = uname()[4]
    check_refresh_available()
    for snapname, snap_opts in opts.items():
        supported_archs = snap_opts.pop("supported-architectures", None)
        if supported_archs and arch not in supported_archs:
            continue
        snap.refresh(snapname, **snap_opts)
    snap.connect_all()


@reactive.hook("upgrade-charm")
def upgrade_charm():
    refresh()


def get_series():
    return subprocess.check_output(["lsb_release", "-sc"], universal_newlines=True).strip()


def snapd_supported():
    # snaps are not supported in trusty lxc containers.
    if get_series() == "trusty" and host.is_container():
        return False
    return True  # For all other cases, assume true.


def kernel_supported():
    kernel_version = uname().release

    if LooseVersion(kernel_version) < LooseVersion("4.4"):
        hookenv.log(
            "Snaps do not work on kernel {}, a reboot "
            "into a supported kernel (>4.4) is required"
            "".format(kernel_version)
        )
        return False
    return True


def ensure_snapd():
    if not snapd_supported():
        hookenv.log("Snaps do not work in this environment", hookenv.ERROR)
        raise Exception("Snaps do not work in this environment")

    # I don't use the apt layer, because that would tie this layer
    # too closely to apt packaging. Perhaps this is a snap-only system.
    if not shutil.which("snap"):
        os.environ["DEBIAN_FRONTEND"] = "noninteractive"
        cmd = ["apt-get", "install", "-y", "snapd"]
        # LP:1699986: Force install of systemd on Trusty.
        if get_series() == "trusty":
            cmd.append("systemd")
        subprocess.check_call(cmd, universal_newlines=True)

    # Work around lp:1628289. Remove this stanza once snapd depends
    # on the necessary package and snaps work in lxd xenial containers
    # without the workaround.
    if host.is_container() and not shutil.which("squashfuse"):
        os.environ["DEBIAN_FRONTEND"] = "noninteractive"
        cmd = ["apt-get", "install", "-y", "squashfuse", "fuse"]
        subprocess.check_call(cmd, universal_newlines=True)


def proxy_settings():
    proxy_vars = ("http_proxy", "https_proxy")
    proxy_env = {key: value for key, value in os.environ.items() if key in proxy_vars}

    snap_proxy = hookenv.config().get("snap_proxy")
    if snap_proxy:
        proxy_env["http_proxy"] = snap_proxy
        proxy_env["https_proxy"] = snap_proxy
    return proxy_env


def update_snap_proxy():
    # Do nothing if we don't have kernel support yet
    if not kernel_supported():
        return

    # This is a hack based on
    # https://bugs.launchpad.net/layer-snap/+bug/1533899/comments/1
    # Do it properly when Bug #1533899 is addressed.
    # Note we can't do this in a standard reactive handler as we need
    # to ensure proxies are configured before attempting installs or
    # updates.
    proxy = proxy_settings()

    override_dir = "/etc/systemd/system/snapd.service.d"
    path = os.path.join(override_dir, "snap_layer_proxy.conf")
    if not proxy and not os.path.exists(path):
        return  # No proxy asked for and proxy never configured.

    # It seems we cannot rely on this directory existing, so manually
    # create it.
    if not os.path.exists(override_dir):
        host.mkdir(override_dir, perms=0o755)

    if not data_changed("snap.proxy", proxy):
        return  # Short circuit avoids unnecessary restarts.

    if proxy:
        create_snap_proxy_conf(path, proxy)
    else:
        remove_snap_proxy_conf(path)
    subprocess.check_call(["systemctl", "daemon-reload"], universal_newlines=True)
    time.sleep(2)
    subprocess.check_call(["systemctl", "restart", "snapd.service"], universal_newlines=True)


def create_snap_proxy_conf(path, proxy):
    host.mkdir(os.path.dirname(path))
    content = dedent(
        """\
                        # Managed by Juju
                        [Service]
                        """
    )
    for proxy_key, proxy_value in proxy.items():
        content += "Environment={}={}\n".format(proxy_key, proxy_value)
    host.write_file(path, content.encode())


def remove_snap_proxy_conf(path):
    if os.path.exists(path):
        os.remove(path)


def ensure_path():
    # Per Bug #1662856, /snap/bin may be missing from $PATH. Fix this.
    if "/snap/bin" not in os.environ["PATH"].split(":"):
        os.environ["PATH"] += ":/snap/bin"


def _get_snapd_version():
    stdout = subprocess.check_output(["snap", "version"], stdin=subprocess.DEVNULL, universal_newlines=True)
    version_info = dict(line.split(None, 1) for line in stdout.splitlines())
    return LooseVersion(version_info["snapd"])


PREFERENCES = """\
Package: *
Pin: release a={}-proposed
Pin-Priority: 400
"""


def ensure_snapd_min_version(min_version):
    snapd_version = _get_snapd_version()
    if snapd_version < LooseVersion(min_version):
        from charmhelpers.fetch import add_source, apt_update, apt_install

        # Temporary until LP:1735344 lands
        add_source("distro-proposed", fail_invalid=True)
        distro = get_series()
        # disable proposed by default, needs to explicit
        write_file(
            "/etc/apt/preferences.d/proposed",
            PREFERENCES.format(distro),
        )
        apt_update()
        # explicitly install snapd from proposed
        apt_install("snapd/{}-proposed".format(distro))
        snapd_version = _get_snapd_version()
        if snapd_version < LooseVersion(min_version):
            hookenv.log("Failed to install snapd >= {}".format(min_version), ERROR)
            raise UnsatisfiedMinimumVersionError(min_version, snapd_version)


def download_assertion_bundle(proxy_url):
    """Download proxy assertion bundle and store id"""
    assertions_url = "{}/v2/auth/store/assertions".format(proxy_url)
    local_bundle, headers = urlretrieve(assertions_url)
    store_id = headers["X-Assertion-Store-Id"]
    return local_bundle, store_id


def configure_snap_store_proxy():
    # Do nothing if we don't have kernel support yet
    if not kernel_supported():
        return

    if not reactive.is_flag_set("config.changed.snap_proxy_url"):
        return
    config = hookenv.config()
    if "snap_proxy_url" not in config:
        # The deprecated snap_proxy_url config items have been removed
        # from config.yaml. If the charm author hasn't added them back
        # explicitly, there is nothing to do. Juju is maintaining these
        # settings as model configuration.
        return
    snap_store_proxy_url = config.get("snap_proxy_url")
    if not snap_store_proxy_url and not config.previous("snap_proxy_url"):
        # Proxy url is not set, and was not set previous hook. Do nothing,
        # to avoid overwriting the Juju maintained setting.
        return
    ensure_snapd_min_version("2.30")
    if snap_store_proxy_url:
        bundle, store_id = download_assertion_bundle(snap_store_proxy_url)
        try:
            subprocess.check_output(
                ["snap", "ack", bundle],
                stdin=subprocess.DEVNULL,
                universal_newlines=True,
            )
        except subprocess.CalledProcessError as e:
            raise InvalidBundleError("snapd could not ack the proxy assertion: " + e.output)
    else:
        store_id = ""

    try:
        subprocess.check_output(
            ["snap", "set", "core", "proxy.store={}".format(store_id)],
            stdin=subprocess.DEVNULL,
            universal_newlines=True,
        )
    except subprocess.CalledProcessError as e:
        raise InvalidBundleError("Proxy ID from header did not match store assertion: " + e.output)


register_trigger(when="config.changed.snapd_refresh", clear_flag="snap.refresh.set")


@when_not("snap.refresh.set")
@when("snap.installed.core")
def change_snapd_refresh():
    """Set the system refresh.timer option"""
    ensure_snapd_min_version("2.31")
    timer = hookenv.config()["snapd_refresh"]
    was_set = reactive.is_flag_set("snap.refresh.was-set")
    if timer or was_set:
        snap.set_refresh_timer(timer)
    reactive.toggle_flag("snap.refresh.was-set", timer)
    reactive.set_flag("snap.refresh.set")


# Bootstrap. We don't use standard reactive handlers to ensure that
# everything is bootstrapped before any charm handlers are run.
hookenv.atstart(hookenv.log, "Initializing Snap Layer")
hookenv.atstart(ensure_snapd)
hookenv.atstart(ensure_path)
hookenv.atstart(update_snap_proxy)
hookenv.atstart(configure_snap_store_proxy)
hookenv.atstart(install)
