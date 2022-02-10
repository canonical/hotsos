"""
This is the requires side of the interface layer, for use in charms that
wish to request integration with GCP native features.  The integration will
be provided by the GCP integration charm, which allows the requiring charm
to not require cloud credentials itself and not have a lot of GCP specific
API code.

The flags that are set by the requires side of this interface are:

* **`endpoint.{endpoint_name}.joined`** This flag is set when the relation
  has been joined, and the charm should then use the methods documented below
  to request specific GCP features.  This flag is automatically removed if
  the relation is broken.  It should not be removed by the charm.

* **`endpoint.{endpoint_name}.ready`** This flag is set once the requested
  features have been enabled for the GCP instance on which the charm is
  running.  This flag is automatically removed if new integration features
  are requested.  It should not be removed by the charm.
"""


import os
import random
import string
from urllib.parse import urljoin
from urllib.request import urlopen, Request

from charmhelpers.core import hookenv
from charmhelpers.core import unitdata

from charms.reactive import Endpoint
from charms.reactive import when, when_not
from charms.reactive import clear_flag, toggle_flag


# block size to read data from GCP metadata service
# (realistically, just needs to be bigger than ~20 chars)
READ_BLOCK_SIZE = 2048


class GCPIntegrationRequires(Endpoint):
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

    @when('endpoint.gcp.joined')
    def request_gcp_integration():
        gcp = endpoint_from_flag('endpoint.gcp.joined')
        gcp.label_instance({
            'tag1': 'value1',
            'tag2': None,
        })
        gcp.request_load_balancer_management()
        # ...

    @when('endpoint.gcp.ready')
    def gcp_integration_ready():
        update_config_enable_gcp()
    ```
    """
    # https://cloud.google.com/compute/docs/storing-retrieving-metadata
    _metadata_url = 'http://metadata.google.internal/computeMetadata/v1/'
    _instance_url = urljoin(_metadata_url, 'instance/name')
    _zone_url = urljoin(_metadata_url, 'instance/zone')
    _metadata_headers = {'Metadata-Flavor': 'Google'}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._instance = None
        self._zone = None

    @property
    def _received(self):
        """
        Helper to streamline access to received data since we expect to only
        ever be connected to a single GCP integration application with a
        single unit.
        """
        return self.relations[0].joined_units.received

    @property
    def _to_publish(self):
        """
        Helper to streamline access to received data since we expect to only
        ever be connected to a single GCP integration application with a
        single unit.
        """
        return self.relations[0].to_publish

    @when('endpoint.{endpoint_name}.joined')
    def send_instance_info(self):
        self._to_publish['charm'] = hookenv.charm_name()
        self._to_publish['instance'] = self.instance
        self._to_publish['zone'] = self.zone
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
    def instance(self):
        """
        This unit's instance name.
        """
        if self._instance is None:
            cache_key = self.expand_name('instance')
            cached = unitdata.kv().get(cache_key)
            if cached:
                self._instance = cached
            else:
                req = Request(self._instance_url,
                              headers=self._metadata_headers)
                with urlopen(req) as fd:
                    instance = fd.read(READ_BLOCK_SIZE).decode('utf8').strip()
                    self._instance = instance
                unitdata.kv().set(cache_key, self._instance)
        return self._instance

    @property
    def zone(self):
        """
        The zone this unit is in.
        """
        if self._zone is None:
            cache_key = self.expand_name('zone')
            cached = unitdata.kv().get(cache_key)
            if cached:
                self._zone = cached
            else:
                req = Request(self._zone_url,
                              headers=self._metadata_headers)
                with urlopen(req) as fd:
                    zone = fd.read(READ_BLOCK_SIZE).decode('utf8').strip()
                    self._zone = zone.split('/')[-1]
                unitdata.kv().set(cache_key, self._zone)
        return self._zone

    @property
    def is_ready(self):
        """
        Whether or not the request for this instance has been completed.
        """
        requested = self._to_publish['requested']
        completed = self._received.get('completed', {}).get(self.instance)
        return requested and requested == completed

    @property
    def credentials(self):
        return self._received['credentials']

    def _request(self, keyvals):
        alphabet = string.ascii_letters + string.digits
        nonce = ''.join(random.choice(alphabet) for _ in range(8))
        self._to_publish.update(keyvals)
        self._to_publish['requested'] = nonce
        clear_flag(self.expand_name('ready'))

    def label_instance(self, labels):
        """
        Request that the given labels be applied to this instance.

        # Parameters
        `labels` (dict): Mapping of labels names to values.
        """
        self._request({'instance-labels': dict(labels)})

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
