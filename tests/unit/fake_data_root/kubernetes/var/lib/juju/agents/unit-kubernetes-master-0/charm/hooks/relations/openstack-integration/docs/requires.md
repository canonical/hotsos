<h1 id="requires">requires</h1>


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

<h1 id="requires.OpenStackIntegrationRequires">OpenStackIntegrationRequires</h1>

```python
OpenStackIntegrationRequires(endpoint_name, relation_ids=None)
```

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

<h2 id="requires.OpenStackIntegrationRequires.auth_url">auth_url</h2>


The authentication endpoint URL.

<h2 id="requires.OpenStackIntegrationRequires.bs_version">bs_version</h2>


What block storage API version to use, `auto` if autodetection is
desired, or `None` to use the default.

<h2 id="requires.OpenStackIntegrationRequires.endpoint_tls_ca">endpoint_tls_ca</h2>


Optional base64-encoded CA certificate for the authentication endpoint,
or None.

<h2 id="requires.OpenStackIntegrationRequires.floating_network_id">floating_network_id</h2>


Optional floating network ID, or None.

<h2 id="requires.OpenStackIntegrationRequires.has_octavia">has_octavia</h2>


Whether the underlying OpenStack supports Octavia instead of
Neutron-based LBaaS.

Will either be True, False, or None if it could not be determined for
some reason (typically due to connecting to an older integrator charm).

<h2 id="requires.OpenStackIntegrationRequires.ignore_volume_az">ignore_volume_az</h2>


Whether to ignore availability zones when attaching Cinder volumes.

Will be `True`, `False`, or `None`.

<h2 id="requires.OpenStackIntegrationRequires.is_changed">is_changed</h2>


Whether or not the request for this instance has changed.

<h2 id="requires.OpenStackIntegrationRequires.is_ready">is_ready</h2>


Whether or not the request for this instance has been completed.

<h2 id="requires.OpenStackIntegrationRequires.lb_method">lb_method</h2>


Optional load-balancer method, or None.

<h2 id="requires.OpenStackIntegrationRequires.manage_security_groups">manage_security_groups</h2>


Whether or not the Load Balancer should automatically manage security
group rules.

Will be `True` or `False`.

<h2 id="requires.OpenStackIntegrationRequires.password">password</h2>


The password.

<h2 id="requires.OpenStackIntegrationRequires.project_domain_name">project_domain_name</h2>


The project domain name.

<h2 id="requires.OpenStackIntegrationRequires.project_name">project_name</h2>


The project name, also known as the tenant ID.

<h2 id="requires.OpenStackIntegrationRequires.region">region</h2>


The region name.

<h2 id="requires.OpenStackIntegrationRequires.subnet_id">subnet_id</h2>


Optional subnet ID to work in, or None.

<h2 id="requires.OpenStackIntegrationRequires.trust_device_path">trust_device_path</h2>


Whether to trust the block device name provided by Ceph.

Will be `True`, `False`, or `None`.

<h2 id="requires.OpenStackIntegrationRequires.user_domain_name">user_domain_name</h2>


The user domain name.

<h2 id="requires.OpenStackIntegrationRequires.username">username</h2>


The username.

<h2 id="requires.OpenStackIntegrationRequires.version">version</h2>


Optional version number for the APIs or None.

