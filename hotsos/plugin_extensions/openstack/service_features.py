from hotsos.core.plugins.openstack.common import OpenstackChecksBase

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
                        ]}}

# checked against neutron
DEFAULTS = {'neutron': {'dhcp-agent': {
                            'enable_metadata_network': False,
                            'enable_isolated_metadata': False}},
            'nova': {'main': {'live_migration_permit_auto_converge': False,
                              'live_migration_permit_post_copy': False}}}


class ServiceFeatureChecks(OpenstackChecksBase):

    def __summary_features(self):
        """
        This is used to display whether or not specific features are enabled.
        """
        _features = {}
        for service in FEATURES:
            svc_cfg = self.ost_projects.all[service].config
            if svc_cfg['main'].exists:
                if service not in _features:
                    _features[service] = {}

                if 'default' not in _features[service]:
                    _features[service]['main'] = {}

                debug_enabled = svc_cfg['main'].get('debug',
                                                    section="DEFAULT") or False
                _features[service]['main']['debug'] = debug_enabled

            for module in FEATURES[service]:
                module_features = {}
                cfg = svc_cfg[module]
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
                    if module in _features[service]:
                        _features[service][module].update(module_features)
                    else:
                        _features[service][module] = module_features

        if self.ssl_enabled:
            _features['api-ssl'] = True
        else:
            _features['api-ssl'] = False

        if _features:
            return _features
