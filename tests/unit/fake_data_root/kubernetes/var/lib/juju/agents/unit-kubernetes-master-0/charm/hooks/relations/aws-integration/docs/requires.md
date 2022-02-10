<h1 id="requires">requires</h1>


This is the requires side of the interface layer, for use in charms that
wish to request integration with AWS native features.  The integration will
be provided by the AWS integration charm, which allows the requiring charm
to not require cloud credentials itself and not have a lot of AWS specific
API code.

The flags that are set by the requires side of this interface are:

* **`endpoint.{endpoint_name}.joined`** This flag is set when the relation
  has been joined, and the charm should then use the methods documented below
  to request specific AWS features.  This flag is automatically removed if
  the relation is broken.  It should not be removed by the charm.

* **`endpoint.{endpoint_name}.ready`** This flag is set once the requested
  features have been enabled for the AWS instance on which the charm is
  running.  This flag is automatically removed if new integration features
  are requested.  It should not be removed by the charm.

<h1 id="requires.AWSIntegrationRequires">AWSIntegrationRequires</h1>

```python
AWSIntegrationRequires(self, *args, **kwargs)
```

Example usage:

```python
from charms.reactive import when, endpoint_from_flag

@when('endpoint.aws.joined')
def request_aws_integration():
    aws = endpoint_from_flag('endpoint.aws.joined')
    aws.request_instance_tags({
        'tag1': 'value1',
        'tag2': None,
    })
    aws.request_load_balancer_management()
    # ...

@when('endpoint.aws.ready')
def aws_integration_ready():
    update_config_enable_aws()
```

<h2 id="requires.AWSIntegrationRequires.instance_id">instance_id</h2>


This unit's instance-id.

<h2 id="requires.AWSIntegrationRequires.region">region</h2>


The region this unit is in.

<h2 id="requires.AWSIntegrationRequires.tag_instance">tag_instance</h2>

```python
AWSIntegrationRequires.tag_instance(self, tags)
```

Request that the given tags be applied to this instance.

__Parameters__

- __`tags` (dict)__: Mapping of tag names to values (or `None`).

<h2 id="requires.AWSIntegrationRequires.tag_instance_security_group">tag_instance_security_group</h2>

```python
AWSIntegrationRequires.tag_instance_security_group(self, tags)
```

Request that the given tags be applied to this instance's
machine-specific security group (firewall) created by Juju.

__Parameters__

- __`tags` (dict)__: Mapping of tag names to values (or `None`).

<h2 id="requires.AWSIntegrationRequires.tag_instance_subnet">tag_instance_subnet</h2>

```python
AWSIntegrationRequires.tag_instance_subnet(self, tags)
```

Request that the given tags be applied to this instance's subnet.

__Parameters__

- __`tags` (dict)__: Mapping of tag names to values (or `None`).

<h2 id="requires.AWSIntegrationRequires.enable_acm_readonly">enable_acm_readonly</h2>

```python
AWSIntegrationRequires.enable_acm_readonly(self)
```

Request readonly for ACM.

<h2 id="requires.AWSIntegrationRequires.enable_acm_fullaccess">enable_acm_fullaccess</h2>

```python
AWSIntegrationRequires.enable_acm_fullaccess(self)
```

Request fullaccess for ACM.

<h2 id="requires.AWSIntegrationRequires.enable_instance_inspection">enable_instance_inspection</h2>

```python
AWSIntegrationRequires.enable_instance_inspection(self)
```

Request the ability to inspect instances.

<h2 id="requires.AWSIntegrationRequires.enable_network_management">enable_network_management</h2>

```python
AWSIntegrationRequires.enable_network_management(self)
```

Request the ability to manage networking (firewalls, subnets, etc).

<h2 id="requires.AWSIntegrationRequires.enable_load_balancer_management">enable_load_balancer_management</h2>

```python
AWSIntegrationRequires.enable_load_balancer_management(self)
```

Request the ability to manage load balancers.

<h2 id="requires.AWSIntegrationRequires.enable_block_storage_management">enable_block_storage_management</h2>

```python
AWSIntegrationRequires.enable_block_storage_management(self)
```

Request the ability to manage block storage.

<h2 id="requires.AWSIntegrationRequires.enable_dns_management">enable_dns_management</h2>

```python
AWSIntegrationRequires.enable_dns_management(self)
```

Request the ability to manage DNS.

<h2 id="requires.AWSIntegrationRequires.enable_object_storage_access">enable_object_storage_access</h2>

```python
AWSIntegrationRequires.enable_object_storage_access(self, patterns=None)
```

Request the ability to access object storage.

__Parameters__

- __`patterns` (list)__: If given, restrict access to the resources matching
    the patterns. If patterns do not start with the S3 ARN prefix
- __(`arn__:aws:s3:::`), it will be prepended.

<h2 id="requires.AWSIntegrationRequires.enable_object_storage_management">enable_object_storage_management</h2>

```python
AWSIntegrationRequires.enable_object_storage_management(self, patterns=None)
```

Request the ability to manage object storage.

__Parameters__

- __`patterns` (list)__: If given, restrict management to the resources
    matching the patterns. If patterns do not start with the S3 ARN
- __prefix (`arn__:aws:s3:::`), it will be prepended.

