#!/usr/bin/python3
import re
import os

from common import (
    constants,
    helpers,
    plugin_yaml,
)

CONFIG_FILES = {"neutron": {"neutron": "etc/neutron/neutron.conf",
                            "openvswitch-agent":
                            "etc/neutron/plugins/ml2/openvswitch_agent.ini",
                            "l3-agent": "etc/neutron/l3_agent.ini",
                            "dhcp-agent": "etc/neutron/dhcp_agent.ini"},
                "nova": {"nova": "etc/nova/nova.conf"}}

FEATURES = {"neutron": {"neutron": ["availability_zone"],
                        "openvswitch-agent": ["l2_population"],
                        "l3-agent": ["agent_mode", "ovs_use_veth"],
                        "dhcp-agent": ["enable_metadata_network",
                                       "enable_isolated_metadata",
                                       "ovs_use_veth"]},
            "nova": {"nova": ["vcpu_pin_set", "cpu_shared_set",
                              "cpu_dedicated_set"]}}

# checked against neutron
DEFAULTS = {"neutron": {"dhcp-agent": {"enable_metadata_network": False,
                                       "enable_isolated_metadata": False}}}

SERVICE_FEATURES = {}


def get_service_features():
    for service in FEATURES:
        for module in FEATURES[service]:
            module_features = {}
            cfg = os.path.join(constants.DATA_ROOT,
                               CONFIG_FILES[service][module])
            if not os.path.exists(cfg):
                continue

            for key in FEATURES[service][module]:
                for line in open(cfg).readlines():
                    ret = re.compile(r"^{}\s*=\s*(.+)\s*".format(key)
                                     ).match(line)
                    if ret:
                        module_features[key] = helpers.bool_str(ret[1])
                        break

                if key not in module_features:
                    if key in DEFAULTS.get(service, {}).get(module, {}):
                        default = DEFAULTS[service][module][key]
                        module_features[key] = default

            # TODO: only include modules for which there is an actual agent
            #       installed since otherwise their config is irrelevant.
            if module_features:
                if service not in SERVICE_FEATURES:
                    SERVICE_FEATURES[service] = {}

                SERVICE_FEATURES[service][module] = module_features


if __name__ == "__main__":
    get_service_features()
    if SERVICE_FEATURES:
        SERVICE_FEATURES = {"features": SERVICE_FEATURES}
        plugin_yaml.dump(SERVICE_FEATURES)
