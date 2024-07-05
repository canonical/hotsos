import abc
from datetime import datetime
import os
import re
from functools import cached_property

from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers.cli import CLIHelper, CmdBase
from hotsos.core.host_helpers import (
    APTPackageHelper,
    DockerImageHelper,
    DPKGVersion,
    PebbleHelper,
    SystemdHelper,
    SSLCertificate,
    SSLCertificatesHelper,
)
from hotsos.core.log import log
from hotsos.core.plugins.openstack.openstack import (
    OSTProjectCatalog,
    OST_EOL_INFO,
    OST_REL_INFO,
)
from hotsos.core.plugins.openstack.neutron import NeutronBase
from hotsos.core.plugins.openstack.nova import NovaBase
from hotsos.core.plugins.openstack.octavia import OctaviaBase
from hotsos.core import plugintools
from hotsos.core.ycheck.events import EventHandlerBase, EventCallbackBase


class OpenstackBase():

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.nova = NovaBase()
        self.neutron = NeutronBase()
        self.octavia = OctaviaBase()
        self.certificate_expire_days = 60
        self.ost_projects = OSTProjectCatalog()
        service_exprs = self.ost_projects.service_exprs
        self.pebble = PebbleHelper(service_exprs=service_exprs)
        self.systemd = SystemdHelper(service_exprs=service_exprs)
        self.apt = APTPackageHelper(
                       core_pkgs=self.ost_projects.packages_core_exprs,
                       other_pkgs=self.ost_projects.packages_dep_exprs)
        self.docker = DockerImageHelper(
                          core_pkgs=self.ost_projects.packages_core_exprs,
                          other_pkgs=self.ost_projects.packages_dep_exprs)

    @cached_property
    def apt_source_path(self):
        return os.path.join(HotSOSConfig.data_root, 'etc/apt/sources.list.d')

    @cached_property
    def installed_pkg_release_names(self):
        """
        Get release name for each installed package that we are tracking and
        return as a list of names. The list should normally have length 1.
        """
        relnames = set()
        for pkg, values in OST_REL_INFO.items():
            if pkg in self.apt.core:
                # Since the versions we match against will always match our
                # version - 1 we use last known lt as current version.
                v_lt = None
                r_lt = None
                pkg_ver = DPKGVersion(self.apt.core[pkg])
                for rel, ver in values.items():
                    if pkg_ver > ver:
                        if v_lt is None:
                            v_lt = ver
                            r_lt = rel
                        elif ver > DPKGVersion(v_lt):
                            v_lt = ver
                            r_lt = rel

                if r_lt:
                    relnames.add(r_lt)

        log.debug("release name(s) found: %s", ','.join(relnames))
        return list(relnames)

    @cached_property
    def release_name(self):
        relnames = self.installed_pkg_release_names
        if relnames:
            if len(relnames) > 1:
                log.warning("Openstack packages from more than one release "
                            "identified: %s", relnames)

            # expect one, if there are more that should be covered by a
            # scenario check.
            return relnames[0]

        relpath = os.path.join(HotSOSConfig.data_root,
                               'etc/openstack-release')
        # this exists as of Jammy/Yoga
        if os.path.exists(relpath):
            with open(relpath) as fd:
                return fd.read().partition('=')[2].strip()

        relname = 'unknown'
        # fallback to uca version if exists
        if not os.path.exists(self.apt_source_path):
            return relname

        release_info = {}
        for source in os.listdir(self.apt_source_path):
            apt_path = os.path.join(self.apt_source_path, source)
            for line in CmdBase.safe_readlines(apt_path):
                rexpr = r'deb .+ubuntu-cloud.+ [a-z]+-([a-z]+)/([a-z]+) .+'
                ret = re.compile(rexpr).match(line)
                if ret:
                    if 'uca' not in release_info:
                        release_info['uca'] = set()

                    if ret[1] != 'updates':
                        release_info['uca'].add(f"{ret[2]}-{ret[1]}")
                    else:
                        release_info['uca'].add(ret[2])

        if release_info.get('uca'):
            return sorted(release_info['uca'], reverse=True)[0]

        return relname

    @cached_property
    def days_to_eol(self):
        if self.release_name != 'unknown':
            eol = OST_EOL_INFO.get(self.release_name)
            if eol is not None:
                today = datetime.utcfromtimestamp(int(CLIHelper().date()))
                delta = (eol - today).days
                return delta

        log.warning("unable to determine eol info for release "
                    "name '%s' - assuming 0 days left", self.release_name)
        return 0

    @property
    def bind_interfaces(self):
        """
        Fetch interfaces used by Openstack services and return dict.
        """
        interfaces = {}

        ifaces = self.nova.bind_interfaces
        if ifaces:
            interfaces.update(ifaces)

        ifaces = self.neutron.bind_interfaces
        if ifaces:
            interfaces.update(ifaces)

        ifaces = self.octavia.bind_interfaces
        if ifaces:
            interfaces.update(ifaces)

        return interfaces

    @cached_property
    def unexpected_masked_services(self):
        """
        Return a list of identified masked services with any services that we
        expect to be masked filtered out.
        """
        masked = set(self.systemd.masked_services)
        if not masked:
            return []

        expected_masked = self.ost_projects.default_masked_services
        return sorted(list(masked.difference(expected_masked)))

    @cached_property
    def openstack_installed(self):
        if self.apt.core:
            return True

        return False

    @cached_property
    def apache2_ssl_config_file(self):
        return os.path.join(HotSOSConfig.data_root,
                            'etc/apache2/sites-enabled',
                            'openstack_https_frontend.conf')

    @cached_property
    def ssl_enabled(self):
        return os.path.exists(self.apache2_ssl_config_file)

    @cached_property
    def _apache2_certificates(self):
        """ Returns list of ssl cert paths relative to data_root. """
        certificate_paths = []
        if not self.ssl_enabled:
            return certificate_paths

        with open(self.apache2_ssl_config_file) as fd:
            for line in fd:
                ret = re.search(r'SSLCertificateFile /(\S+)', line)
                if ret:
                    path = ret.group(1)
                    if path not in certificate_paths:
                        certificate_paths.append(path)

            return certificate_paths

    @cached_property
    def apache2_certificates_expiring(self):
        apache2_certificates_expiring = []
        max_days = self.certificate_expire_days
        for path in self._apache2_certificates:
            try:
                ssl_checks = SSLCertificatesHelper(SSLCertificate(path),
                                                   max_days)
            except OSError:
                log.info("cert path not found: %s", path)
                continue

            if ssl_checks.certificate_expires_soon:
                apache2_certificates_expiring.append(path)

        return apache2_certificates_expiring

    @cached_property
    def apache2_allow_encoded_slashes_on(self):
        """ Returns True if AllowEncodedSlashes On is found. """
        if not self.ssl_enabled:
            return False

        with open(self.apache2_ssl_config_file) as fd:
            for line in fd:
                if line.strip().startswith('#'):
                    continue

                ret = re.search(r'[Aa]llow[Ee]ncoded[Ss]lashes\s+[Oo]n', line)
                if ret:
                    return True
        return False


class OpenstackChecksBase(OpenstackBase, plugintools.PluginPartBase):
    plugin_name = "openstack"
    plugin_root_index = 4

    @property
    def plugin_runnable(self):
        return self.openstack_installed


class OpenstackEventCallbackBase(OpenstackBase, EventCallbackBase):

    @classmethod
    def global_event_tally_time_granularity_override(cls):
        return True

    @abc.abstractmethod
    def __call__(self):
        """ Callback method. """


class OpenstackEventHandlerBase(OpenstackChecksBase, EventHandlerBase):
    pass
