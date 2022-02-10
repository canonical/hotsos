# Overview

This interface handles the communication with the hacluster subordinate
charm using the `ha` interface protocol.

# Usage

## Requires

The interface layer will set the following reactive states, as appropriate:

  * `{relation_name}.connected` The relation is established and ready for
    the local charm to configure the hacluster subordinate charm. The
    configuration of the resources to manage for the hacluster charm
    can be managed via one of the following methods:

    * `manage_resources` method
    * `bind_on` method

    Configuration of the managed resources within the hacluster can be
    managed by passing `common.CRM` object definitions to the
    `manage_resources` method.

  * `{relation_name}.available` The hacluster is up and ready.

For example:
```python
from charms.reactive import when, when_not
from charms.reactive import set_state, remove_state

from relations.hacluster.common import CRM


@when('ha.connected')
def cluster_connected(hacluster):

    resources = CRM()
    resources.primitive('res_vip', 'ocf:IPAddr2',
                        params='ip=10.0.3.100 nic=eth0',
                        op='monitor interval="10s"')
    resources.clone('cl_res_vip', 'res_vip')

    hacluster.bind_on(iface='eth0', mcastport=4430)
    hacluster.manage_resources(resources)
```

Additionally, for more code clarity a custom object implements the interface
defined in common.ResourceDescriptor can be used to simplify the code for
reuse.

For example:
```python
import ipaddress

from relation.hacluster.common import CRM
from relation.hacluster.common import ResourceDescriptor

class VirtualIP(ResourceDescriptor):
    def __init__(self, vip, nic='eth0'):
        self.vip = vip
        self.nic = 'eth0'

    def configure_resource(self, crm):
        ipaddr = ipaddress.ip_address(self.vip)
        if isinstance(ipaddr, ipaddress.IPv4Address):
            res_type = 'ocf:heartbeat:IPAddr2'
            res_parms = 'ip={ip} nic={nic}'.format(ip=self.vip,
                                                   nic=self.nic)
        else:
            res_type = 'ocf:heartbeat:IPv6addr'
            res_params = 'ipv6addr={ip} nic={nic}'.format(ip=self.vip,
                                                          nic=self.nic)

        crm.primitive('res_vip', res_type, params=res_params,
                      op='monitor interval="10s"')
        crm.clone('cl_res_vip', 'res_vip')
```

Once the VirtualIP class above has been defined in charm code, it can make
the code a bit cleaner. The example above can thusly be written as:

```python
@when('ha.connected')
def cluster_connected(hacluster):
    resources = CRM()
    resources.add(VirtualIP('10.0.3.100'))

    hacluster.bind_on(iface='eth0', mcastport=4430)
    hacluster.manage_resources(resources)
```
