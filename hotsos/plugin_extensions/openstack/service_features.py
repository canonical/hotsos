from hotsos.core.log import log
from hotsos.core.plugins.openstack.common import OpenstackChecksBase

FEATURES = {'neutron': {
                'main': {
                    'DEFAULT': ['global_physnet_mtu'],
                    'AGENT': ['availability_zone']},
                'openvswitch-agent': {
                    'AGENT': ['l2_population'],
                    'SECURITYGROUP': ['firewall_driver']},
                'l3-agent': {
                    'DEFAULT': ['agent_mode', 'ovs_use_veth']},
                'dhcp-agent': {
                    'DEFAULT': ['enable_metadata_network',
                                'enable_isolated_metadata',
                                'ovs_use_veth']},
                'ovn': {
                    'DEFAULT': ['enable_distributed_floating_ip']},
                'ml2': {
                    'ML2': ['path_mtu']}},
            'nova': {
                'main': {
                    'DEFAULT': ['vcpu_pin_set'],
                    'compute': [
                                'cpu_shared_set',
                                'cpu_dedicated_set'],
                    'libvirt': ['cpu_mode',
                                'cpu_model',
                                'cpu_model_extra_flags',
                                'live_migration_permit_auto_converge',
                                'live_migration_permit_post_copy']}}}

# checked against neutron
DEFAULTS = {'neutron': {'dhcp-agent': {
                            'enable_metadata_network': False,
                            'enable_isolated_metadata': False}},
            'nova': {'main': {'live_migration_permit_auto_converge': False,
                              'live_migration_permit_post_copy': False}}}


class ServiceFeatureChecks(OpenstackChecksBase):
    summary_part_index = 5

    @staticmethod
    def _get_module_features(service, module, sections, cfg):
        """
        Get dictionary of features for this service module and whether they are
        enabled/disabled.

        @param service: name of Openstack service
        @param module: service submodule (agent)
        @param sections: config sections
        @param cfg: OpenstackConfig object
        """
        module_features = {}
        for section, keys in sections.items():
            for key in keys:
                val = cfg.get(key, section=section)
                if val is not None:
                    module_features[key] = val

                if key in module_features or service not in DEFAULTS:
                    continue

                if (module not in DEFAULTS[service] or
                        key not in DEFAULTS[service][module]):
                    continue

                module_features[key] = DEFAULTS[service][module][key]

        return module_features

    def __7_summary_features(self):
        """
        This is used to display whether or not specific features are enabled.
        """
        features = {}
        for service, modules in FEATURES.items():
            svc_cfg = self.ost_projects.all[service].config
            if not svc_cfg['main'].exists:
                continue

            dbg_enabled = svc_cfg['main'].get('debug', section="DEFAULT")
            features[service] = {'main': {'debug': dbg_enabled or False}}

            for module, sections in modules.items():
                log.debug("getting features for '%s.%s'", service, module)
                cfg = svc_cfg[module]
                if not cfg.exists:
                    log.debug("%s not found - skipping features", cfg.path)
                    continue

                module_features = self._get_module_features(service, module,
                                                            sections, cfg)
                if not module_features:
                    continue

                if module in features[service]:
                    features[service][module].update(module_features)
                else:
                    features[service][module] = module_features

        if self.ssl_enabled is not None:
            features['api-ssl'] = self.ssl_enabled or False

        if features:
            return features
