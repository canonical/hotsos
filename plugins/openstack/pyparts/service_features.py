from core.plugins.openstack import (
    OpenstackChecksBase,
)

FEATURES = {'neutron': {'main': [
                            'availability_zone'],
                        'openvswitch-agent': [
                            'l2_population',
                            'firewall_driver'],
                        'l3-agent': [
                            'agent_mode',
                            'ovs_use_veth'],
                        'dhcp-agent': [
                            'enable_metadata_network',
                            'enable_isolated_metadata',
                            'ovs_use_veth']},
            'nova': {'main': [
                        'vcpu_pin_set',
                        'cpu_shared_set',
                        'cpu_dedicated_set',
                        'live_migration_permit_auto_converge',
                        'live_migration_permit_post_copy',
                        'live_migration_inbound_addr',
                        ]}}

# checked against neutron
DEFAULTS = {'neutron': {'dhcp-agent': {
                            'enable_metadata_network': False,
                            'enable_isolated_metadata': False}},
            'nova': {'main': {'live_migration_permit_auto_converge': False,
                              'live_migration_permit_post_copy': False}}}
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
                cfg = self.ost_projects.all[service].config[module]
                if not cfg.exists:
                    continue

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
        # Only run if we think Openstack is installed.
        if not self.openstack_installed:
            return

        self.get_service_features()
