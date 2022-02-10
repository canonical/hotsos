<h1 id="provides">provides</h1>


This is the provides side of the interface layer, for use only by the GCP
integration charm itself.

The flags that are set by the provides side of this interface are:

* **`endpoint.{endpoint_name}.requested`** This flag is set when there is
  a new or updated request by a remote unit for GCP integration features.
  The GCP integration charm should then iterate over each request, perform
  whatever actions are necessary to satisfy those requests, and then mark
  them as complete.

<h1 id="provides.GCPIntegrationProvides">GCPIntegrationProvides</h1>

```python
GCPIntegrationProvides(self, endpoint_name, relation_ids=None)
```

Example usage:

```python
from charms.reactive import when, endpoint_from_flag
from charms import layer

@when('endpoint.gcp.requests-pending')
def handle_requests():
    gcp = endpoint_from_flag('endpoint.gcp.requests-pending')
    for request in gcp.requests:
        if request.instance_labels:
            layer.gcp.label_instance(
                request.instance,
                request.zone,
                request.instance_labels)
        if request.requested_load_balancer_management:
            layer.gcp.enable_load_balancer_management(
                request.charm,
                request.instance,
                request.zone,
            )
        # ...
    gcp.mark_completed()
```

<h2 id="provides.GCPIntegrationProvides.relation_ids">relation_ids</h2>


A list of the IDs of all established relations.

<h2 id="provides.GCPIntegrationProvides.requests">requests</h2>


A list of the new or updated `IntegrationRequests` that
have been made.

<h2 id="provides.GCPIntegrationProvides.get_departed_charms">get_departed_charms</h2>

```python
GCPIntegrationProvides.get_departed_charms(self)
```

Get a list of all charms that have had all units depart since the
last time this was called.

<h2 id="provides.GCPIntegrationProvides.mark_completed">mark_completed</h2>

```python
GCPIntegrationProvides.mark_completed(self)
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

<h2 id="provides.IntegrationRequest.has_credentials">has_credentials</h2>


Whether or not credentials have been set via `set_credentials`.

<h2 id="provides.IntegrationRequest.instance">instance</h2>


The instance name reported for this request.

<h2 id="provides.IntegrationRequest.instance_labels">instance_labels</h2>


Mapping of label names to values to apply to this instance.

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

<h2 id="provides.IntegrationRequest.unit_name">unit_name</h2>


The name of the unit making the request.

<h2 id="provides.IntegrationRequest.zone">zone</h2>


The zone reported for this request.

<h2 id="provides.IntegrationRequest.mark_completed">mark_completed</h2>

```python
IntegrationRequest.mark_completed(self)
```

Mark this request as having been completed.

<h2 id="provides.IntegrationRequest.set_credentials">set_credentials</h2>

```python
IntegrationRequest.set_credentials(self, credentials)
```

Set the credentials for this request.

