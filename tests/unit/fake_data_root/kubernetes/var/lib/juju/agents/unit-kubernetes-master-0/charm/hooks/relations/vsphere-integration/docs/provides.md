<h1 id="provides">provides</h1>


This is the provides side of the interface layer, for use only by the
vSphere integration charm itself.

The flags that are set by the provides side of this interface are:

* **`endpoint.{endpoint_name}.requested`** This flag is set when there is
  a new or updated request by a remote unit for vSphere integration
  features.  The vSphere integration charm should then iterate over each
  request, perform whatever actions are necessary to satisfy those requests,
  and then mark them as complete.

<h1 id="provides.VsphereIntegrationProvides">VsphereIntegrationProvides</h1>

```python
VsphereIntegrationProvides(self, endpoint_name, relation_ids=None)
```

Example usage:

```python
from charms.reactive import when, endpoint_from_flag
from charms import layer

@when('endpoint.vsphere.requests-pending')
def handle_requests():
    vsphere = endpoint_from_flag('endpoint.vsphere.requests-pending')
    for request in vsphere.requests:
        request.set_credentials(layer.vsphere.get_user_credentials())
    vsphere.mark_completed()
```

<h2 id="provides.VsphereIntegrationProvides.requests">requests</h2>


A list of the new or updated `IntegrationRequests` that
have been made.

<h2 id="provides.VsphereIntegrationProvides.mark_completed">mark_completed</h2>

```python
VsphereIntegrationProvides.mark_completed(self)
```

Mark all requests as completed and remove the `requests-pending` flag.

<h1 id="provides.IntegrationRequest">IntegrationRequest</h1>

```python
IntegrationRequest(self, unit)
```

A request for integration from a single remote unit.

<h2 id="provides.IntegrationRequest.has_credentials">has_credentials</h2>


Whether or not credentials have been set via `set_credentials`.

<h2 id="provides.IntegrationRequest.is_changed">is_changed</h2>


Whether this request has changed since the last time it was
marked completed (if ever).

<h2 id="provides.IntegrationRequest.set_credentials">set_credentials</h2>

```python
IntegrationRequest.set_credentials(self, vsphere_ip, user, password, datacenter, datastore)
```

Set the credentials for this request.
