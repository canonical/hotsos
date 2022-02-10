#!/usr/bin/python

from charmhelpers.core import hookenv
from charmhelpers.core.host import file_hash
from charms.layer.kubernetes_common import kubeclientconfig_path
from charms.reactive import Endpoint
from charms.reactive import toggle_flag, clear_flag


class CNIPluginProvider(Endpoint):
    def manage_flags(self):
        toggle_flag(self.expand_name("{endpoint_name}.connected"), self.is_joined)
        toggle_flag(
            self.expand_name("{endpoint_name}.available"), self.config_available()
        )
        clear_flag(self.expand_name("endpoint.{endpoint_name}.changed"))

    def config_available(self):
        """Ensures all config from the CNI plugin is available."""
        goal_state = hookenv.goal_state()
        related_apps = [
            app
            for app in goal_state.get("relations", {}).get(self.endpoint_name, "")
            if "/" not in app
        ]
        if not related_apps:
            return False
        configs = self.get_configs()
        return all(
            "cidr" in config and "cni-conf-file" in config
            for config in [configs.get(related_app, {}) for related_app in related_apps]
        )

    def get_config(self, default=None):
        """Get CNI config for one related application.

        If default is specified, and there is a related application with a
        matching name, then that application is chosen. Otherwise, the
        application is chosen alphabetically.

        Whichever application is chosen, that application's CNI config is
        returned.
        """
        configs = self.get_configs()
        if not configs:
            return {}
        elif default and default not in configs:
            msg = "relation not found for default CNI %s, ignoring" % default
            hookenv.log(msg, level="WARN")
            return self.get_config()
        elif default:
            return configs.get(default, {})
        else:
            return configs.get(sorted(configs)[0], {})

    def get_configs(self):
        """Get CNI configs for all related applications.

        This returns a mapping of application names to CNI configs. Here's an
        example return value:
        {
            'flannel': {
                'cidr': '10.1.0.0/16',
                'cni-conf-file': '10-flannel.conflist'
            },
            'calico': {
                'cidr': '192.168.0.0/16',
                'cni-conf-file': '10-calico.conflist'
            }
        }
        """
        return {
            relation.application_name: relation.joined_units.received_raw
            for relation in self.relations
            if relation.application_name
        }

    def notify_kubeconfig_changed(self):
        kubeconfig_hash = file_hash(kubeclientconfig_path)
        for relation in self.relations:
            relation.to_publish_raw.update({"kubeconfig-hash": kubeconfig_hash})
