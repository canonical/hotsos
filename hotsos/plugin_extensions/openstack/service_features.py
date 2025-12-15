from hotsos.core.log import log
from hotsos.core.plugins.openstack.common import (
    ApacheInfo,
    OpenstackBase,
    OpenStackChecks,
)
from hotsos.core.plugintools import (
    summary_entry,
    get_min_available_entry_index,
)

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


class ServiceFeatureChecks(OpenstackBase, OpenStackChecks):
    """ Implements Openstack service feature checks. """
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

    @summary_entry('features', get_min_available_entry_index() + 3)
    def summary_features(self):
        """
        For each OpenStack service running on this host, display common config
        and service specific features.
        """
        features = {}
        apache = ApacheInfo()
        installed = {name: service for name, service in
                     self.project_catalog.all.items()
                     if service.installed and 'main' in service.config and
                     service.config['main'].exists}
        for name, service in installed.items():
            debug_enabled = service.config['main'].get('debug',
                                                       section="DEFAULT")
            features[name] = {}
            if service.api_installed and apache.project_ssl_enabled(name):
                features[name]['api-ssl'] = True

            features[name]['main'] = {'debug': debug_enabled or False}
            if name not in FEATURES:
                continue

            for module, sections in FEATURES[name].items():
                log.debug("getting features for '%s.%s'", name, module)
                cfg = service.config[module]
                if not cfg.exists:
                    log.debug("%s not found - skipping features", cfg.path)
                    continue

                module_features = self._get_module_features(name, module,
                                                            sections, cfg)
                if not module_features:
                    continue

                if module in features[name]:
                    features[name][module].update(module_features)
                else:
                    features[name][module] = module_features

        return features or None
