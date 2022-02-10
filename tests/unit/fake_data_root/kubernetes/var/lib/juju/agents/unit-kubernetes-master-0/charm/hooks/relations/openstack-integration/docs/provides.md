<h1 id="provides">provides</h1>


This is the provides side of the interface layer, for use only by the
OpenStack integration charm itself.

The flags that are set by the provides side of this interface are:

* **`endpoint.{endpoint_name}.requested`** This flag is set when there is
  a new or updated request by a remote unit for OpenStack integration
  features.  The OpenStack integration charm should then iterate over each
  request, perform whatever actions are necessary to satisfy those requests,
  and then mark them as complete.

<h1 id="provides.OpenStackIntegrationProvides">OpenStackIntegrationProvides</h1>

```python
OpenStackIntegrationProvides(endpoint_name, relation_ids=None)
```

Example usage:

```python
from charms.reactive import when, endpoint_from_flag
from charms import layer

@when('endpoint.openstack.requests-pending')
def handle_requests():
    openstack = endpoint_from_flag('endpoint.openstack.requests-pending')
    for request in openstack.requests:
        request.set_credentials(layer.openstack.get_user_credentials())
    openstack.mark_completed()
```

<h2 id="provides.OpenStackIntegrationProvides.all_requests">all_requests</h2>


A list of all of the [`IntegrationRequests`](#provides.OpenStackIntegrationProvides.all_requests.IntegrationRequests) that have been made.

<h2 id="provides.OpenStackIntegrationProvides.new_requests">new_requests</h2>


A list of the new or updated [`IntegrationRequests`](#provides.OpenStackIntegrationProvides.new_requests.IntegrationRequests) that have been made.

<h2 id="provides.OpenStackIntegrationProvides.mark_completed">mark_completed</h2>

```python
OpenStackIntegrationProvides.mark_completed()
```

Mark all requests as completed and remove the `requests-pending` flag.

<h1 id="provides.IntegrationRequest">IntegrationRequest</h1>

```python
IntegrationRequest(unit)
```

A request for integration from a single remote unit.

<h2 id="provides.IntegrationRequest.has_credentials">has_credentials</h2>


Whether or not credentials have been set via `set_credentials`.

<h2 id="provides.IntegrationRequest.is_changed">is_changed</h2>


Whether this request has changed since the last time it was
marked completed (if ever).

<h2 id="provides.IntegrationRequest.set_credentials">set_credentials</h2>

```python
IntegrationRequest.set_credentials(auth_url,
                                   region,
                                   username,
                                   password,
                                   user_domain_name,
                                   project_domain_name,
                                   project_name,
                                   endpoint_tls_ca,
                                   version=None)
```

Set the credentials for this request.

<h2 id="provides.IntegrationRequest.set_lbaas_config">set_lbaas_config</h2>

```python
IntegrationRequest.set_lbaas_config(subnet_id,
                                    floating_network_id,
                                    lb_method,
                                    manage_security_groups,
                                    has_octavia=None)
```

Set the load-balancer-as-a-service config for this request.

<h2 id="provides.IntegrationRequest.set_block_storage_config">set_block_storage_config</h2>

```python
IntegrationRequest.set_block_storage_config(bs_version, trust_device_path,
                                            ignore_volume_az)
```

Set the block storage config for this request.

