"""
This is the requires side of the interface layer, for use in charms that wish
to request integration with OpenStack native features.  The integration will be
provided by the OpenStack integration charm, which allows the requiring charm
to not require cloud credentials itself and not have a lot of OpenStack
specific API code.

The flags that are set by the requires side of this interface are:

* **`endpoint.{endpoint_name}.joined`** This flag is set when the relation
  has been joined, and the charm should then use the methods documented below
  to request specific OpenStack features.  This flag is automatically removed
  if the relation is broken.  It should not be removed by the charm.

* **`endpoint.{endpoint_name}.ready`** This flag is set once the requested
  features have been enabled for the OpenStack instance on which the charm is
  running.  This flag is automatically removed if new integration features are
  requested.  It should not be removed by the charm.

* **`endpoint.{endpoint_name}.ready.changed`** This flag is set if the data
  changes after the ready flag was set.  This flag should be removed by the
  charm once handled.
"""


from charms.reactive import Endpoint
from charms.reactive import when, when_not
from charms.reactive import set_flag, clear_flag, toggle_flag, is_flag_set
from charms.reactive import data_changed


class OpenStackIntegrationRequires(Endpoint):
    """
    Interface to request integration access.

    Note that due to resource limits and permissions granularity, policies are
    limited to being applied at the charm level.  That means that, if any
    permissions are requested (i.e., any of the enable methods are called),
    what is granted will be the sum of those ever requested by any instance of
    the charm on this cloud.

    Labels, on the other hand, will be instance specific.

    Example usage:

    ```python
    from charms.reactive import when, endpoint_from_flag

    @when('endpoint.openstack.ready')
    def openstack_integration_ready():
        openstack = endpoint_from_flag('endpoint.openstack.ready')
        update_config_enable_openstack(openstack)
    ```
    """

    @property
    def _received(self):
        """
        Helper to streamline access to received data since we expect to only
        ever be connected to a single OpenStack integration application with a
        single unit.
        """
        return self.relations[0].joined_units.received

    @property
    def _to_publish(self):
        """
        Helper to streamline access to received data since we expect to only
        ever be connected to a single OpenStack integration application with a
        single unit.
        """
        return self.relations[0].to_publish

    @when('endpoint.{endpoint_name}.changed')
    def check_ready(self):
        # My middle name is ready. No, that doesn't sound right.
        # I eat ready for breakfast.
        was_ready = is_flag_set(self.expand_name('ready'))
        toggle_flag(self.expand_name('ready'), self.is_ready)
        if self.is_ready and was_ready and self.is_changed:
            set_flag(self.expand_name('ready.changed'))
        clear_flag(self.expand_name('changed'))

    @when_not('endpoint.{endpoint_name}.joined')
    def remove_ready(self):
        clear_flag(self.expand_name('ready'))

    @property
    def is_ready(self):
        """
        Whether or not the request for this instance has been completed.
        """
        # Although more information can be passed, such as LBaaS access
        # the minimum needed to be considered ready is defined here
        return all(field is not None for field in [
            self.auth_url,
            self.username,
            self.password,
            self.user_domain_name,
            self.project_domain_name,
            self.project_name,
        ])

    @property
    def is_changed(self):
        """
        Whether or not the request for this instance has changed.
        """
        return data_changed(self.expand_name('all-data'), [
            self.auth_url,
            self.region,
            self.username,
            self.password,
            self.user_domain_name,
            self.project_domain_name,
            self.project_name,
            self.endpoint_tls_ca,
            self.subnet_id,
            self.floating_network_id,
            self.lb_method,
            self.manage_security_groups,
        ])

    @property
    def auth_url(self):
        """
        The authentication endpoint URL.
        """
        return self._received['auth_url']

    @property
    def region(self):
        """
        The region name.
        """
        return self._received['region']

    @property
    def username(self):
        """
        The username.
        """
        return self._received['username']

    @property
    def password(self):
        """
        The password.
        """
        return self._received['password']

    @property
    def user_domain_name(self):
        """
        The user domain name.
        """
        return self._received['user_domain_name']

    @property
    def project_domain_name(self):
        """
        The project domain name.
        """
        return self._received['project_domain_name']

    @property
    def project_name(self):
        """
        The project name, also known as the tenant ID.
        """
        return self._received['project_name']

    @property
    def endpoint_tls_ca(self):
        """
        Optional base64-encoded CA certificate for the authentication endpoint,
        or None.
        """
        return self._received['endpoint_tls_ca'] or None

    @property
    def version(self):
        """
        Optional version number for the APIs or None.
        """
        return self._received['version'] or None

    @property
    def subnet_id(self):
        """
        Optional subnet ID to work in, or None.
        """
        return self._received['subnet_id']

    @property
    def floating_network_id(self):
        """
        Optional floating network ID, or None.
        """
        return self._received['floating_network_id']

    @property
    def lb_method(self):
        """
        Optional load-balancer method, or None.
        """
        return self._received['lb_method']

    @property
    def manage_security_groups(self):
        """
        Whether or not the Load Balancer should automatically manage security
        group rules.

        Will be `True` or `False`.
        """
        return self._received['manage_security_groups'] or False

    @property
    def bs_version(self):
        """
        What block storage API version to use, `auto` if autodetection is
        desired, or `None` to use the default.
        """
        return self._received['bs_version']

    @property
    def trust_device_path(self):
        """
        Whether to trust the block device name provided by Ceph.

        Will be `True`, `False`, or `None`.
        """
        return self._received['trust_device_path']

    @property
    def ignore_volume_az(self):
        """
        Whether to ignore availability zones when attaching Cinder volumes.

        Will be `True`, `False`, or `None`.
        """
        return self._received['ignore_volume_az']

    @property
    def has_octavia(self):
        """
        Whether the underlying OpenStack supports Octavia instead of
        Neutron-based LBaaS.

        Will either be True, False, or None if it could not be determined for
        some reason (typically due to connecting to an older integrator charm).
        """
        return self._received['has_octavia']
