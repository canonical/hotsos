"""
This is the requires side of the interface layer, for use in charms that wish
to request docker-registry data. The data will be provided by the
docker-registry charm.
The flags that are set by the requires side of this interface are:
* **`endpoint.{endpoint_name}.joined`** This flag is set when the relation
  has been joined, and the charm should then use the methods documented below
  to request specific registry data.  This flag is automatically removed
  if the relation is broken.  It should not be removed by the charm.
* **`endpoint.{endpoint_name}.ready`** This flag is set once the requested
  config has been enabled for the registry instance on which the charm is
  running.  This flag is automatically removed if new integration features are
  requested.  It should not be removed by the charm.
"""


from charms.reactive import Endpoint
from charms.reactive import when, when_not
from charms.reactive import clear_flag, toggle_flag


class DockerRegistryRequires(Endpoint):
    """
    Interface to request registry config.
    Example usage:
    ```python
    from charms.reactive import when, endpoint_from_flag
    @when('endpoint.docker-registry.ready')
    def registry_ready():
        registry = endpoint_from_flag('endpoint.docker-registry.joined')
        update_config(registry.registry_netloc)
    ```
    """

    @property
    def _received(self):
        """
        Helper to streamline access to received data since we expect to only
        ever be connected to a single docker-registry application with a
        single unit.
        """
        return self.all_joined_units.received

    @property
    def _to_publish(self):
        """
        Helper to streamline access to received data since we expect to only
        ever be connected to a single docker-registry application with a
        single unit.
        """
        return self.relations[0].to_publish

    @when('endpoint.{endpoint_name}.changed')
    def check_ready(self):
        toggle_flag(self.expand_name('ready'), self.is_ready)
        clear_flag(self.expand_name('changed'))

    @when_not('endpoint.{endpoint_name}.joined')
    def remove_ready(self):
        clear_flag(self.expand_name('ready'))

    def has_auth_basic(self):
        """
        Whether or not the registry has basic/htpasswd auth.
        """
        return all(field is not None for field in [
            self.basic_password,
            self.basic_user,
        ])

    def has_custom_url(self):
        """
        Whether or not the registry has a custom URL.
        """
        return all(field is not None for field in [
            self.registry_url,
        ])

    def has_tls(self):
        """
        Whether or not the registry has TLS certificates configured.
        """
        return all(field is not None for field in [
            self.tls_ca,
        ])

    @property
    def is_ready(self):
        """
        Whether or not the request for this instance has been completed.
        """
        return all(field is not None for field in [
            self.registry_netloc,
        ])

    @property
    def basic_password(self):
        return self._received.get('basic_password')

    @property
    def basic_user(self):
        return self._received.get('basic_user')

    @property
    def registry_netloc(self):
        return self._received.get('registry_netloc')

    @property
    def registry_url(self):
        return self._received.get('registry_url')

    @property
    def tls_ca(self):
        return self._received.get('tls_ca')
