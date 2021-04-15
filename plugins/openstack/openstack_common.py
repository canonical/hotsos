import os

from common import (
    helpers,
)

# Plugin config opts from global
OPENSTACK_AGENT_ERROR_KEY_BY_TIME = \
    helpers.bool_str(os.environ.get('OPENSTACK_AGENT_ERROR_KEY_BY_TIME',
                                    "False"))
OPENSTACK_SHOW_CPU_PINNING_RESULTS = \
    helpers.bool_str(os.environ.get('OPENSTACK_SHOW_CPU_PINNING_RESULTS',
                                    "False"))

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
                "octavia",
                "swift",
                ]

SVC_VALID_SUFFIX = r"[0-9a-zA-Z-_]*[^:/]?"

# TODO: keep this list up-to-date with services we care about in the context of
#       openstack.
OST_SERVICES = [r"aodh{}".format(SVC_VALID_SUFFIX),
                r"barbican{}".format(SVC_VALID_SUFFIX),
                r"ceilometer{}".format(SVC_VALID_SUFFIX),
                r"cinder{}".format(SVC_VALID_SUFFIX),
                r"designate{}".format(SVC_VALID_SUFFIX),
                r"glance{}".format(SVC_VALID_SUFFIX),
                r"gnocchi{}".format(SVC_VALID_SUFFIX),
                r"heat{}".format(SVC_VALID_SUFFIX),
                r"horizon",
                r"keystone{}".format(SVC_VALID_SUFFIX),
                r"neutron{}".format(SVC_VALID_SUFFIX),
                r"nova{}".format(SVC_VALID_SUFFIX),
                r"octavia{}".format(SVC_VALID_SUFFIX),
                r"swift{}".format(SVC_VALID_SUFFIX),
                ]

# Services that are not actually openstack projects but are used by them
OST_SERVICES_DEPS = [r"apache{}".format(SVC_VALID_SUFFIX),
                     r"beam.smp",
                     r"dnsmasq",
                     r"haproxy",
                     r"keepalived{}".format(SVC_VALID_SUFFIX),
                     r"mysqld",
                     r"ovs{}".format(SVC_VALID_SUFFIX),
                     r"ovn{}".format(SVC_VALID_SUFFIX),
                     r"rabbitmq-server",
                     r"vault{}".format(SVC_VALID_SUFFIX),
                     r"qemu-system-\S+",
                     ]


OST_DEP_PKGS = [r"conntrack",
                r"dnsmasq",
                r"haproxy",
                r"keepalived",
                r"libc-bin",
                r"libvirt-daemon",
                r"libvirt-bin",
                r"python3?-oslo[.-]",
                r"openvswitch-switch",
                r"ovn",
                r"qemu-kvm",
                r"rabbitmq-server",
                ]

AGENT_DAEMON_NAMES = {
    "cinder": ["cinder-scheduler", "cinder-volume"],
    "glance": ["glance-api"],
    "heat": ["heat-engine", "heat-api", "heat-api-cfn"],
    "keystone": ["keystone"],
    "neutron": ["neutron-openvswitch-agent", "neutron-dhcp-agent",
                "neutron-l3-agent", "neutron-server"],
    "nova": ["nova-compute", "nova-scheduler", "nova-conductor",
             "nova-api-os-compute", "nova-api-wsgi"],
    "octavia": ["octavia-api", "octavia-worker",
                "octavia-health-manager", "octavia-housekeeping"],
    }

AGENT_LOG_PATHS = {"cinder": "var/log/cinder",
                   "glance": "var/log/glance",
                   "heat": "var/log/heat",
                   "keystone": "var/log/keystone",
                   "neutron": "var/log/neutron",
                   "nova": "var/log/nova",
                   "octavia": "var/log/octavia",
                   }
