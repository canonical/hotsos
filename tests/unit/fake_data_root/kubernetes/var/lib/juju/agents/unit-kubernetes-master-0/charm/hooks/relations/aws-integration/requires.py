"""
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
"""


import json
import string
from hashlib import sha256
from urllib.parse import urljoin
from urllib.request import urlopen

from charmhelpers.core import unitdata

from charms.reactive import Endpoint
from charms.reactive import when, when_not
from charms.reactive import clear_flag, toggle_flag


# block size to read data from AWS metadata service
# (realistically, just needs to be bigger than ~20 chars)
READ_BLOCK_SIZE = 2048


class AWSIntegrationRequires(Endpoint):
    """
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
    """
    # the IP is the AWS metadata service, documented here:
    # https://docs.aws.amazon.com/AWSEC2/latest/UserGuide/ec2-instance-metadata.html
    _metadata_url = 'http://169.254.169.254/latest/meta-data/'
    _instance_id_url = urljoin(_metadata_url, 'instance-id')
    _az_url = urljoin(_metadata_url, 'placement/availability-zone')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._instance_id = None
        self._region = None

    @property
    def _received(self):
        """
        Helper to streamline access to received data since we expect to only
        ever be connected to a single AWS integration application with a
        single unit.
        """
        return self.relations[0].joined_units.received

    @property
    def _to_publish(self):
        """
        Helper to streamline access to received data since we expect to only
        ever be connected to a single AWS integration application with a
        single unit.
        """
        return self.relations[0].to_publish

    @when('endpoint.{endpoint_name}.joined')
    def send_instance_info(self):
        self._to_publish['instance-id'] = self.instance_id
        self._to_publish['region'] = self.region

    @when('endpoint.{endpoint_name}.changed')
    def check_ready(self):
        completed = self._received.get('completed', {})
        actual_hash = completed.get(self.instance_id)
        # My middle name is ready. No, that doesn't sound right.
        # I eat ready for breakfast.
        toggle_flag(self.expand_name('ready'),
                    self._requested and actual_hash == self._expected_hash)
        clear_flag(self.expand_name('changed'))

    @when_not('endpoint.{endpoint_name}.joined')
    def remove_ready(self):
        clear_flag(self.expand_name('ready'))

    @property
    def instance_id(self):
        """
        This unit's instance-id.
        """
        if self._instance_id is None:
            cache_key = self.expand_name('instance-id')
            cached = unitdata.kv().get(cache_key)
            if cached:
                self._instance_id = cached
            else:
                with urlopen(self._instance_id_url) as fd:
                    self._instance_id = fd.read(READ_BLOCK_SIZE).decode('utf8')
                unitdata.kv().set(cache_key, self._instance_id)
        return self._instance_id

    @property
    def region(self):
        """
        The region this unit is in.
        """
        if self._region is None:
            cache_key = self.expand_name('region')
            cached = unitdata.kv().get(cache_key)
            if cached:
                self._region = cached
            else:
                with urlopen(self._az_url) as fd:
                    az = fd.read(READ_BLOCK_SIZE).decode('utf8')
                    self._region = az.rstrip(string.ascii_lowercase)
                unitdata.kv().set(cache_key, self._region)
        return self._region

    @property
    def _expected_hash(self):
        return sha256(json.dumps(dict(self._to_publish),
                                 sort_keys=True).encode('utf8')).hexdigest()

    @property
    def _requested(self):
        # whether or not a request has been issued
        return self._to_publish['requested']

    def _request(self, keyvals):
        self._to_publish.update(keyvals)
        self._to_publish['requested'] = True
        clear_flag(self.expand_name('ready'))

    def tag_instance(self, tags):
        """
        Request that the given tags be applied to this instance.

        # Parameters
        `tags` (dict): Mapping of tag names to values (or `None`).
        """
        self._request({'instance-tags': dict(tags)})

    def tag_instance_security_group(self, tags):
        """
        Request that the given tags be applied to this instance's
        machine-specific security group (firewall) created by Juju.

        # Parameters
        `tags` (dict): Mapping of tag names to values (or `None`).
        """
        self._request({'instance-security-group-tags': dict(tags)})

    def tag_instance_subnet(self, tags):
        """
        Request that the given tags be applied to this instance's subnet.

        # Parameters
        `tags` (dict): Mapping of tag names to values (or `None`).
        """
        self._request({'instance-subnet-tags': dict(tags)})

    def enable_acm_readonly(self):
        """
        Request readonly for ACM.
        """
        self._request({'enable-acm-readonly': True})

    def enable_acm_fullaccess(self):
        """
        Request fullaccess for ACM.
        """
        self._request({'enable-acm-fullaccess': True})

    def enable_instance_inspection(self):
        """
        Request the ability to inspect instances.
        """
        self._request({'enable-instance-inspection': True})

    def enable_network_management(self):
        """
        Request the ability to manage networking (firewalls, subnets, etc).
        """
        self._request({'enable-network-management': True})

    def enable_load_balancer_management(self):
        """
        Request the ability to manage load balancers.
        """
        self._request({'enable-load-balancer-management': True})

    def enable_block_storage_management(self):
        """
        Request the ability to manage block storage.
        """
        self._request({'enable-block-storage-management': True})

    def enable_dns_management(self):
        """
        Request the ability to manage DNS.
        """
        self._request({'enable-dns-management': True})

    def enable_object_storage_access(self, patterns=None):
        """
        Request the ability to access object storage.

        # Parameters
        `patterns` (list): If given, restrict access to the resources matching
            the patterns. If patterns do not start with the S3 ARN prefix
            (`arn:aws:s3:::`), it will be prepended.
        """
        if patterns:
            for i, pattern in enumerate(patterns):
                if not pattern.startswith('arn:aws:s3:::'):
                    patterns[i] = 'arn:aws:s3:::{}'.format(pattern)
        self._request({
            'enable-object-storage-access': True,
            'object-storage-access-patterns': patterns,
        })

    def enable_object_storage_management(self, patterns=None):
        """
        Request the ability to manage object storage.

        # Parameters
        `patterns` (list): If given, restrict management to the resources
            matching the patterns. If patterns do not start with the S3 ARN
            prefix (`arn:aws:s3:::`), it will be prepended.
        """
        if patterns:
            for i, pattern in enumerate(patterns):
                if not pattern.startswith('arn:aws:s3:::'):
                    patterns[i] = 'arn:aws:s3:::{}'.format(pattern)
        self._request({
            'enable-object-storage-management': True,
            'object-storage-management-patterns': patterns,
        })
