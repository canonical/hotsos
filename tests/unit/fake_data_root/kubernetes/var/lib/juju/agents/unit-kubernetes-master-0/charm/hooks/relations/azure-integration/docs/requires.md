<h1 id="requires">requires</h1>


This is the requires side of the interface layer, for use in charms that
wish to request integration with Azure native features.  The integration will
be provided by the Azure integrator charm, which allows the requiring charm
to not require cloud credentials itself and not have a lot of Azure specific
API code.

The flags that are set by the requires side of this interface are:

* **`endpoint.{endpoint_name}.joined`** This flag is set when the relation
  has been joined, and the charm should then use the methods documented below
  to request specific Azure features.  This flag is automatically removed if
  the relation is broken.  It should not be removed by the charm.

* **`endpoint.{endpoint_name}.ready`** This flag is set once the requested
  features have been enabled for the Azure instance on which the charm is
  running.  This flag is automatically removed if new integration features
  are requested.  It should not be removed by the charm.

<h1 id="requires.AzureIntegrationRequires">AzureIntegrationRequires</h1>

```python
AzureIntegrationRequires(self, *args, **kwargs)
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

@when('endpoint.azure.joined')
def request_azure_integration():
    azure = endpoint_from_flag('endpoint.azure.joined')
    azure.tag_instance({
        'tag1': 'value1',
        'tag2': None,
    })
    azure.request_load_balancer_management()
    # ...

@when('endpoint.azure.ready')
def azure_integration_ready():
    update_config_enable_azure()
```

<h2 id="requires.AzureIntegrationRequires.is_ready">is_ready</h2>


Whether or not the request for this instance has been completed.

<h2 id="requires.AzureIntegrationRequires.resource_group">resource_group</h2>


The resource group this unit is in.

<h2 id="requires.AzureIntegrationRequires.vm_id">vm_id</h2>


This unit's instance ID.

<h2 id="requires.AzureIntegrationRequires.vm_name">vm_name</h2>


This unit's instance name.

<h2 id="requires.AzureIntegrationRequires.tag_instance">tag_instance</h2>

```python
AzureIntegrationRequires.tag_instance(self, tags)
```

Request that the given tags be applied to this instance.

__Parameters__

- __`tags` (dict)__: Mapping of tags names to values.

<h2 id="requires.AzureIntegrationRequires.enable_instance_inspection">enable_instance_inspection</h2>

```python
AzureIntegrationRequires.enable_instance_inspection(self)
```

Request the ability to inspect instances.

<h2 id="requires.AzureIntegrationRequires.enable_network_management">enable_network_management</h2>

```python
AzureIntegrationRequires.enable_network_management(self)
```

Request the ability to manage networking.

<h2 id="requires.AzureIntegrationRequires.enable_security_management">enable_security_management</h2>

```python
AzureIntegrationRequires.enable_security_management(self)
```

Request the ability to manage security (e.g., firewalls).

<h2 id="requires.AzureIntegrationRequires.enable_block_storage_management">enable_block_storage_management</h2>

```python
AzureIntegrationRequires.enable_block_storage_management(self)
```

Request the ability to manage block storage.

<h2 id="requires.AzureIntegrationRequires.enable_dns_management">enable_dns_management</h2>

```python
AzureIntegrationRequires.enable_dns_management(self)
```

Request the ability to manage DNS.

<h2 id="requires.AzureIntegrationRequires.enable_object_storage_access">enable_object_storage_access</h2>

```python
AzureIntegrationRequires.enable_object_storage_access(self)
```

Request the ability to access object storage.

<h2 id="requires.AzureIntegrationRequires.enable_object_storage_management">enable_object_storage_management</h2>

```python
AzureIntegrationRequires.enable_object_storage_management(self)
```

Request the ability to manage object storage.

