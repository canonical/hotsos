from datetime import datetime
import os
import re

from hotsos.core.utils import cached_property
from hotsos.core.config import HotSOSConfig
from hotsos.core.plugins.openstack.openstack import (
    OSTProjectCatalog,
    OST_EOL_INFO,
    OST_REL_INFO,
)
from hotsos.core.log import log
from hotsos.core import plugintools
from hotsos.core.plugins.openstack.nova import NovaBase
from hotsos.core.plugins.openstack.neutron import NeutronBase
from hotsos.core.plugins.openstack.octavia import OctaviaBase
from hotsos.core.ycheck.events import YEventCheckerBase
from hotsos.core.host_helpers.cli import CLIHelper, CmdBase
from hotsos.core.host_helpers import (
    APTPackageHelper,
    DockerImageHelper,
    DPKGVersionCompare,
    PebbleHelper,
    SystemdHelper,
    SSLCertificate,
    SSLCertificatesHelper,
)


class OpenstackBase(object):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.nova = NovaBase()
        self.neutron = NeutronBase()
        self.octavia = OctaviaBase()
        self.certificate_expire_days = 60

    @cached_property
    def apache2_ssl_config_file(self):
        return os.path.join(HotSOSConfig.data_root,
                            'etc/apache2/sites-enabled',
                            'openstack_https_frontend.conf')

    @cached_property
    def ssl_enabled(self):
        return os.path.exists(self.apache2_ssl_config_file)

    @cached_property
    def apache2_certificates_list(self):
        certificate_path_list = []
        certificate_list = []
        if self.ssl_enabled:
            try:
                with open(self.apache2_ssl_config_file) as fd:
                    for line in fd:
                        regex_match = re.search(r'SSLCertificateFile /(.*)',
                                                line)
                        if regex_match:
                            certificate_path = os.path.join(
                                               HotSOSConfig.data_root,
                                               regex_match.group(1))
                            if certificate_path not in certificate_path_list:
                                certificate_path_list.append(certificate_path)
            except OSError:
                log.debug("Unable to open apache2 configuration file %s",
                          self.apache2_ssl_config_file)
                return certificate_list

        if len(certificate_path_list) > 0:
            for certificate_path in certificate_path_list:
                try:
                    ssl_certificate = SSLCertificate(certificate_path)
                    certificate_list.append(ssl_certificate)
                except OSError:
                    continue

        return certificate_list

    @cached_property
    def apache2_certificates_expiring(self):
        apache2_certificates_expiring = []
        certificate_list = self.apache2_certificates_list
        for certificate in certificate_list:
            ssl_checks = SSLCertificatesHelper(certificate,
                                               self.certificate_expire_days)
            if ssl_checks.certificate_expires_soon:
                apache2_certificates_expiring.append(certificate.path)
        return apache2_certificates_expiring


class OpenstackChecksBase(OpenstackBase, plugintools.PluginPartBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
    def apt_packages_all(self):
        return self.apt.all

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
        for pkg in OST_REL_INFO:
            if pkg in self.apt.core:
                # Since the versions we match against will always match our
                # version - 1 we use last known lt as current version.
                v_lt = None
                r_lt = None
                pkg_ver = DPKGVersionCompare(self.apt.core[pkg])
                for rel, ver in OST_REL_INFO[pkg].items():
                    if pkg_ver > ver:
                        if v_lt is None:
                            v_lt = ver
                            r_lt = rel
                        elif ver > DPKGVersionCompare(v_lt):
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
                        release_info['uca'].add("{}-{}".format(ret[2], ret[1]))
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
            else:
                log.warning("unable to determine eol info for unknown release "
                            "name '%s'", self.release_name)

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
        return list(masked.difference(expected_masked))

    @cached_property
    def openstack_installed(self):
        if self.apt.core:
            return True

        return False

    @property
    def plugin_runnable(self):
        return self.openstack_installed


class OpenstackEventChecksBase(OpenstackChecksBase, YEventCheckerBase):
    """
    Normally we would call run_checks() here but the Openstack implementations
    do run() themselves so we defer.
    """

    def categorise_events(self, *args, **kwargs):
        if 'include_time' not in kwargs:
            include_time = HotSOSConfig.event_tally_granularity == 'time'
            kwargs['include_time'] = include_time

        return super().categorise_events(*args, **kwargs)
