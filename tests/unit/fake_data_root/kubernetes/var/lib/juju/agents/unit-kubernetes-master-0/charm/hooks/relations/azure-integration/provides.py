"""
This is the provides side of the interface layer, for use only by the Azure
integrator charm itself.

The flags that are set by the provides side of this interface are:

* **`endpoint.{endpoint_name}.requested`** This flag is set when there is
  a new or updated request by a remote unit for Azure integration features.
  The Azure integration charm should then iterate over each request, perform
  whatever actions are necessary to satisfy those requests, and then mark
  them as complete.
"""

from operator import attrgetter

from charms.reactive import Endpoint
from charms.reactive import when
from charms.reactive import toggle_flag, clear_flag


class AzureIntegrationProvides(Endpoint):
    """
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
    """

    @when('endpoint.{endpoint_name}.changed')
    def check_requests(self):
        toggle_flag(self.expand_name('requests-pending'),
                    len(self.requests) > 0)
        clear_flag(self.expand_name('changed'))

    @property
    def requests(self):
        """
        A list of the new or updated #IntegrationRequests that
        have been made.
        """
        if not hasattr(self, '_requests'):
            all_requests = [IntegrationRequest(unit)
                            for unit in self.all_joined_units]
            is_changed = attrgetter('is_changed')
            self._requests = list(filter(is_changed, all_requests))
        return self._requests

    @property
    def relation_ids(self):
        """
        A list of the IDs of all established relations.
        """
        return [relation.relation_id for relation in self.relations]

    def get_departed_charms(self):
        """
        Get a list of all charms that have had all units depart since the
        last time this was called.
        """
        joined_charms = {unit.received['charm']
                         for unit in self.all_joined_units
                         if unit.received['charm']}
        departed_charms = [unit.received['charm']
                           for unit in self.all_departed_units
                           if unit.received['charm'] not in joined_charms]
        self.all_departed_units.clear()
        return departed_charms

    def mark_completed(self):
        """
        Mark all requests as completed and remove the `requests-pending` flag.
        """
        for request in self.requests:
            request.mark_completed()
        clear_flag(self.expand_name('requests-pending'))
        self._requests = []


class IntegrationRequest:
    """
    A request for integration from a single remote unit.
    """
    def __init__(self, unit):
        self._unit = unit

    @property
    def _to_publish(self):
        return self._unit.relation.to_publish

    @property
    def _completed(self):
        return self._to_publish.get('completed', {})

    @property
    def _requested(self):
        return self._unit.received['requested']

    @property
    def is_changed(self):
        """
        Whether this request has changed since the last time it was
        marked completed (if ever).
        """
        if not all([self.charm, self.vm_id, self.vm_name,
                    self.resource_group, self._requested]):
            return False
        return self._completed.get(self.vm_id) != self._requested

    def mark_completed(self):
        """
        Mark this request as having been completed.
        """
        completed = self._completed
        completed[self.vm_id] = self._requested
        self._to_publish['completed'] = completed  # have to explicitly update

    def send_additional_metadata(self, resource_group_location,
                                 vnet_name, vnet_resource_group,
                                 subnet_name, security_group_name,
                                 security_group_resource_group,
                                 use_managed_identity=True, aad_client=None,
                                 aad_secret=None, tenant_id=None):
        self._to_publish.update({
            'resource-group-location': resource_group_location,
            'vnet-name': vnet_name,
            'vnet-resource-group': vnet_resource_group,
            'subnet-name': subnet_name,
            'security-group-name': security_group_name,
            'security-group-resource-group': security_group_resource_group,
            'use-managed-identity': use_managed_identity,
            'aad-client': aad_client,
            'aad-client-secret': aad_secret,
            'tenant-id': tenant_id
        })

    @property
    def relation_id(self):
        """
        The ID of the relation for the unit making the request.
        """
        return self._unit.relation.relation_id

    @property
    def unit_name(self):
        """
        The name of the unit making the request.
        """
        return self._unit.unit_name

    @property
    def application_name(self):
        """
        The name of the application making the request.
        """
        return self._unit.application_name

    @property
    def charm(self):
        """
        The charm name reported for this request.
        """
        return self._unit.received['charm']

    @property
    def vm_id(self):
        """
        The instance ID reported for this request.
        """
        return self._unit.received['vm-id']

    @property
    def vm_name(self):
        """
        The instance name reported for this request.
        """
        return self._unit.received['vm-name']

    @property
    def resource_group(self):
        """
        The resource group reported for this request.
        """
        return self._unit.received['res-group']

    @property
    def model_uuid(self):
        """
        The UUID of the model containing the application making this request.
        """
        return self._unit.received['model-uuid']

    @property
    def instance_tags(self):
        """
        Mapping of tag names to values to apply to this instance.
        """
        # uses dict() here to make a copy, just to be safe
        return dict(self._unit.received.get('instance-tags', {}))

    @property
    def requested_instance_inspection(self):
        """
        Flag indicating whether the ability to inspect instances was requested.
        """
        return bool(self._unit.received['enable-instance-inspection'])

    @property
    def requested_network_management(self):
        """
        Flag indicating whether the ability to manage networking was requested.
        """
        return bool(self._unit.received['enable-network-management'])

    @property
    def requested_loadbalancer_management(self):
        """
        Flag indicating whether the ability to manage networking was requested.
        """
        return bool(self._unit.received['enable-loadbalancer-management'])


    @property
    def requested_security_management(self):
        """
        Flag indicating whether security management was requested.
        """
        return bool(self._unit.received['enable-security-management'])

    @property
    def requested_block_storage_management(self):
        """
        Flag indicating whether block storage management was requested.
        """
        return bool(self._unit.received['enable-block-storage-management'])

    @property
    def requested_dns_management(self):
        """
        Flag indicating whether DNS management was requested.
        """
        return bool(self._unit.received['enable-dns-management'])

    @property
    def requested_object_storage_access(self):
        """
        Flag indicating whether object storage access was requested.
        """
        return bool(self._unit.received['enable-object-storage-access'])

    @property
    def requested_object_storage_management(self):
        """
        Flag indicating whether object storage management was requested.
        """
        return bool(self._unit.received['enable-object-storage-management'])
