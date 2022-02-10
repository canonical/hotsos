<h1 id="provides">provides</h1>


This is the provides side of the interface layer, for use only by the Azure
integrator charm itself.

The flags that are set by the provides side of this interface are:

* **`endpoint.{endpoint_name}.requested`** This flag is set when there is
  a new or updated request by a remote unit for Azure integration features.
  The Azure integration charm should then iterate over each request, perform
  whatever actions are necessary to satisfy those requests, and then mark
  them as complete.

<h1 id="provides.AzureIntegrationProvides">AzureIntegrationProvides</h1>

```python
AzureIntegrationProvides(self, endpoint_name, relation_ids=None)
```

Example usage:

```python
from charms.reactive import when, endpoint_from_flag
from charms import layer

@when('endpoint.azure.requests-pending')
def handle_requests():
    azure = endpoint_from_flag('endpoint.azure.requests-pending')
    for request in azure.requests:
        if request.instance_tags:
            layer.azure.tag_instance(
                request.vm_name,
                request.resource_group,
                request.instance_tags)
        if request.requested_load_balancer_management:
            layer.azure.enable_load_balancer_management(
                request.charm,
                request.vm_name,
                request.resource_group,
            )
        # ...
    azure.mark_completed()
```

<h2 id="provides.AzureIntegrationProvides.relation_ids">relation_ids</h2>


A list of the IDs of all established relations.

<h2 id="provides.AzureIntegrationProvides.requests">requests</h2>


A list of the new or updated `IntegrationRequests` that
have been made.

<h2 id="provides.AzureIntegrationProvides.get_departed_charms">get_departed_charms</h2>

```python
AzureIntegrationProvides.get_departed_charms(self)
```

Get a list of all charms that have had all units depart since the
last time this was called.

<h2 id="provides.AzureIntegrationProvides.mark_completed">mark_completed</h2>

```python
AzureIntegrationProvides.mark_completed(self)
```

Mark all requests as completed and remove the `requests-pending` flag.

<h1 id="provides.IntegrationRequest">IntegrationRequest</h1>

```python
IntegrationRequest(self, unit)
```

A request for integration from a single remote unit.

<h2 id="provides.IntegrationRequest.application_name">application_name</h2>


The name of the application making the request.

<h2 id="provides.IntegrationRequest.charm">charm</h2>


The charm name reported for this request.

<h2 id="provides.IntegrationRequest.instance_tags">instance_tags</h2>


Mapping of tag names to values to apply to this instance.

<h2 id="provides.IntegrationRequest.is_changed">is_changed</h2>


Whether this request has changed since the last time it was
marked completed (if ever).

<h2 id="provides.IntegrationRequest.model_uuid">model_uuid</h2>


The UUID of the model containing the application making this request.

<h2 id="provides.IntegrationRequest.relation_id">relation_id</h2>


The ID of the relation for the unit making the request.

<h2 id="provides.IntegrationRequest.requested_block_storage_management">requested_block_storage_management</h2>


Flag indicating whether block storage management was requested.

<h2 id="provides.IntegrationRequest.requested_dns_management">requested_dns_management</h2>


Flag indicating whether DNS management was requested.

<h2 id="provides.IntegrationRequest.requested_instance_inspection">requested_instance_inspection</h2>


Flag indicating whether the ability to inspect instances was requested.

<h2 id="provides.IntegrationRequest.requested_network_management">requested_network_management</h2>


Flag indicating whether the ability to manage networking was requested.

<h2 id="provides.IntegrationRequest.requested_object_storage_access">requested_object_storage_access</h2>


Flag indicating whether object storage access was requested.

<h2 id="provides.IntegrationRequest.requested_object_storage_management">requested_object_storage_management</h2>


Flag indicating whether object storage management was requested.

<h2 id="provides.IntegrationRequest.requested_security_management">requested_security_management</h2>


Flag indicating whether security management was requested.

<h2 id="provides.IntegrationRequest.resource_group">resource_group</h2>


The resource group reported for this request.

<h2 id="provides.IntegrationRequest.unit_name">unit_name</h2>


The name of the unit making the request.

<h2 id="provides.IntegrationRequest.vm_id">vm_id</h2>


The instance ID reported for this request.

<h2 id="provides.IntegrationRequest.vm_name">vm_name</h2>


The instance name reported for this request.

<h2 id="provides.IntegrationRequest.mark_completed">mark_completed</h2>

```python
IntegrationRequest.mark_completed(self)
```

Mark this request as having been completed.

