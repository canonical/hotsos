import os
import re

from core import (
    checks,
    constants,
    host_helpers,
    plugintools,
)
from core.cli_helpers import CmdBase, CLIHelper
from core.plugins.openstack import exceptions

APT_SOURCE_PATH = os.path.join(constants.DATA_ROOT, "etc/apt/sources.list.d")

# Plugin config opts from global
OPENSTACK_AGENT_ERROR_KEY_BY_TIME = \
    constants.bool_str(os.environ.get('OPENSTACK_AGENT_ERROR_KEY_BY_TIME',
                                      'False'))
OPENSTACK_SHOW_CPU_PINNING_RESULTS = \
    constants.bool_str(os.environ.get('OPENSTACK_SHOW_CPU_PINNING_RESULTS',
                                      'False'))

OST_REL_INFO = {
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
        'ocata': '2:15.0.0'},
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
        'ocata': '2:10.0.0'},
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

# These are the names of Openstack projects we want to track.
OST_PROJECTS = ["aodh",
                "barbican",
                "ceilometer",
                "cinder",
                "designate",
                "glance",
                "gnocchi",
                "heat",
                "horizon",
                "keystone",
                "neutron",
                "nova",
                "manila",
                "masakari",
                "octavia",
                "placement",
                "swift",
                ]

SVC_VALID_SUFFIX = r"[0-9a-zA-Z-_]*"

# expressions used to match openstack services for each project
OST_SERVICES_EXPRS = []
for project in OST_PROJECTS:
    OST_SERVICES_EXPRS.append(project + SVC_VALID_SUFFIX)

# Services that are not actually openstack projects but are used by them
OST_SERVICES_DEPS = [r"apache{}".format(SVC_VALID_SUFFIX),
                     r"dnsmasq",
                     r"ganesha.nfsd",
                     r"haproxy",
                     r"keepalived{}".format(SVC_VALID_SUFFIX),
                     r"mysqld",
                     r"vault{}".format(SVC_VALID_SUFFIX),
                     r"qemu-system-\S+",
                     r"radvd",
                     ]

OST_PKG_ALIASES = ["openstack-dashboard"]
OST_PKGS_CORE = OST_PROJECTS + OST_PKG_ALIASES
OST_DEP_PKGS = [r"conntrack",
                r"dnsmasq",
                r"haproxy",
                r"keepalived",
                r"libvirt-daemon",
                r"libvirt-bin",
                r"mysql-?\S+",
                r"pacemaker",
                r"corosync",
                r"nfs--ganesha",
                r"python3?-oslo[.-]",
                r"qemu-kvm",
                r"radvd",
                ]
# Add in clients/deps
for pkg in OST_PKGS_CORE:
    OST_DEP_PKGS.append(r"python3?-{}\S*".format(pkg))

AGENT_DAEMON_NAMES = {
    "barbican": ["barbican-api", "barbican-worker"],
    "cinder": ["cinder-scheduler", "cinder-volume"],
    "designate": ["designate-agent", "designate-api", "designate-central",
                  "designate-mdns", "designate-producer", "designate-sink",
                  "designate-worker"],
    "glance": ["glance-api"],
    "heat": ["heat-engine", "heat-api", "heat-api-cfn"],
    "keystone": ["keystone"],
    "manila": ["manila-api", "manila-scheduler", "manila-data",
               "manila-share"],
    "neutron": ["neutron-openvswitch-agent", "neutron-dhcp-agent",
                "neutron-l3-agent", "neutron-server",
                "neutron-sriov-agent"],
    "nova": ["nova-compute", "nova-scheduler", "nova-conductor",
             "nova-api-os-compute", "nova-api-wsgi", "nova-api-metadata.log"],
    "octavia": ["octavia-api", "octavia-worker",
                "octavia-health-manager", "octavia-housekeeping",
                "octavia-driver-agent"],
    }


# These can exist in any service
AGENT_EXCEPTIONS_COMMON = [
    r"AMQP server on .+ is unreachable",
    r"amqp.exceptions.ConnectionForced",
    r"OSError: Server unexpectedly closed connection",
]
for exc in exceptions.OSLO_DB_EXCEPTIONS + \
        exceptions.OSLO_MESSAGING_EXCEPTIONS + \
        exceptions.PYTHON_BUILTIN_EXCEPTIONS:
    AGENT_EXCEPTIONS_COMMON.append(exc)

SERVICE_RESOURCES = {}
for service in OST_PROJECTS:
    SERVICE_RESOURCES[service] = {"logs": os.path.join("var/log", service),
                                  "exceptions_base": [] +
                                  AGENT_EXCEPTIONS_COMMON,
                                  "daemons":
                                  AGENT_DAEMON_NAMES.get(service, [])}

NEUTRON_HA_PATH = 'var/lib/neutron/ha_confs'

CONFIG_FILES = {"neutron": {"neutron": "etc/neutron/neutron.conf",
                            "openvswitch-agent":
                            "etc/neutron/plugins/ml2/openvswitch_agent.ini",
                            "l3-agent": "etc/neutron/l3_agent.ini",
                            "dhcp-agent": "etc/neutron/dhcp_agent.ini"},
                "nova": {"nova": "etc/nova/nova.conf"}}


class OpenstackConfig(checks.SectionalConfigBase):
    pass


class OSGuest(object):
    def __init__(self, uuid, name):
        self.uuid = uuid
        self.name = name
        self.ports = []

    def add_port(self, port):
        self.ports.append(port)


class OpenstackBase(object):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._instances = []
        self.nethelp = host_helpers.HostNetworkingHelper()
        nova_conf = os.path.join(constants.DATA_ROOT,
                                 CONFIG_FILES['nova']['nova'])
        self.nova_config = OpenstackConfig(nova_conf)
        neutron_ovs_conf = CONFIG_FILES['neutron']['openvswitch-agent']
        neutron_ovs_conf = os.path.join(constants.DATA_ROOT, neutron_ovs_conf)
        self.neutron_ovs_config = OpenstackConfig(neutron_ovs_conf)
        self.apt_check = checks.APTPackageChecksBase(core_pkgs=OST_PKGS_CORE,
                                                     other_pkgs=OST_DEP_PKGS)

    @property
    def instances(self):
        if self._instances:
            return self._instances

        for line in CLIHelper().ps():
            ret = re.compile(".+product=OpenStack Nova.+").match(line)
            if ret:
                name = None
                uuid = None

                expr = r".+uuid\s+([a-z0-9\-]+)[\s,]+.+"
                ret = re.compile(expr).match(ret[0])
                if ret:
                    uuid = ret[1]

                expr = r".+\s+-name\s+guest=(instance-\w+)[,]*.*\s+.+"
                ret = re.compile(expr).match(ret[0])
                if ret:
                    name = ret[1]

                if not all([name, uuid]):
                    continue

                guest = OSGuest(uuid, name)
                ret = re.compile(r"mac=([a-z0-9:]+)").findall(line)
                if ret:
                    for mac in ret:
                        # convert libvirt to local/native
                        mac = "fe" + mac[2:]
                        _port = self.nethelp.get_interface_with_hwaddr(mac)
                        if _port:
                            guest.add_port(_port)

                self._instances.append(guest)

        return self._instances

    @property
    def nova_bind_interfaces(self):
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

    @property
    def neutron_bind_interfaces(self):
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

    @property
    def octavia_bind_interfaces(self):
        """
        Fetch interface o-hm0 used by Openstack Octavia. Returned dict is
        keyed by config key used to identify interface.
        """
        interfaces = {}
        port = self.nethelp.get_interface_with_name('o-hm0')
        if port:
            interfaces.update({'o-hm0': port})

        return interfaces

    @property
    def bind_interfaces(self):
        """
        Fetch interfaces used by Openstack services and return dict.
        """
        interfaces = {}

        nova = self.nova_bind_interfaces
        if nova:
            interfaces.update(nova)

        neutron = self.neutron_bind_interfaces
        if neutron:
            interfaces.update(neutron)

        return interfaces

    @property
    def release_name(self):
        relname = None

        # First try from package version (TODO: add more)
        for pkg in ['neutron-common', 'nova-common']:
            if pkg in self.apt_check.core:
                for rel, ver in sorted(OST_REL_INFO[pkg].items(),
                                       key=lambda i: i[1], reverse=True):
                    if self.apt_check.core[pkg] > \
                            checks.DPKGVersionCompare(ver):
                        relname = rel
                        break

                break

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
                rexpr = r"deb .+ubuntu-cloud.+ [a-z]+-([a-z]+)/([a-z]+) .+"
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


class OpenstackEventChecksBase(OpenstackChecksBase, checks.EventChecksBase):

    def __call__(self):
        ret = self.run_checks()
        if ret:
            self._output.update(ret)


class OpenstackServiceChecksBase(OpenstackChecksBase,
                                 checks.ServiceChecksBase):
    pass


class OpenstackPackageChecksBase(OpenstackChecksBase):
    pass


class OpenstackPackageBugChecksBase(OpenstackPackageChecksBase):

    def __call__(self):
        c = checks.PackageBugChecksBase(self.release_name, self.apt_check.all)
        c()


class OpenstackDockerImageChecksBase(OpenstackChecksBase,
                                     checks.DockerImageChecksBase):

    def __init__(self):
        super().__init__(core_pkgs=OST_PKGS_CORE, other_pkgs=OST_DEP_PKGS)
