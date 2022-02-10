#!/usr/bin/python

from charmhelpers.core import unitdata
from charms.reactive import Endpoint
from charms.reactive import when_any, when_not
from charms.reactive import set_state, remove_state

db = unitdata.kv()


class CNIPluginClient(Endpoint):
    def manage_flags(self):
        kubeconfig_hash = self.get_config().get("kubeconfig-hash")
        kubeconfig_hash_key = self.expand_name("{endpoint_name}.kubeconfig-hash")
        if kubeconfig_hash:
            set_state(self.expand_name("{endpoint_name}.kubeconfig.available"))
        if kubeconfig_hash != db.get(kubeconfig_hash_key):
            set_state(self.expand_name("{endpoint_name}.kubeconfig.changed"))
            db.set(kubeconfig_hash_key, kubeconfig_hash)

    @when_any("endpoint.{endpoint_name}.joined", "endpoint.{endpoint_name}.changed")
    def changed(self):
        """Indicate the relation is connected, and if the relation data is
        set it is also available."""
        set_state(self.expand_name("{endpoint_name}.connected"))
        remove_state(self.expand_name("endpoint.{endpoint_name}.changed"))

    @when_not("endpoint.{endpoint_name}.joined")
    def broken(self):
        """Indicate the relation is no longer available and not connected."""
        remove_state(self.expand_name("{endpoint_name}.connected"))

    def get_config(self):
        """Get the kubernetes configuration information."""
        return self.all_joined_units.received_raw

    def set_config(self, cidr, cni_conf_file):
        """Sets the CNI configuration information."""
        for relation in self.relations:
            relation.to_publish_raw.update(
                {"cidr": cidr, "cni-conf-file": cni_conf_file}
            )
