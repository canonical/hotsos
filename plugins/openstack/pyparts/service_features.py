import os

from core import constants
from core.plugins.openstack import (
    CONFIG_FILES,
    OpenstackChecksBase,
    OpenstackConfig,
)

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
YAML_PRIORITY = 5


class ServiceFeatureChecks(OpenstackChecksBase):

    @property
    def output(self):
        if self._output:
            return {"features": self._output}

    def get_service_features(self):
        """
        This is used to display whether or not specific features are enabled.
        """
        for service in FEATURES:
            for module in FEATURES[service]:
                module_features = {}
                path = os.path.join(constants.DATA_ROOT,
                                    CONFIG_FILES[service][module])
                cfg = OpenstackConfig(path)
                if not cfg.exists:
                    return

                for key in FEATURES[service][module]:
                    val = cfg.get(key)
                    if val is not None:
                        module_features[key] = val

                    if key not in module_features:
                        if key in DEFAULTS.get(service, {}).get(module, {}):
                            default = DEFAULTS[service][module][key]
                            module_features[key] = default

                # TODO: only include modules for which there is an actual agent
                #       installed since otherwise their config is irrelevant.
                if module_features:
                    if service not in self._output:
                        self._output[service] = {}

                    self._output[service][module] = module_features

    def __call__(self):
        self.get_service_features()
