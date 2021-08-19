import os
import re

from common import (
    checks,
    constants,
    host_helpers,
    plugintools,
)
from common.cli_helpers import CLIHelper
from common.plugins.openstack import exceptions

# Plugin config opts from global
OPENSTACK_AGENT_ERROR_KEY_BY_TIME = \
    constants.bool_str(os.environ.get('OPENSTACK_AGENT_ERROR_KEY_BY_TIME',
                                      'False'))
OPENSTACK_SHOW_CPU_PINNING_RESULTS = \
    constants.bool_str(os.environ.get('OPENSTACK_SHOW_CPU_PINNING_RESULTS',
                                      'False'))

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
                ]

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
    r"(AMQP server on .+ is unreachable)",
    r"(amqp.exceptions.ConnectionForced):",
    r"(OSError: Server unexpectedly closed connection)",
    r"(ConnectionResetError: .+)",
]
for exc in exceptions.OSLO_DB_EXCEPTIONS + \
        exceptions.OSLO_MESSAGING_EXCEPTIONS + \
        exceptions.PYTHON_BUILTIN_EXCEPTIONS:
    AGENT_EXCEPTIONS_COMMON.append(r"({})".format(exc))

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


class OpenstackServiceChecksBase(plugintools.PluginPartBase,
                                 checks.ServiceChecksBase):
    pass


class OpenstackChecksBase(plugintools.PluginPartBase):

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

    @property
    def running_instances(self):
        if self._instances:
            return self._instances

        for line in CLIHelper().ps():
            ret = re.compile(".+product=OpenStack Nova.+").match(line)
            if ret:
                guest = {}
                expr = r".+uuid\s+([a-z0-9\-]+)[\s,]+.+"
                ret = re.compile(expr).match(ret[0])
                if ret:
                    guest["uuid"] = ret[1]

                expr = r".+\s+-name\s+guest=(instance-\w+)[,]*.*\s+.+"
                ret = re.compile(expr).match(ret[0])
                if ret:
                    guest["name"] = ret[1]

                if guest:
                    # get ports
                    ret = re.compile(r"mac=([a-z0-9:]+)").findall(line)
                    if ret:
                        guest['ports'] = []
                        for mac in ret:
                            # convert libvirt to local/native
                            mac = "fe" + mac[2:]
                            _port = self.nethelp.get_interface_with_hwaddr(mac)
                            if _port:
                                guest['ports'].append(_port)

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

    def __call__(self):
        pass


class AgentChecksBase(object):
    MAX_RESULTS = 5

    def __init__(self, searchobj, master_results_key=None):
        """
        @param searchobj: FileSearcher object used for searches.
        @param master_results_key: optional - key into which results
                                   will be stored in master yaml.
        """
        self.searchobj = searchobj
        if master_results_key:
            self.master_results_key = master_results_key

    def register_search_terms(self):
        raise NotImplementedError

    def process_results(self, results):
        raise NotImplementedError


class OpenstackConfig(checks.SectionalConfigBase):
    pass


class OpenstackPackageChecksBase(plugintools.PluginPartBase,
                                 checks.APTPackageChecksBase):

    def __init__(self):
        super().__init__(core_pkgs=OST_PKGS_CORE, other_pkgs=OST_DEP_PKGS)


class OpenstackDockerImageChecksBase(plugintools.PluginPartBase,
                                     checks.DockerImageChecksBase):

    def __init__(self):
        super().__init__(core_pkgs=OST_PKGS_CORE, other_pkgs=OST_DEP_PKGS)
