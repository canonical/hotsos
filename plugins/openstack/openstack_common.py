import os
import re

from common import (
    checks,
    helpers,
)

# Plugin config opts from global
OPENSTACK_AGENT_ERROR_KEY_BY_TIME = \
    helpers.bool_str(os.environ.get('OPENSTACK_AGENT_ERROR_KEY_BY_TIME',
                                    "False"))
OPENSTACK_SHOW_CPU_PINNING_RESULTS = \
    helpers.bool_str(os.environ.get('OPENSTACK_SHOW_CPU_PINNING_RESULTS',
                                    "False"))

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

SVC_VALID_SUFFIX = r"[0-9a-zA-Z-_]*[^:/]?"

# expressions used to match openstack services for each project
OST_SERVICES_EXPRS = []
for project in OST_PROJECTS:
    OST_SERVICES_EXPRS.append(project + SVC_VALID_SUFFIX)

# Services that are not actually openstack projects but are used by them
OST_SERVICES_DEPS = [r"apache{}".format(SVC_VALID_SUFFIX),
                     r"beam.smp",
                     r"dnsmasq",
                     r"ganesha.nfsd",
                     r"haproxy",
                     r"keepalived{}".format(SVC_VALID_SUFFIX),
                     r"mysqld",
                     r"ovs{}".format(SVC_VALID_SUFFIX),
                     r"ovn{}".format(SVC_VALID_SUFFIX),
                     r"vault{}".format(SVC_VALID_SUFFIX),
                     r"qemu-system-\S+",
                     ]

OST_PKG_ALIASES = ["openstack-dashboard"]

OST_DEP_PKGS = [r"conntrack",
                r"dnsmasq",
                r"haproxy",
                r"keepalived",
                r"libc-bin",
                r"libvirt-daemon",
                r"libvirt-bin",
                r"nfs--ganesha",
                r"python3?-oslo[.-]",
                r"openvswitch-switch",
                r"ovn",
                r"qemu-kvm",
                ]

AGENT_DAEMON_NAMES = {
    "cinder": ["cinder-scheduler", "cinder-volume"],
    "glance": ["glance-api"],
    "heat": ["heat-engine", "heat-api", "heat-api-cfn"],
    "keystone": ["keystone"],
    "manila": ["manila-api", "manila-scheduler", "manila-data",
               "manila-share"],
    "neutron": ["neutron-openvswitch-agent", "neutron-dhcp-agent",
                "neutron-l3-agent", "neutron-server"],
    "nova": ["nova-compute", "nova-scheduler", "nova-conductor",
             "nova-api-os-compute", "nova-api-wsgi"],
    "octavia": ["octavia-api", "octavia-worker",
                "octavia-health-manager", "octavia-housekeeping",
                "octavia-driver-agent"],
    }

AGENT_LOG_PATHS = {"cinder": "var/log/cinder",
                   "glance": "var/log/glance",
                   "heat": "var/log/heat",
                   "keystone": "var/log/keystone",
                   "manila": "/var/log/manila",
                   "neutron": "var/log/neutron",
                   "nova": "var/log/nova",
                   "octavia": "var/log/octavia",
                   }

NEUTRON_HA_PATH = 'var/lib/neutron/ha_confs'


class OpenstackServiceChecksBase(checks.ServiceChecksBase):
    pass


class OpenstackChecksBase(object):

    def __init__(self):
        self._instances = []

    @property
    def running_instances(self):
        if self._instances:
            return self._instances

        for line in helpers.get_ps():
            ret = re.compile(".+product=OpenStack Nova.+").match(line)
            if ret:
                expr = r".+uuid\s+([a-z0-9\-]+)[\s,]+.+"
                ret = re.compile(expr).match(ret[0])
                if ret:
                    self._instances.append(ret[1])

        return self._instances

    def __call__(self):
        pass
