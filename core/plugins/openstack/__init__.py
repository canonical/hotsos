import os
import re

from core.issues import (
    issue_types,
    issue_utils,
)
from core import (
    checks,
    constants,
    host_helpers,
    plugintools,
)
from core.ycheck.events import YEventCheckerBase
from core.checks import DPKGVersionCompare
from core.log import log
from core.cli_helpers import CmdBase, CLIHelper
from core.plugins.openstack.exceptions import (
    EXCEPTIONS_COMMON,
    BARBICAN_EXCEPTIONS,
    CASTELLAN_EXCEPTIONS,
    CINDER_EXCEPTIONS,
    KEYSTONE_EXCEPTIONS,
    MANILA_EXCEPTIONS,
    PLACEMENT_EXCEPTIONS,
    PYTHON_LIBVIRT_EXCEPTIONS,
    NOVA_EXCEPTIONS,
    NEUTRON_EXCEPTIONS,
    OCTAVIA_EXCEPTIONS,
    OVSDBAPP_EXCEPTIONS,
)

APT_SOURCE_PATH = os.path.join(constants.DATA_ROOT, 'etc/apt/sources.list.d')
NEUTRON_HA_PATH = 'var/lib/neutron/ha_confs'

# Plugin config opts from global
AGENT_ERROR_KEY_BY_TIME = \
    constants.bool_str(os.environ.get('AGENT_ERROR_KEY_BY_TIME',
                                      'False'))
SHOW_CPU_PINNING_RESULTS = \
    constants.bool_str(os.environ.get('SHOW_CPU_PINNING_RESULTS',
                                      'False'))

OST_REL_INFO = {
    'barbican-common': {
        'yoga': '1:14.0.0',
        'xena': '1:13.0.0',
        'wallaby': '1:12.0.0',
        'victoria': '1:11.0.0',
        'ussuri': '1:10.0.0',
        'train': '1:9.0.0',
        'stein': '1:8.0.0',
        'rocky': '1:7.0.0',
        'queens': '1:6.0.0'},
    'cinder-common': {
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
        'yoga': '1:18.0.0',
        'xena': '1:17.0.0',
        'wallaby': '1:16.0.0',
        'victoria': '1:15.0.0',
        'ussuri': '1:14.0.0',
        'train': '1:13.0.0',
        'stein': '1:12.0.0',
        'rocky': '1:11.0.0',
        'queens': '1:10.0.0'},
    'keystone': {
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
    'nova-common': {
        'yoga': '2:25.0.0',
        'xena': '2:24.0.0',
        'wallaby': '2:23.0.0',
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
    'neutron-common': {
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
    'octavia-common': {
        'yoga': '10.0.0',
        'xena': '9.0.0',
        'wallaby': '8.0.0',
        'victoria': '7.0.0',
        'ussuri': '6.0.0',
        'train': '5.0.0',
        'stein': '4.0.0',
        'rocky': '3.0.0'}
    }

OST_EXCEPTIONS = {'barbican': BARBICAN_EXCEPTIONS + CASTELLAN_EXCEPTIONS,
                  'cinder': CINDER_EXCEPTIONS + CASTELLAN_EXCEPTIONS,
                  'keystone': KEYSTONE_EXCEPTIONS,
                  'manila': MANILA_EXCEPTIONS,
                  'neutron': NEUTRON_EXCEPTIONS + OVSDBAPP_EXCEPTIONS,
                  'nova': NOVA_EXCEPTIONS + PYTHON_LIBVIRT_EXCEPTIONS,
                  'octavia': OCTAVIA_EXCEPTIONS,
                  'placement': PLACEMENT_EXCEPTIONS,
                  }


class OpenstackConfig(checks.SectionalConfigBase):
    pass


class OSTProject(object):
    SVC_VALID_SUFFIX = r'[0-9a-zA-Z-_]*'
    PY_CLIENT_PREFIX = r"python3?-{}\S*"

    def __init__(self, name, config=None, daemon_names=None,
                 apt_core_alt=None, systemd_masked_services=None,
                 log_path_overrides=None):
        """
        @param name: name of this project
        @param config: dict of config files keyed by a label used to identify
                       them. All projects should have a config file labelled
                       'main'.
        @param daemon_names: list of daemon names of processes run by this
                             project.
        @param apt_core_alt: optional list of apt packages (regex) that are
                             used by this project where the name of the project
                             is not the same as the name used for its packages.
        @param systemd_masked_services: optional list of services that are
               expected to be masked in systemd e.g. if they are actually being
               run by apache.
        """
        self.name = name
        self.packages_core = [name]
        if apt_core_alt:
            self.packages_core.append(apt_core_alt)
            client = self.PY_CLIENT_PREFIX.format(apt_core_alt)
        else:
            client = self.PY_CLIENT_PREFIX.format(name)

        self.config = {}
        if config:
            for label, path in config.items():
                path = os.path.join(constants.DATA_ROOT, 'etc', name, path)
                self.config[label] = OpenstackConfig(path)

        self.systemd_masked_services = systemd_masked_services or []
        self.packages_core.append(client)
        self.service_expr = '{}{}'.format(name, self.SVC_VALID_SUFFIX)
        self.daemon_names = daemon_names or []
        self.logs_path = os.path.join('var/log', name)
        self.log_path_overrides = log_path_overrides or {}
        self.exceptions = EXCEPTIONS_COMMON + OST_EXCEPTIONS.get(name, [])

    @property
    def log_paths(self):
        """
        Returns tuples of daemon name, log path for each agent/daemon.
        """
        proj_manage = "{}-manage".format(self.name)
        yield proj_manage, os.path.join('var/log', self.name,
                                        "{}.log".format(proj_manage))
        for daemon in self.daemon_names:
            path = os.path.join('var/log', self.name,
                                "{}.log".format(daemon))
            yield daemon, self.log_path_overrides.get(daemon, path)


class OSTProjectCatalog(object):
    # Services that are not actually openstack projects but are used by them
    OST_SERVICES_DEPS = [r'apache2',
                         'dnsmasq',
                         'ganesha.nfsd',
                         'haproxy',
                         r"keepalived{}".format(OSTProject.SVC_VALID_SUFFIX),
                         'mysqld',
                         r"vault{}".format(OSTProject.SVC_VALID_SUFFIX),
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
                       r'mysql-?\S+',
                       'pacemaker',
                       'corosync',
                       'nfs--ganesha',
                       r'python3?-oslo[.-]',
                       'qemu-kvm',
                       'radvd',
                       ]

    def __init__(self):
        self._projects = {}
        self.add('aodh', config={'main': 'aodh.conf'},
                 systemd_masked_services=['aodh-api']),
        self.add('barbican',
                 daemon_names=['barbican-api', 'barbican-worker'],
                 config={'main': 'barbican.conf'},
                 systemd_masked_services=['barbican-api']),
        self.add('ceilometer', config={'main': 'ceilometer.conf'},
                 systemd_masked_services=['ceilometer-api']),
        self.add('cinder',
                 daemon_names=['cinder-scheduler', 'cinder-volume'],
                 config={'main': 'cinder.conf'}),
        self.add('designate',
                 daemon_names=['designate-agent', 'designate-api',
                               'designate-central', 'designate-mdns',
                               'designate-producer', 'designate-sink',
                               'designate-worker'],
                 config={'main': 'designate.conf'}),
        self.add('glance', daemon_names=['glance-api'],
                 config={'main': 'glance-api.conf'}),
        self.add('gnocchi', config={'main': 'gnocchi.conf'},
                 systemd_masked_services=['gnocchi-api']),
        self.add('heat',
                 daemon_names=['heat-engine', 'heat-api', 'heat-api-cfn'],
                 config={'main': 'heat.conf'}),
        self.add('horizon',
                 apt_core_alt='openstack-dashboard'),
        self.add('keystone', daemon_names=['keystone'],
                 config={'main': 'keystone.conf'},
                 systemd_masked_services=['keystone']),
        self.add('neutron',
                 daemon_names=['neutron-openvswitch-agent',
                               'neutron-dhcp-agent', 'neutron-l3-agent',
                               'neutron-server', 'neutron-sriov-agent'],
                 config={'main': 'neutron.conf',
                         'openvswitch-agent':
                         'plugins/ml2/openvswitch_agent.ini',
                         'l3-agent': 'l3_agent.ini',
                         'dhcp-agent': 'dhcp_agent.ini'},
                 systemd_masked_services=['nova-api-metadata']),
        self.add('nova',
                 daemon_names=['nova-compute', 'nova-scheduler',
                               'nova-conductor', 'nova-api-os-compute',
                               'nova-api-wsgi', 'nova-api-metadata',
                               'nova-placement'],
                 config={'main': 'nova.conf'},
                 systemd_masked_services=['nova-api-os-compute'],
                 log_path_overrides={'nova-api-os-compute':
                                     'var/log/apache2/nova-*.log'}),
        self.add('manila',
                 daemon_names=['manila-api', 'manila-scheduler',
                               'manila-data', 'manila-share'],
                 config={'main': 'manila.conf'},
                 systemd_masked_services=['manila-api']),
        self.add('masakari', config={'main': 'masakari.conf'},
                 systemd_masked_services=['masakari']),
        self.add('octavia',
                 daemon_names=['octavia-api', 'octavia-worker',
                               'octavia-health-manager',
                               'octavia-housekeeping',
                               'octavia-driver-agent'],
                 config={'main': 'octavia.conf'},
                 systemd_masked_services=['octavia-api']),
        self.add('placement', config={'main': 'placement.conf'},
                 systemd_masked_services=['placement'],
                 log_path_overrides={'placement':
                                     'var/log/apache2/*error.log'}),
        self.add('swift', config={'main': 'swift-proxy.conf',
                                  'proxy': 'swift-proxy.conf'}),

    def __getattr__(self, name):
        return self._projects[name]

    @property
    def all(self):
        return self._projects

    @property
    def service_exprs(self):
        # Expressions used to match openstack systemd services for each project
        return [p.service_expr for p in self.all.values()] + \
                self.OST_SERVICES_DEPS

    @property
    def default_masked_services(self):
        """
        Returns a list of services that are expected to be marked as masked in
        systemd.
        """
        masked = []
        for p in self.all.values():
            masked += p.systemd_masked_services

        return masked

    def add(self, name, *args, **kwargs):
        self._projects[name] = OSTProject(name, *args, **kwargs)

    @property
    def packages_core(self):
        # Set of packages we consider to be core for openstack
        core = []
        for p in self.all.values():
            core += p.packages_core

        return core

    @property
    def package_dependencies(self):
        return self.APT_DEPS_COMMON


class OSGuest(object):
    def __init__(self, uuid, name):
        self.uuid = uuid
        self.name = name
        self.ports = []

    def add_port(self, port):
        self.ports.append(port)


class NeutronRouter(object):
    def __init__(self, uuid, ha_state):
        self.uuid = uuid
        self.ha_state = ha_state
        self.vr_id = None


class NeutronHAInfo(object):

    def __init__(self):
        self._routers = []
        self._get_neutron_ha_info()
        self.vr_id = None

    def _get_neutron_ha_info(self):
        if not os.path.exists(self.state_path):
            return

        for entry in os.listdir(self.state_path):
            entry = os.path.join(self.state_path, entry)
            if not os.path.isdir(entry):
                # if its not a directory then it is probably not a live router
                # so we ignore it.
                continue

            state_path = os.path.join(entry, 'state')
            if not os.path.exists(state_path):
                continue

            with open(state_path) as fd:
                uuid = os.path.basename(entry)
                state = fd.read().strip()
                router = NeutronRouter(uuid, state)

            keepalived_conf_path = os.path.join(entry, 'keepalived.conf')
            if os.path.isfile(keepalived_conf_path):
                with open(keepalived_conf_path) as fd:
                    for line in fd:
                        expr = r'.+ virtual_router_id (\d+)'
                        ret = re.compile(expr).search(line)
                        if ret:
                            router.vr_id = ret.group(1)

            self._routers.append(router)

    def find_router_with_vr_id(self, id):
        for r in self.ha_routers:
            if r.vr_id == id:
                return r

    @property
    def state_path(self):
        return os.path.join(constants.DATA_ROOT, NEUTRON_HA_PATH)

    @property
    def ha_routers(self):
        return self._routers


class OctaviaBase(object):

    OCTAVIA_HM_PORT_NAME = 'o-hm0'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.nethelp = host_helpers.HostNetworkingHelper()

    @property
    def bind_interfaces(self):
        """
        Fetch interface o-hm0 used by Openstack Octavia. Returned dict is
        keyed by config key used to identify interface.
        """
        interfaces = {}
        port = self.nethelp.get_interface_with_name(self.OCTAVIA_HM_PORT_NAME)
        if port:
            interfaces.update({self.OCTAVIA_HM_PORT_NAME: port})

        return interfaces

    @property
    def hm_port_has_address(self):
        port = self.bind_interfaces.get(self.OCTAVIA_HM_PORT_NAME)
        if port is None or not port.addresses:
            return False

        return True

    @property
    def hm_port_healthy(self):
        port = self.bind_interfaces.get(self.OCTAVIA_HM_PORT_NAME)
        if port is None:
            return True

        for counters in port.stats.values():
            total = sum(counters.values())
            if not total:
                continue

            pcent = int(100 / float(total) * float(counters.get('dropped', 0)))
            if pcent > 1:
                return False

            pcent = int(100 / float(total) * float(counters.get('errors', 0)))
            if pcent > 1:
                return False

        return True


class NovaBase(object):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.nethelp = host_helpers.HostNetworkingHelper()
        self._instances = []
        self.nova_config = OSTProjectCatalog().nova.config['main']

    @property
    def instances(self):
        if self._instances:
            return self._instances

        for line in CLIHelper().ps():
            ret = re.compile('.+product=OpenStack Nova.+').match(line)
            if ret:
                name = None
                uuid = None

                expr = r'.+uuid\s+([a-z0-9\-]+)[\s,]+.+'
                ret = re.compile(expr).match(ret[0])
                if ret:
                    uuid = ret[1]

                expr = r'.+\s+-name\s+guest=(instance-\w+)[,]*.*\s+.+'
                ret = re.compile(expr).match(ret[0])
                if ret:
                    name = ret[1]

                if not all([name, uuid]):
                    continue

                guest = OSGuest(uuid, name)
                ret = re.compile(r'mac=([a-z0-9:]+)').findall(line)
                if ret:
                    for mac in ret:
                        # convert libvirt to local/native
                        mac = 'fe' + mac[2:]
                        _port = self.nethelp.get_interface_with_hwaddr(mac)
                        if _port:
                            guest.add_port(_port)

                self._instances.append(guest)

        return self._instances

    @property
    def bind_interfaces(self):
        """
        Fetch interfaces used by Openstack Nova. Returned dict is keyed by
        config key used to identify interface.
        """
        my_ip = self.nova_config.get('my_ip')

        interfaces = {}
        if not any([my_ip]):
            return interfaces

        if my_ip:
            port = self.nethelp.get_interface_with_addr(my_ip)
            # NOTE: my_ip can be an address or fqdn, we currently only support
            # searching by address.
            if port:
                interfaces.update({'my_ip': port})

        return interfaces


class NeutronBase(object):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.nethelp = host_helpers.HostNetworkingHelper()
        neutron = OSTProjectCatalog().neutron
        self.neutron_ovs_config = neutron.config['openvswitch-agent']

    @property
    def bind_interfaces(self):
        """
        Fetch interfaces used by Openstack Neutron. Returned dict is keyed by
        config key used to identify interface.
        """
        local_ip = self.neutron_ovs_config.get('local_ip')

        interfaces = {}
        if not any([local_ip]):
            return interfaces

        if local_ip:
            port = self.nethelp.get_interface_with_addr(local_ip)
            # NOTE: local_ip can be an address or fqdn, we currently only
            # support searching by address.
            if port:
                interfaces.update({'local_ip': port})

        return interfaces


class OpenstackBase(object):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ost_projects = OSTProjectCatalog()
        other_pkgs = self.ost_projects.package_dependencies
        self.apt_check = checks.APTPackageChecksBase(
                                  core_pkgs=self.ost_projects.packages_core,
                                  other_pkgs=other_pkgs)
        self.nova = NovaBase()
        self.neutron = NeutronBase()
        self.octavia = OctaviaBase()

    @property
    def apt_packages_all(self):
        return self.apt_check.all

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

    @property
    def release_name(self):
        relname = None

        relnames = set()
        for pkg in OST_REL_INFO:
            if pkg in self.apt_check.core:
                # Since the versions we match against will always match our
                # version - 1 we use last known lt as current version.
                v_lt = None
                r_lt = None
                pkg_ver = DPKGVersionCompare(self.apt_check.core[pkg])
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
        if relnames:
            relnames = sorted(list(relnames))
            if len(relnames) > 1:
                relnames
                msg = ("openstack packages from mixed releases found - {}".
                       format(relnames))
                issue = issue_types.OpenstackWarning(msg)
                issue_utils.add_issue(issue)

            relname = relnames[0]

        if relname:
            return relname

        relname = 'unknown'

        # fallback to uca version if exists
        if not os.path.exists(APT_SOURCE_PATH):
            return relname

        release_info = {}
        for source in os.listdir(APT_SOURCE_PATH):
            apt_path = os.path.join(APT_SOURCE_PATH, source)
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


class OpenstackChecksBase(OpenstackBase, plugintools.PluginPartBase):

    @property
    def openstack_installed(self):
        if self.apt_check.core:
            return True

        return False

    @property
    def plugin_runnable(self):
        return self.openstack_installed


class OpenstackEventChecksBase(OpenstackChecksBase, YEventCheckerBase):

    def __call__(self):
        ret = self.run_checks()
        if ret:
            self._output.update(ret)


class OpenstackServiceChecksBase(OpenstackChecksBase,
                                 checks.ServiceChecksBase):
    def __init__(self):
        service_exprs = OSTProjectCatalog().service_exprs
        super().__init__(service_exprs=service_exprs, hint_range=(0, 3))


class OpenstackPackageChecksBase(OpenstackChecksBase):
    pass


class OpenstackDockerImageChecksBase(OpenstackChecksBase,
                                     checks.DockerImageChecksBase):

    def __init__(self):
        self.ost_projects = OSTProjectCatalog()
        super().__init__(core_pkgs=self.ost_projects.packages_core,
                         other_pkgs=self.ost_projects.package_dependencies)
