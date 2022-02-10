"""
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
"""


import json
import os
import random
import string
from urllib.request import urlopen, Request

from charmhelpers.core import hookenv
from charmhelpers.core import unitdata

from charms.reactive import Endpoint
from charms.reactive import when, when_not
from charms.reactive import clear_flag, toggle_flag


# block size to read data from Azure metadata service
# (realistically, just needs to be bigger than ~20 chars)
READ_BLOCK_SIZE = 2048


class AzureIntegrationRequires(Endpoint):
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
    """
    # https://docs.microsoft.com/en-us/azure/virtual-machines/windows/instance-metadata-service
    _metadata_url = 'http://169.254.169.254/metadata/instance?api-version=2017-12-01'  # noqa
    _metadata_headers = {'Metadata': 'true'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._vm_metadata = None

    @property
    def _received(self):
        """
        Helper to streamline access to received data since we expect to only
        ever be connected to a single Azure integration application with a
        single unit.
        """
        return self.relations[0].joined_units.received

    @property
    def _to_publish(self):
        """
        Helper to streamline access to received data since we expect to only
        ever be connected to a single Azure integration application with a
        single unit.
        """
        return self.relations[0].to_publish

    @when('endpoint.{endpoint_name}.joined')
    def send_instance_info(self):
        self._to_publish['charm'] = hookenv.charm_name()
        self._to_publish['vm-id'] = self.vm_id
        self._to_publish['vm-name'] = self.vm_name
        self._to_publish['res-group'] = self.resource_group
        self._to_publish['model-uuid'] = os.environ['JUJU_MODEL_UUID']

    @when('endpoint.{endpoint_name}.changed')
    def check_ready(self):
        # My middle name is ready. No, that doesn't sound right.
        # I eat ready for breakfast.
        toggle_flag(self.expand_name('ready'), self.is_ready)
        clear_flag(self.expand_name('changed'))

    @when_not('endpoint.{endpoint_name}.joined')
    def remove_ready(self):
        clear_flag(self.expand_name('ready'))

    @property
    def vm_metadata(self):
        if self._vm_metadata is None:
            cache_key = self.expand_name('vm-metadata')
            cached = unitdata.kv().get(cache_key)
            if cached:
                self._vm_metadata = cached
            else:
                req = Request(self._metadata_url,
                              headers=self._metadata_headers)
                with urlopen(req) as fd:
                    metadata = fd.read(READ_BLOCK_SIZE).decode('utf8').strip()
                    self._vm_metadata = json.loads(metadata)
                unitdata.kv().set(cache_key, self._vm_metadata)
        return self._vm_metadata

    @property
    def vm_id(self):
        """
        This unit's instance ID.
        """
        return self.vm_metadata['compute']['vmId']

    @property
    def vm_name(self):
        """
        This unit's instance name.
        """
        return self.vm_metadata['compute']['name']

    @property
    def vm_location(self):
        """
        The location (region) the instance is running in.
        """
        return self.vm_metadata['compute']['location']

    @property
    def resource_group(self):
        """
        The resource group this unit is in.
        """
        return self.vm_metadata['compute']['resourceGroupName']

    @property
    def resource_group_location(self):
        """
        The location (region) the resource group is in.
        """
        return self._received['resource-group-location']

    @property
    def subscription_id(self):
        """
        The ID of the Azure Subscription this unit is in.
        """
        return self.vm_metadata['compute']['subscriptionId']

    @property
    def vnet_name(self):
        """
        The name of the virtual network the instance is in.
        """
        return self._received['vnet-name']

    @property
    def vnet_resource_group(self):
        """
        The name of the virtual network the instance is in.
        """
        return self._received['vnet-resource-group']

    @property
    def subnet_name(self):
        """
        The name of the subnet the instance is in.
        """
        return self._received['subnet-name']

    @property
    def security_group_name(self):
        """
        The name of the security group attached to the cluster's subnet.
        """
        return self._received['security-group-name']

    @property
    def is_ready(self):
        """
        Whether or not the request for this instance has been completed.
        """
        requested = self._to_publish['requested']
        completed = self._received.get('completed', {}).get(self.vm_id)
        return requested and requested == completed

    @property
    def security_group_resource_group(self):
        return self._received['security-group-resource-group']

    @property
    def managed_identity(self):
        return self._received['use-managed-identity']

    @property
    def aad_client_id(self):
        return self._received['aad-client']

    @property
    def aad_client_secret(self):
        return self._received['aad-client-secret']
    
    @property
    def tenant_id(self):
        return self._received['tenant-id']

    def _request(self, keyvals):
        alphabet = string.ascii_letters + string.digits
        nonce = ''.join(random.choice(alphabet) for _ in range(8))
        self._to_publish.update(keyvals)
        self._to_publish['requested'] = nonce
        clear_flag(self.expand_name('ready'))

    def tag_instance(self, tags):
        """
        Request that the given tags be applied to this instance.

        # Parameters
        `tags` (dict): Mapping of tags names to values.
        """
        self._request({'instance-tags': dict(tags)})

    def enable_instance_inspection(self):
        """
        Request the ability to inspect instances.
        """
        self._request({'enable-instance-inspection': True})

    def enable_network_management(self):
        """
        Request the ability to manage networking.
        """
        self._request({'enable-network-management': True})

    def enable_loadbalancer_management(self):
        """
        Request the ability to manage networking.
        """
        self._request({'enable-loadbalancer-management': True})


    def enable_security_management(self):
        """
        Request the ability to manage security (e.g., firewalls).
        """
        self._request({'enable-security-management': True})

    def enable_block_storage_management(self):
        """
        Request the ability to manage block storage.
        """
        self._request({'enable-block-storage-management': True})

    def enable_dns_management(self):
        """
        Request the ability to manage DNS.
        """
        self._request({'enable-dns': True})

    def enable_object_storage_access(self):
        """
        Request the ability to access object storage.
        """
        self._request({'enable-object-storage-access': True})

    def enable_object_storage_management(self):
        """
        Request the ability to manage object storage.
        """
        self._request({'enable-object-storage-management': True})


