import os
from datetime import datetime
from functools import cached_property

from hotsos.core.config import HotSOSConfig
from hotsos.core import host_helpers
from hotsos.core.log import log
from hotsos.core.plugins.openstack.exceptions import (
    EXCEPTIONS_COMMON,
    BARBICAN_EXCEPTIONS,
    CASTELLAN_EXCEPTIONS,
    CINDER_EXCEPTIONS,
    DESIGNATE_EXCEPTIONS,
    GLANCE_EXCEPTIONS,
    GLANCE_STORE_EXCEPTIONS,
    HEAT_EXCEPTIONS,
    KEYSTONE_EXCEPTIONS,
    MANILA_EXCEPTIONS,
    PLACEMENT_EXCEPTIONS,
    PYTHON_LIBVIRT_EXCEPTIONS,
    NOVA_EXCEPTIONS,
    NEUTRON_EXCEPTIONS,
    NEUTRONCLIENT_EXCEPTIONS,
    OCTAVIA_EXCEPTIONS,
    OS_VIF_EXCEPTIONS,
    OVSDBAPP_EXCEPTIONS,
    MASAKARI_EXCEPTIONS,
)


# NOTE(tpsilva): when updating this, refer to the Charmed Openstack supported
# versions page: https://ubuntu.com/openstack/docs/supported-versions
OST_EOL_INFO = {
    'caracal': datetime(2029, 4, 30),
    'bobcat': datetime(2025, 4, 30),
    'antelope': datetime(2026, 4, 30),
    'zed': datetime(2024, 4, 30),
    'yoga': datetime(2027, 4, 30),
    'xena': datetime(2023, 4, 30),
    'wallaby': datetime(2024, 4, 30),
    'victoria': datetime(2022, 4, 30),
    'ussuri': datetime(2030, 4, 30),
    'train': datetime(2021, 2, 28),
    'stein': datetime(2022, 4, 30),
    'rocky': datetime(2020, 2, 29),
    'queens': datetime(2028, 4, 30),
    'mitaka': datetime(2024, 4, 30)
}

# NOTE(dosaboy): Find package versions at:
# https://openstack-ci-reports.ubuntu.com/reports/cloud-archive/index.html
OST_REL_INFO = {
    'aodh-common': {
        'caracal': '1:18.0.0',
        'bobcat': '1:17.0.0',
        'antelope': '1:16.0.0',
        'zed': '1:15.0.0',
        'yoga': '1:14.0.0',
        'xena': '1:13.0.0',
        'wallaby': '1:12.0.0',
        'victoria': '11.0.0',
        'ussuri': '10.0.0',
        'train': '9.0.0',
        'stein': '8.0.0',
        'rocky': '7.0.0',
        'queens': '6.0.0'},
    'barbican-common': {
        'caracal': '2:18.0.0',
        'bobcat': '2:17.0.0',
        'antelope': '2:16.0.0',
        'zed': '2:15.0.0',
        'yoga': '2:14.0.0',
        'xena': '1:13.0.0',
        'wallaby': '1:12.0.0',
        'victoria': '1:11.0.0',
        'ussuri': '1:10.0.0',
        'train': '1:9.0.0',
        'stein': '1:8.0.0',
        'rocky': '1:7.0.0',
        'queens': '1:6.0.0'},
    'cinder-common': {
        'caracal': '2:24.0.0',
        'bobcat': '2:23.0.0',
        'antelope': '2:22.0.0',
        'zed': '2:21.0.0',
        'yoga': '2:20.0.0',
        'xena': '2:19.0.0',
        'wallaby': '2:18.0.0',
        'victoria': '2:17.0.0',
        'ussuri': '2:16.0.0',
        'train': '2:15.0.0',
        'stein': '2:14.0.0',
        'rocky': '2:13.0.0',
        'queens': '2:12.0.0'},
    'designate-common': {
        'caracal': '1:18.0.0',
        'bobcat': '1:17.0.0',
        'antelope': '1:16.0.0',
        'zed': '1:15.0.0',
        'yoga': '1:14.0.0',
        'xena': '1:13.0.0',
        'wallaby': '1:12.0.0',
        'victoria': '1:11.0.0',
        'ussuri': '1:10.0.0',
        'train': '1:9.0.0',
        'stein': '1:8.0.0',
        'rocky': '1:7.0.0',
        'queens': '1:6.0.0'},
    'glance-common': {
        'caracal': '2:28.0.1',
        'bobcat': '2:27.0.0',
        'antelope': '2:26.0.0',
        'zed': '2:25.0.0',
        'yoga': '2:24.0.0',
        'xena': '2:23.0.0',
        'wallaby': '2:22.0.0',
        'victoria': '2:21.0.0',
        'ussuri': '2:20.0.0',
        'train': '2:19.0.0',
        'stein': '2:18.0.0',
        'rocky': '2:17.0.0',
        'queens': '2:16.0.0'},
    'heat-common': {
        'caracal': '1:22.0.0',
        'bobcat': '1:21.0.0',
        'antelope': '1:20.0.0',
        'zed': '1:19.0.0',
        'yoga': '1:18.0.0',
        'xena': '1:17.0.0',
        'wallaby': '1:16.0.0',
        'victoria': '1:15.0.0',
        'ussuri': '1:14.0.0',
        'train': '1:13.0.0',
        'stein': '1:12.0.0',
        'rocky': '1:11.0.0',
        'queens': '1:10.0.0'},
    'ironic-common': {
        'caracal': '1:24.1.1',
        'bobcat': '1:23.0.0',
        'antelope': '1:21.2',
        'zed': '1:20.2.0',
        'yoga': '1:19.0.0'},
    'keystone': {
        'caracal': '2:25.0.0',
        'bobcat': '2:24.0.0',
        'antelope': '2:23.0.0',
        'zed': '2:22.0.0',
        'yoga': '2:21.0.0',
        'xena': '2:20.0.0',
        'wallaby': '2:19.0.0',
        'victoria': '2:18.0.0',
        'ussuri': '2:17.0.0',
        'train': '2:16.0.0',
        'stein': '2:15.0.0',
        'rocky': '2:14.0.0',
        'queens': '2:13.0.0',
        'pike': '2:12.0.0',
        'ocata': '2:11.0.0'},
    'masakari-common': {
        'caracal': '17.0.0',
        'bobcat': '16.0.0',
        'antelope': '15.0.0',
        'zed': '14.0.0',
        'yoga': '13.0.0',
        'xena': '12.0.0',
        'wallaby': '11.0.0',
        'victoria': '10.0.0',
        'ussuri': '9.0.0',
        'train': '8.0.0',
        'stein': '7.0.0',
        'rocky': '6.0.0'},
    'neutron-common': {
        'caracal': '2:24.0.0',
        'bobcat': '2:23.0.0',
        'antelope': '2:22.0.0',
        'zed': '2:21.0.0',
        'yoga': '2:20.0.0',
        'xena': '2:19.0.0',
        'wallaby': '2:18.0.0',
        'victoria': '2:17.0.0',
        'ussuri': '2:16.0.0',
        'train': '2:15.0.0',
        'stein': '2:14.0.0',
        'rocky': '2:13.0.0',
        'queens': '2:12.0.0',
        'pike': '2:11.0.0',
        'ocata': '2:10.0.0',
        'newton': '2:9.0.0',
        'mitaka': '2:8.0.0',
        'liberty': '2:7.0.0',
        'kilo': '1:2015.1.0',
        'juno': '1:2014.2.0',
        'icehouse': '1:2014.1.0'},
    'nova-common': {
        'caracal': '3:29.0.1',
        'bobcat': '3:28.0.0',
        'antelope': '3:27.0.0',
        'zed': '3:26.0.0',
        'yoga': '3:25.0.0',
        'xena': '3:24.0.0',
        'wallaby': '3:23.0.0',
        'victoria': '2:22.0.0',
        'ussuri': '2:21.0.0',
        'train': '2:20.0.0',
        'stein': '2:19.0.0',
        'rocky': '2:18.0.0',
        'queens': '2:17.0.0',
        'pike': '2:16.0.0',
        'ocata': '2:15.0.0',
        'newton': '2:14.0.0',
        'mitaka': '2:13.0.0',
        'liberty': '2:12.0.0',
        'kilo': '1:2015.1.0',
        'juno': '1:2014.2.0',
        'icehouse': '1:2014.1.0'},
    'octavia-common': {
        'caracal': '1:14.0.0',
        'bobcat': '1:13.0.0',
        'antelope': '1:12.0.0',
        'zed': '1:11.0.0',
        'yoga': '1:10.0.0',
        'xena': '1:9.0.0',
        'wallaby': '1:8.0.0',
        'victoria': '7.0.0',
        'ussuri': '6.0.0',
        'train': '5.0.0',
        'stein': '4.0.0',
        'rocky': '3.0.0'},
    'openstack-dashboard-common': {
        'caracal': '4:24.0.0',
        'bobcat': '4:23.3.0',
        'antelope': '4:23.1.0',
        'zed': '4:22.2.0',
        'yoga': '4:22.0.0',
        'xena': '4:20.0.0',
        'wallaby': '4:19.0.0',
        'victoria': '4:18.0.0',
        'ussuri': '3:18.0.0',
        'train': '3:16.0.0',
        'stein': '3:15.0.0',
        'rocky': '3:14.0.0',
        'queens': '3:13.0.0'},
    'placement-common': {
        'caracal': '1:11.0.0',
        'bobcat': '1:10.0.0',
        'antelope': '1:9.0.0',
        'zed': '1:8.0.0',
        'yoga': '1:7.0.0',
        'xena': '1:6.0.0',
        'wallaby': '1:5.0.0',
        'victoria': '4.0.0',
        'ussuri': '3.0.0',
        'train': '2.0.0',
        'stein': '1.0.0'}
}

OST_EXCEPTIONS = {'barbican': BARBICAN_EXCEPTIONS + CASTELLAN_EXCEPTIONS,
                  'cinder': CINDER_EXCEPTIONS + CASTELLAN_EXCEPTIONS,
                  'designate': DESIGNATE_EXCEPTIONS,
                  'glance': GLANCE_EXCEPTIONS + GLANCE_STORE_EXCEPTIONS,
                  'heat': HEAT_EXCEPTIONS,
                  'keystone': KEYSTONE_EXCEPTIONS,
                  'manila': MANILA_EXCEPTIONS,
                  'masakari': MASAKARI_EXCEPTIONS,
                  'neutron': NEUTRON_EXCEPTIONS + OVSDBAPP_EXCEPTIONS,
                  'nova': NOVA_EXCEPTIONS + PYTHON_LIBVIRT_EXCEPTIONS +
                  NEUTRONCLIENT_EXCEPTIONS + OS_VIF_EXCEPTIONS,
                  'octavia': OCTAVIA_EXCEPTIONS,
                  'placement': PLACEMENT_EXCEPTIONS,
                  }


class OpenstackConfig(host_helpers.IniConfigBase):

    def __getattr__(self, key):
        return self.get(key)


class OSTProject():
    SVC_VALID_SUFFIX = r'[0-9a-zA-Z-_]*'
    PY_CLIENT_PREFIX = r"python3?-{}\S*"

    def __init__(self, name, config=None, apt_core_alt=None,
                 systemd_masked_services=None,
                 systemd_deprecated_services=None,
                 log_path_overrides=None,
                 systemd_extra_services=None):
        """
        @param name: name of this project
        @param config: dict of config files keyed by a label used to identify
                       them. All projects should have a config file labelled
                       'main'.
        @param apt_core_alt: optional list of apt packages (regex) that are
                             used by this project where the name of the project
                             is not the same as the name used for its packages.
        @param systemd_masked_services: optional list of services that are
               expected to be masked in systemd e.g. if they are actually being
               run by apache.
        @param systemd_deprecated_services: optional list of services that are
               deprecated. This can be helpful if e.g. you want to skip checks
               for resources related to these services.
        @param log_path_overrides: specify log path for a given service that
                                   overrides the default format i.e.
                                   /var/log/<project>/<svc>.log.
        @param systemd_extra_services: optional list of systemd services that
               are used. This is useful e.g. if components are run under
               apache or if a package runs components using services whose name
               don't match the name of the project.
        """
        self.name = name
        self.packages_deps = [self.PY_CLIENT_PREFIX.format(name)]
        self.packages_core = [name]
        if apt_core_alt:
            self.packages_core.extend(apt_core_alt)
            for c in apt_core_alt:
                self.packages_deps.append(self.PY_CLIENT_PREFIX.format(c))

        self.config = {}
        if config:
            for label, path in config.items():
                path = os.path.join(HotSOSConfig.data_root, 'etc', name, path)
                self.config[label] = OpenstackConfig(path)

        self.systemd_extra_services = systemd_extra_services or []
        self.systemd_masked_services = systemd_masked_services or []
        self.systemd_deprecated_services = systemd_deprecated_services or []
        self.logs_path = os.path.join('var/log', name)
        self.log_path_overrides = log_path_overrides or {}
        self.exceptions = EXCEPTIONS_COMMON + OST_EXCEPTIONS.get(name, [])

    @cached_property
    def installed(self):
        """ Return True if the openstack service is installed. """
        return bool(host_helpers.APTPackageHelper(
                                            core_pkgs=self.packages_core).core)

    @cached_property
    def services_expr(self):
        exprs = [f'{self.name}{self.SVC_VALID_SUFFIX}']
        if self.systemd_extra_services:
            exprs += self.systemd_extra_services
        return exprs

    @cached_property
    def services(self):
        exprs = self.services_expr
        info = host_helpers.SystemdHelper(service_exprs=exprs)
        if not info.services:
            log.debug("no systemd services found for '%s' - trying pebble",
                      self.name)
            info = host_helpers.PebbleHelper(service_exprs=exprs)

        return info.services

    def log_paths(self, include_deprecated_services=True):
        """
        Returns tuples of daemon name, log path for each agent/daemon.
        """
        proj_manage = f"{self.name}-manage"
        path = os.path.join('var/log', self.name, f"{proj_manage}.log")
        yield proj_manage, [path]
        for svc in self.services:
            if (not include_deprecated_services and
                    svc in self.systemd_deprecated_services):
                continue

            path = os.path.join('var/log', self.name,
                                f"{svc}.log")
            yield svc, self.log_path_overrides.get(svc, [path])


class OSTProjectCatalog():
    # Services that are not actually openstack projects but are used by them
    OST_SERVICES_DEPS = ['dnsmasq',
                         r'(?:nfs-)?ganesha\S*',
                         'haproxy',
                         rf"keepalived{OSTProject.SVC_VALID_SUFFIX}",
                         rf"vault{OSTProject.SVC_VALID_SUFFIX}",
                         r'qemu-system-\S+',
                         'radvd',
                         ]

    # Set of packages that any project can depend on
    APT_DEPS_COMMON = ['conntrack',
                       'dnsmasq',
                       'haproxy',
                       'keepalived',
                       'libvirt-daemon',
                       'libvirt-bin',
                       r'nfs-ganesha\S*',
                       r'python3?-oslo[.-]',
                       'qemu-kvm',
                       'radvd',
                       ]

    def __init__(self):
        self._projects = {}
        self.add('aodh', config={'main': 'aodh.conf'},
                 systemd_masked_services=['aodh-api'],
                 systemd_extra_services=['apache2'],
                 log_path_overrides={'apache2':
                                     ['var/log/aodh/aodh-api.log']})
        self.add('barbican', config={'main': 'barbican.conf'},
                 systemd_masked_services=['barbican-api'],
                 systemd_extra_services=['apache2'],
                 log_path_overrides={'apache2':
                                     ['var/log/barbican/barbican-api.log']})
        self.add('ceilometer', config={'main': 'ceilometer.conf'},
                 systemd_masked_services=['ceilometer-api'])
        self.add('cinder', config={'main': 'cinder.conf'},
                 systemd_extra_services=['apache2'],
                 log_path_overrides={'apache2':
                                     ['var/log/apache2/cinder_*.log']})
        self.add('designate', config={'main': 'designate.conf'},
                 systemd_extra_services=['apache2'])
        self.add('glance', config={'main': 'glance-api.conf'},
                 systemd_extra_services=['apache2'])
        self.add('gnocchi', config={'main': 'gnocchi.conf'},
                 systemd_masked_services=['gnocchi-api'],
                 systemd_extra_services=['apache2'],
                 log_path_overrides={'apache2':
                                     ['var/log/gnocchi/gnocchi-api.log']})
        self.add('heat', config={'main': 'heat.conf'},
                 systemd_extra_services=['apache2'])
        self.add('horizon', apt_core_alt=['openstack-dashboard'],
                 systemd_extra_services=['apache2'])
        self.add('ironic', config={'main': 'ironic.conf'})
        self.add('keystone', config={'main': 'keystone.conf'},
                 systemd_masked_services=['keystone'],
                 systemd_extra_services=['apache2'],
                 log_path_overrides={'apache2':
                                     ['var/log/keystone/keystone.log']})
        self.add('neutron',
                 config={'main': 'neutron.conf',
                         'openvswitch-agent':
                         'plugins/ml2/openvswitch_agent.ini',
                         'l3-agent': 'l3_agent.ini',
                         'dhcp-agent': 'dhcp_agent.ini',
                         'ovn': 'ovn.ini',
                         'ml2': 'plugins/ml2/ml2_conf.ini'},
                 systemd_masked_services=['nova-api-metadata'],
                 systemd_extra_services=['apache2'],
                 systemd_deprecated_services=['neutron-lbaas-agent',
                                              'neutron-lbaasv2-agent',
                                              'neutron-fwaas-agent'])
        self.add('nova', config={'main': 'nova.conf'},
                 # See LP bug 1957760 for reason why neutron-server is added.
                 systemd_masked_services=['nova-api-os-compute',
                                          'neutron-server'],
                 systemd_extra_services=['apache2'],
                 log_path_overrides={'apache2':
                                     ['var/log/apache2/nova-*.log',
                                      'var/log/nova/nova-api-wsgi.log']})
        self.add('manila', config={'main': 'manila.conf'},
                 systemd_masked_services=['manila-api'],
                 systemd_extra_services=['apache2'],
                 log_path_overrides={'apache2':
                                     ['var/log/manila/manila-api.log']})
        self.add('masakari', config={'main': 'masakari.conf'},
                 systemd_masked_services=['masakari'],
                 systemd_extra_services=['apache2', 'masakari-engine'],
                 log_path_overrides={'apache2':
                                     ['var/log/apache2/masakari_error.log']})
        self.add('octavia', config={'main': 'octavia.conf',
                                    'amphora': 'amphora-agent.conf'},
                 systemd_masked_services=['octavia-api'],
                 apt_core_alt=[r'amphora-\S+'],
                 systemd_extra_services=['apache2', 'amphora-agent'],
                 log_path_overrides={'apache2':
                                     ['var/log/octavia/octavia-api.log']})
        self.add('placement', config={'main': 'placement.conf'},
                 systemd_masked_services=['placement'],
                 systemd_extra_services=['apache2'],
                 log_path_overrides={'apache2':
                                     ['var/log/apache2/*error.log']})
        self.add('swift', config={'main': 'swift-proxy.conf',
                                  'proxy': 'swift-proxy.conf'},
                 systemd_extra_services=['apache2'])

    def __getitem__(self, name):
        return self._projects[name]

    def __getattr__(self, name):
        if name in self._projects:
            return self._projects[name]

        raise AttributeError(f"project {name} not found")

    @cached_property
    def all(self):
        return self._projects

    @cached_property
    def service_exprs(self):
        # Expressions used to match openstack systemd services for each project
        exprs = []
        for p in self.all.values():
            if p.installed:
                exprs.extend(p.services_expr)

        exprs.extend(self.OST_SERVICES_DEPS)
        return exprs

    @cached_property
    def default_masked_services(self):
        """
        Returns a list of services that are expected to be marked as masked in
        systemd.
        """
        masked = []
        for p in self.all.values():
            masked += p.systemd_masked_services

        return sorted(masked)

    def add(self, name, *args, **kwargs):
        self._projects[name] = OSTProject(name, *args, **kwargs)

    @cached_property
    def packages_core_exprs(self):
        core = set()
        for p in self.all.values():
            core.update(p.packages_core)

        return list(core)

    @cached_property
    def packages_dep_exprs(self):
        deps = set(self.APT_DEPS_COMMON)
        for p in self.all.values():
            deps.update(p.packages_deps)

        return list(deps)


class OSTServiceBase():

    def __init__(self, name, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.nethelp = host_helpers.HostNetworkingHelper()
        self.project = OSTProjectCatalog()[name]

    @cached_property
    def installed(self):
        """ Return True if the openstack service is installed. """
        return self.project.installed
