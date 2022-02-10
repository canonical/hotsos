# Copyright 2014-2021 Canonical Limited.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# This file is sourced from lp:openstack-charm-helpers
#
# Authors:
#  James Page <james.page@ubuntu.com>
#  Adam Gandelman <adamg@ubuntu.com>
#

import collections
import errno
import hashlib
import math
import six

import os
import shutil
import json
import time
import uuid

from subprocess import (
    check_call,
    check_output,
    CalledProcessError,
)
from charmhelpers import deprecate
from charmhelpers.core.hookenv import (
    application_name,
    config,
    service_name,
    local_unit,
    relation_get,
    relation_ids,
    relation_set,
    related_units,
    log,
    DEBUG,
    INFO,
    WARNING,
    ERROR,
)
from charmhelpers.core.host import (
    mount,
    mounts,
    service_start,
    service_stop,
    service_running,
    umount,
    cmp_pkgrevno,
)
from charmhelpers.fetch import (
    apt_install,
)
from charmhelpers.core.unitdata import kv

from charmhelpers.core.kernel import modprobe
from charmhelpers.contrib.openstack.utils import config_flags_parser

KEYRING = '/etc/ceph/ceph.client.{}.keyring'
KEYFILE = '/etc/ceph/ceph.client.{}.key'

CEPH_CONF = """[global]
auth supported = {auth}
keyring = {keyring}
mon host = {mon_hosts}
log to syslog = {use_syslog}
err to syslog = {use_syslog}
clog to syslog = {use_syslog}
"""

# The number of placement groups per OSD to target for placement group
# calculations. This number is chosen as 100 due to the ceph PG Calc
# documentation recommending to choose 100 for clusters which are not
# expected to increase in the foreseeable future. Since the majority of the
# calculations are done on deployment, target the case of non-expanding
# clusters as the default.
DEFAULT_PGS_PER_OSD_TARGET = 100
DEFAULT_POOL_WEIGHT = 10.0
LEGACY_PG_COUNT = 200
DEFAULT_MINIMUM_PGS = 2
AUTOSCALER_DEFAULT_PGS = 32


class OsdPostUpgradeError(Exception):
    """Error class for OSD post-upgrade operations."""
    pass


class OSDSettingConflict(Exception):
    """Error class for conflicting osd setting requests."""
    pass


class OSDSettingNotAllowed(Exception):
    """Error class for a disallowed setting."""
    pass


OSD_SETTING_EXCEPTIONS = (OSDSettingConflict, OSDSettingNotAllowed)

OSD_SETTING_WHITELIST = [
    'osd heartbeat grace',
    'osd heartbeat interval',
]


def _order_dict_by_key(rdict):
    """Convert a dictionary into an OrderedDict sorted by key.

    :param rdict: Dictionary to be ordered.
    :type rdict: dict
    :returns: Ordered Dictionary.
    :rtype: collections.OrderedDict
    """
    return collections.OrderedDict(sorted(rdict.items(), key=lambda k: k[0]))


def get_osd_settings(relation_name):
    """Consolidate requested osd settings from all clients.

    Consolidate requested osd settings from all clients. Check that the
    requested setting is on the whitelist and it does not conflict with
    any other requested settings.

    :returns: Dictionary of settings
    :rtype: dict

    :raises: OSDSettingNotAllowed
    :raises: OSDSettingConflict
    """
    rel_ids = relation_ids(relation_name)
    osd_settings = {}
    for relid in rel_ids:
        for unit in related_units(relid):
            unit_settings = relation_get('osd-settings', unit, relid) or '{}'
            unit_settings = json.loads(unit_settings)
            for key, value in unit_settings.items():
                if key not in OSD_SETTING_WHITELIST:
                    msg = 'Illegal settings "{}"'.format(key)
                    raise OSDSettingNotAllowed(msg)
                if key in osd_settings:
                    if osd_settings[key] != unit_settings[key]:
                        msg = 'Conflicting settings for "{}"'.format(key)
                        raise OSDSettingConflict(msg)
                else:
                    osd_settings[key] = value
    return _order_dict_by_key(osd_settings)


def send_application_name(relid=None):
    """Send the application name down the relation.

    :param relid: Relation id to set application name in.
    :type relid: str
    """
    relation_set(
        relation_id=relid,
        relation_settings={'application-name': application_name()})


def send_osd_settings():
    """Pass on requested OSD settings to osd units."""
    try:
        settings = get_osd_settings('client')
    except OSD_SETTING_EXCEPTIONS as e:
        # There is a problem with the settings, not passing them on. Update
        # status will notify the user.
        log(e, level=ERROR)
        return
    data = {
        'osd-settings': json.dumps(settings, sort_keys=True)}
    for relid in relation_ids('osd'):
        relation_set(relation_id=relid,
                     relation_settings=data)


def validator(value, valid_type, valid_range=None):
    """Helper function for type validation.

    Used to validate these:
    https://docs.ceph.com/docs/master/rados/operations/pools/#set-pool-values
    https://docs.ceph.com/docs/master/rados/configuration/bluestore-config-ref/#inline-compression

    Example input:
        validator(value=1,
                  valid_type=int,
                  valid_range=[0, 2])

    This says I'm testing value=1.  It must be an int inclusive in [0,2]

    :param value: The value to validate.
    :type value: any
    :param valid_type: The type that value should be.
    :type valid_type: any
    :param valid_range: A range of values that value can assume.
    :type valid_range: Optional[Union[List,Tuple]]
    :raises: AssertionError, ValueError
    """
    assert isinstance(value, valid_type), (
        "{} is not a {}".format(value, valid_type))
    if valid_range is not None:
        assert isinstance(
            valid_range, list) or isinstance(valid_range, tuple), (
                "valid_range must be of type List or Tuple, "
                "was given {} of type {}"
                .format(valid_range, type(valid_range)))
        # If we're dealing with strings
        if isinstance(value, six.string_types):
            assert value in valid_range, (
                "{} is not in the list {}".format(value, valid_range))
        # Integer, float should have a min and max
        else:
            if len(valid_range) != 2:
                raise ValueError(
                    "Invalid valid_range list of {} for {}. "
                    "List must be [min,max]".format(valid_range, value))
            assert value >= valid_range[0], (
                "{} is less than minimum allowed value of {}"
                .format(value, valid_range[0]))
            assert value <= valid_range[1], (
                "{} is greater than maximum allowed value of {}"
                .format(value, valid_range[1]))


class PoolCreationError(Exception):
    """A custom exception to inform the caller that a pool creation failed.

    Provides an error message
    """

    def __init__(self, message):
        super(PoolCreationError, self).__init__(message)


class BasePool(object):
    """An object oriented approach to Ceph pool creation.

    This base class is inherited by ReplicatedPool and ErasurePool. Do not call
    create() on this base class as it will raise an exception.

    Instantiate a child class and call create().
    """
    # Dictionary that maps pool operation properties to Tuples with valid type
    # and valid range
    op_validation_map = {
        'compression-algorithm': (str, ('lz4', 'snappy', 'zlib', 'zstd')),
        'compression-mode': (str, ('none', 'passive', 'aggressive', 'force')),
        'compression-required-ratio': (float, None),
        'compression-min-blob-size': (int, None),
        'compression-min-blob-size-hdd': (int, None),
        'compression-min-blob-size-ssd': (int, None),
        'compression-max-blob-size': (int, None),
        'compression-max-blob-size-hdd': (int, None),
        'compression-max-blob-size-ssd': (int, None),
        'rbd-mirroring-mode': (str, ('image', 'pool'))
    }

    def __init__(self, service, name=None, percent_data=None, app_name=None,
                 op=None):
        """Initialize BasePool object.

        Pool information is either initialized from individual keyword
        arguments or from a individual CephBrokerRq operation Dict.

        :param service: The Ceph user name to run commands under.
        :type service: str
        :param name: Name of pool to operate on.
        :type name: str
        :param percent_data: The expected pool size in relation to all
                             available resources in the Ceph cluster. Will be
                             used to set the ``target_size_ratio`` pool
                             property. (default: 10.0)
        :type percent_data: Optional[float]
        :param app_name: Ceph application name, usually one of:
                         ('cephfs', 'rbd', 'rgw') (default: 'unknown')
        :type app_name: Optional[str]
        :param op: Broker request Op to compile pool data from.
        :type op: Optional[Dict[str,any]]
        :raises: KeyError
        """
        # NOTE: Do not perform initialization steps that require live data from
        # a running cluster here. The *Pool classes may be used for validation.
        self.service = service
        self.op = op or {}

        if op:
            # When initializing from op the `name` attribute is required and we
            # will fail with KeyError if it is not provided.
            self.name = op['name']
            self.percent_data = op.get('weight')
            self.app_name = op.get('app-name')
        else:
            self.name = name
            self.percent_data = percent_data
            self.app_name = app_name

        # Set defaults for these if they are not provided
        self.percent_data = self.percent_data or 10.0
        self.app_name = self.app_name or 'unknown'

    def validate(self):
        """Check that value of supplied operation parameters are valid.

        :raises: ValueError
        """
        for op_key, op_value in self.op.items():
            if op_key in self.op_validation_map and op_value is not None:
                valid_type, valid_range = self.op_validation_map[op_key]
                try:
                    validator(op_value, valid_type, valid_range)
                except (AssertionError, ValueError) as e:
                    # Normalize on ValueError, also add information about which
                    # variable we had an issue with.
                    raise ValueError("'{}': {}".format(op_key, str(e)))

    def _create(self):
        """Perform the pool creation, method MUST be overridden by child class.
        """
        raise NotImplementedError

    def _post_create(self):
        """Perform common post pool creation tasks.

        Note that pool properties subject to change during the lifetime of a
        pool / deployment should go into the ``update`` method.

        Do not add calls for a specific pool type here, those should go into
        one of the pool specific classes.
        """
        nautilus_or_later = cmp_pkgrevno('ceph-common', '14.2.0') >= 0
        if nautilus_or_later:
            # Ensure we set the expected pool ratio
            update_pool(
                client=self.service,
                pool=self.name,
                settings={
                    'target_size_ratio': str(
                        self.percent_data / 100.0),
                })
        try:
            set_app_name_for_pool(client=self.service,
                                  pool=self.name,
                                  name=self.app_name)
        except CalledProcessError:
            log('Could not set app name for pool {}'
                .format(self.name),
                level=WARNING)
        if 'pg_autoscaler' in enabled_manager_modules():
            try:
                enable_pg_autoscale(self.service, self.name)
            except CalledProcessError as e:
                log('Could not configure auto scaling for pool {}: {}'
                    .format(self.name, e),
                    level=WARNING)

    def create(self):
        """Create pool and perform any post pool creation tasks.

        To allow for sharing of common code among pool specific classes the
        processing has been broken out into the private methods ``_create``
        and ``_post_create``.

        Do not add any pool type specific handling here, that should go into
        one of the pool specific classes.
        """
        if not pool_exists(self.service, self.name):
            self.validate()
            self._create()
            self._post_create()
            self.update()

    def set_quota(self):
        """Set a quota if requested.

        :raises: CalledProcessError
        """
        max_bytes = self.op.get('max-bytes')
        max_objects = self.op.get('max-objects')
        if max_bytes or max_objects:
            set_pool_quota(service=self.service, pool_name=self.name,
                           max_bytes=max_bytes, max_objects=max_objects)

    def set_compression(self):
        """Set compression properties if requested.

        :raises: CalledProcessError
        """
        compression_properties = {
            key.replace('-', '_'): value
            for key, value in self.op.items()
            if key in (
                'compression-algorithm',
                'compression-mode',
                'compression-required-ratio',
                'compression-min-blob-size',
                'compression-min-blob-size-hdd',
                'compression-min-blob-size-ssd',
                'compression-max-blob-size',
                'compression-max-blob-size-hdd',
                'compression-max-blob-size-ssd') and value}
        if compression_properties:
            update_pool(self.service, self.name, compression_properties)

    def update(self):
        """Update properties for an already existing pool.

        Do not add calls for a specific pool type here, those should go into
        one of the pool specific classes.
        """
        self.validate()
        self.set_quota()
        self.set_compression()

    def add_cache_tier(self, cache_pool, mode):
        """Adds a new cache tier to an existing pool.

        :param cache_pool: The cache tier pool name to add.
        :type cache_pool: str
        :param mode: The caching mode to use for this pool.
                     valid range = ["readonly", "writeback"]
        :type mode: str
        """
        # Check the input types and values
        validator(value=cache_pool, valid_type=six.string_types)
        validator(
            value=mode, valid_type=six.string_types,
            valid_range=["readonly", "writeback"])

        check_call([
            'ceph', '--id', self.service,
            'osd', 'tier', 'add', self.name, cache_pool,
        ])
        check_call([
            'ceph', '--id', self.service,
            'osd', 'tier', 'cache-mode', cache_pool, mode,
        ])
        check_call([
            'ceph', '--id', self.service,
            'osd', 'tier', 'set-overlay', self.name, cache_pool,
        ])
        check_call([
            'ceph', '--id', self.service,
            'osd', 'pool', 'set', cache_pool, 'hit_set_type', 'bloom',
        ])

    def remove_cache_tier(self, cache_pool):
        """Removes a cache tier from Ceph.

        Flushes all dirty objects from writeback pools and waits for that to
        complete.

        :param cache_pool: The cache tier pool name to remove.
        :type cache_pool: str
        """
        # read-only is easy, writeback is much harder
        mode = get_cache_mode(self.service, cache_pool)
        if mode == 'readonly':
            check_call([
                'ceph', '--id', self.service,
                'osd', 'tier', 'cache-mode', cache_pool, 'none'
            ])
            check_call([
                'ceph', '--id', self.service,
                'osd', 'tier', 'remove', self.name, cache_pool,
            ])

        elif mode == 'writeback':
            pool_forward_cmd = ['ceph', '--id', self.service, 'osd', 'tier',
                                'cache-mode', cache_pool, 'forward']
            if cmp_pkgrevno('ceph-common', '10.1') >= 0:
                # Jewel added a mandatory flag
                pool_forward_cmd.append('--yes-i-really-mean-it')

            check_call(pool_forward_cmd)
            # Flush the cache and wait for it to return
            check_call([
                'rados', '--id', self.service,
                '-p', cache_pool, 'cache-flush-evict-all'])
            check_call([
                'ceph', '--id', self.service,
                'osd', 'tier', 'remove-overlay', self.name])
            check_call([
                'ceph', '--id', self.service,
                'osd', 'tier', 'remove', self.name, cache_pool])

    def get_pgs(self, pool_size, percent_data=DEFAULT_POOL_WEIGHT,
                device_class=None):
        """Return the number of placement groups to use when creating the pool.

        Returns the number of placement groups which should be specified when
        creating the pool. This is based upon the calculation guidelines
        provided by the Ceph Placement Group Calculator (located online at
        http://ceph.com/pgcalc/).

        The number of placement groups are calculated using the following:

            (Target PGs per OSD) * (OSD #) * (%Data)
            ----------------------------------------
                         (Pool size)

        Per the upstream guidelines, the OSD # should really be considered
        based on the number of OSDs which are eligible to be selected by the
        pool. Since the pool creation doesn't specify any of CRUSH set rules,
        the default rule will be dependent upon the type of pool being
        created (replicated or erasure).

        This code makes no attempt to determine the number of OSDs which can be
        selected for the specific rule, rather it is left to the user to tune
        in the form of 'expected-osd-count' config option.

        :param pool_size: pool_size is either the number of replicas for
            replicated pools or the K+M sum for erasure coded pools
        :type pool_size: int
        :param percent_data: the percentage of data that is expected to
            be contained in the pool for the specific OSD set. Default value
            is to assume 10% of the data is for this pool, which is a
            relatively low % of the data but allows for the pg_num to be
            increased. NOTE: the default is primarily to handle the scenario
            where related charms requiring pools has not been upgraded to
            include an update to indicate their relative usage of the pools.
        :type percent_data: float
        :param device_class: class of storage to use for basis of pgs
            calculation; ceph supports nvme, ssd and hdd by default based
            on presence of devices of each type in the deployment.
        :type device_class: str
        :returns: The number of pgs to use.
        :rtype: int
        """

        # Note: This calculation follows the approach that is provided
        # by the Ceph PG Calculator located at http://ceph.com/pgcalc/.
        validator(value=pool_size, valid_type=int)

        # Ensure that percent data is set to something - even with a default
        # it can be set to None, which would wreak havoc below.
        if percent_data is None:
            percent_data = DEFAULT_POOL_WEIGHT

        # If the expected-osd-count is specified, then use the max between
        # the expected-osd-count and the actual osd_count
        osd_list = get_osds(self.service, device_class)
        expected = config('expected-osd-count') or 0

        if osd_list:
            if device_class:
                osd_count = len(osd_list)
            else:
                osd_count = max(expected, len(osd_list))

            # Log a message to provide some insight if the calculations claim
            # to be off because someone is setting the expected count and
            # there are more OSDs in reality. Try to make a proper guess
            # based upon the cluster itself.
            if not device_class and expected and osd_count != expected:
                log("Found more OSDs than provided expected count. "
                    "Using the actual count instead", INFO)
        elif expected:
            # Use the expected-osd-count in older ceph versions to allow for
            # a more accurate pg calculations
            osd_count = expected
        else:
            # NOTE(james-page): Default to 200 for older ceph versions
            # which don't support OSD query from cli
            return LEGACY_PG_COUNT

        percent_data /= 100.0
        target_pgs_per_osd = config(
            'pgs-per-osd') or DEFAULT_PGS_PER_OSD_TARGET
        num_pg = (target_pgs_per_osd * osd_count * percent_data) // pool_size

        # NOTE: ensure a sane minimum number of PGS otherwise we don't get any
        #       reasonable data distribution in minimal OSD configurations
        if num_pg < DEFAULT_MINIMUM_PGS:
            num_pg = DEFAULT_MINIMUM_PGS

        # The CRUSH algorithm has a slight optimization for placement groups
        # with powers of 2 so find the nearest power of 2. If the nearest
        # power of 2 is more than 25% below the original value, the next
        # highest value is used. To do this, find the nearest power of 2 such
        # that 2^n <= num_pg, check to see if its within the 25% tolerance.
        exponent = math.floor(math.log(num_pg, 2))
        nearest = 2 ** exponent
        if (num_pg - nearest) > (num_pg * 0.25):
            # Choose the next highest power of 2 since the nearest is more
            # than 25% below the original value.
            return int(nearest * 2)
        else:
            return int(nearest)


class Pool(BasePool):
    """Compatibility shim for any descendents external to this library."""

    @deprecate(
        'The ``Pool`` baseclass has been replaced by ``BasePool`` class.')
    def __init__(self, service, name):
        super(Pool, self).__init__(service, name=name)

    def create(self):
        pass


class ReplicatedPool(BasePool):
    def __init__(self, service, name=None, pg_num=None, replicas=None,
                 percent_data=None, app_name=None, op=None):
        """Initialize ReplicatedPool object.

        Pool information is either initialized from individual keyword
        arguments or from a individual CephBrokerRq operation Dict.

        Please refer to the docstring of the ``BasePool`` class for
        documentation of the common parameters.

        :param pg_num: Express wish for number of Placement Groups (this value
                       is subject to validation against a running cluster prior
                       to use to avoid creating a pool with too many PGs)
        :type pg_num: int
        :param replicas: Number of copies there should be of each object added
                         to this replicated pool.
        :type replicas: int
        :raises: KeyError
        """
        # NOTE: Do not perform initialization steps that require live data from
        # a running cluster here. The *Pool classes may be used for validation.

        # The common parameters are handled in our parents initializer
        super(ReplicatedPool, self).__init__(
            service=service, name=name, percent_data=percent_data,
            app_name=app_name, op=op)

        if op:
            # When initializing from op `replicas` is a required attribute, and
            # we will fail with KeyError if it is not provided.
            self.replicas = op['replicas']
            self.pg_num = op.get('pg_num')
        else:
            self.replicas = replicas or 2
            self.pg_num = pg_num

    def _create(self):
        # Do extra validation on pg_num with data from live cluster
        if self.pg_num:
            # Since the number of placement groups were specified, ensure
            # that there aren't too many created.
            max_pgs = self.get_pgs(self.replicas, 100.0)
            self.pg_num = min(self.pg_num, max_pgs)
        else:
            self.pg_num = self.get_pgs(self.replicas, self.percent_data)

        nautilus_or_later = cmp_pkgrevno('ceph-common', '14.2.0') >= 0
        # Create it
        if nautilus_or_later:
            cmd = [
                'ceph', '--id', self.service, 'osd', 'pool', 'create',
                '--pg-num-min={}'.format(
                    min(AUTOSCALER_DEFAULT_PGS, self.pg_num)
                ),
                self.name, str(self.pg_num)
            ]
        else:
            cmd = [
                'ceph', '--id', self.service, 'osd', 'pool', 'create',
                self.name, str(self.pg_num)
            ]
        check_call(cmd)

    def _post_create(self):
        # Set the pool replica size
        update_pool(client=self.service,
                    pool=self.name,
                    settings={'size': str(self.replicas)})
        # Perform other common post pool creation tasks
        super(ReplicatedPool, self)._post_create()


class ErasurePool(BasePool):
    """Default jerasure erasure coded pool."""

    def __init__(self, service, name=None, erasure_code_profile=None,
                 percent_data=None, app_name=None, op=None,
                 allow_ec_overwrites=False):
        """Initialize ReplicatedPool object.

        Pool information is either initialized from individual keyword
        arguments or from a individual CephBrokerRq operation Dict.

        Please refer to the docstring of the ``BasePool`` class for
        documentation of the common parameters.

        :param erasure_code_profile: EC Profile to use (default: 'default')
        :type erasure_code_profile: Optional[str]
        """
        # NOTE: Do not perform initialization steps that require live data from
        # a running cluster here. The *Pool classes may be used for validation.

        # The common parameters are handled in our parents initializer
        super(ErasurePool, self).__init__(
            service=service, name=name, percent_data=percent_data,
            app_name=app_name, op=op)

        if op:
            # Note that the different default when initializing from op stems
            # from different handling of this in the `charms.ceph` library.
            self.erasure_code_profile = op.get('erasure-profile',
                                               'default-canonical')
            self.allow_ec_overwrites = op.get('allow-ec-overwrites')
        else:
            # We keep the class default when initialized from keyword arguments
            # to not break the API for any other consumers.
            self.erasure_code_profile = erasure_code_profile or 'default'
            self.allow_ec_overwrites = allow_ec_overwrites

    def _create(self):
        # Try to find the erasure profile information in order to properly
        # size the number of placement groups. The size of an erasure
        # coded placement group is calculated as k+m.
        erasure_profile = get_erasure_profile(self.service,
                                              self.erasure_code_profile)

        # Check for errors
        if erasure_profile is None:
            msg = ("Failed to discover erasure profile named "
                   "{}".format(self.erasure_code_profile))
            log(msg, level=ERROR)
            raise PoolCreationError(msg)
        if 'k' not in erasure_profile or 'm' not in erasure_profile:
            # Error
            msg = ("Unable to find k (data chunks) or m (coding chunks) "
                   "in erasure profile {}".format(erasure_profile))
            log(msg, level=ERROR)
            raise PoolCreationError(msg)

        k = int(erasure_profile['k'])
        m = int(erasure_profile['m'])
        pgs = self.get_pgs(k + m, self.percent_data)
        nautilus_or_later = cmp_pkgrevno('ceph-common', '14.2.0') >= 0
        # Create it
        if nautilus_or_later:
            cmd = [
                'ceph', '--id', self.service, 'osd', 'pool', 'create',
                '--pg-num-min={}'.format(
                    min(AUTOSCALER_DEFAULT_PGS, pgs)
                ),
                self.name, str(pgs), str(pgs),
                'erasure', self.erasure_code_profile
            ]
        else:
            cmd = [
                'ceph', '--id', self.service, 'osd', 'pool', 'create',
                self.name, str(pgs), str(pgs),
                'erasure', self.erasure_code_profile
            ]
        check_call(cmd)

    def _post_create(self):
        super(ErasurePool, self)._post_create()
        if self.allow_ec_overwrites:
            update_pool(self.service, self.name,
                        {'allow_ec_overwrites': 'true'})


def enabled_manager_modules():
    """Return a list of enabled manager modules.

    :rtype: List[str]
    """
    cmd = ['ceph', 'mgr', 'module', 'ls']
    try:
        modules = check_output(cmd)
        if six.PY3:
            modules = modules.decode('UTF-8')
    except CalledProcessError as e:
        log("Failed to list ceph modules: {}".format(e), WARNING)
        return []
    modules = json.loads(modules)
    return modules['enabled_modules']


def enable_pg_autoscale(service, pool_name):
    """Enable Ceph's PG autoscaler for the specified pool.

    :param service: The Ceph user name to run the command under
    :type service: str
    :param pool_name: The name of the pool to enable sutoscaling on
    :type pool_name: str
    :raises: CalledProcessError if the command fails
    """
    check_call([
        'ceph', '--id', service,
        'osd', 'pool', 'set', pool_name, 'pg_autoscale_mode', 'on'])


def get_mon_map(service):
    """Return the current monitor map.

    :param service: The Ceph user name to run the command under
    :type service: str
    :returns: Dictionary with monitor map data
    :rtype: Dict[str,any]
    :raises: ValueError if the monmap fails to parse, CalledProcessError if our
             ceph command fails.
    """
    try:
        mon_status = check_output(['ceph', '--id', service,
                                   'mon_status', '--format=json'])
        if six.PY3:
            mon_status = mon_status.decode('UTF-8')
        try:
            return json.loads(mon_status)
        except ValueError as v:
            log("Unable to parse mon_status json: {}. Error: {}"
                .format(mon_status, str(v)))
            raise
    except CalledProcessError as e:
        log("mon_status command failed with message: {}"
            .format(str(e)))
        raise


def hash_monitor_names(service):
    """Get a sorted list of monitor hashes in ascending order.

    Uses the get_mon_map() function to get information about the monitor
    cluster. Hash the name of each monitor.

    :param service: The Ceph user name to run the command under.
    :type service: str
    :returns: a sorted list of monitor hashes in an ascending order.
    :rtype : List[str]
    :raises: CalledProcessError, ValueError
    """
    try:
        hash_list = []
        monitor_list = get_mon_map(service=service)
        if monitor_list['monmap']['mons']:
            for mon in monitor_list['monmap']['mons']:
                hash_list.append(
                    hashlib.sha224(mon['name'].encode('utf-8')).hexdigest())
            return sorted(hash_list)
        else:
            return None
    except (ValueError, CalledProcessError):
        raise


def monitor_key_delete(service, key):
    """Delete a key and value pair from the monitor cluster.

    Deletes a key value pair on the monitor cluster.

    :param service: The Ceph user name to run the command under
    :type service: str
    :param key: The key to delete.
    :type key: str
    :raises: CalledProcessError
    """
    try:
        check_output(
            ['ceph', '--id', service,
             'config-key', 'del', str(key)])
    except CalledProcessError as e:
        log("Monitor config-key put failed with message: {}"
            .format(e.output))
        raise


def monitor_key_set(service, key, value):
    """Set a key value pair on the monitor cluster.

    :param service: The Ceph user name to run the command under.
    :type service str
    :param key: The key to set.
    :type key: str
    :param value: The value to set. This will be coerced into a string.
    :type value: str
    :raises: CalledProcessError
    """
    try:
        check_output(
            ['ceph', '--id', service,
             'config-key', 'put', str(key), str(value)])
    except CalledProcessError as e:
        log("Monitor config-key put failed with message: {}"
            .format(e.output))
        raise


def monitor_key_get(service, key):
    """Get the value of an existing key in the monitor cluster.

    :param service: The Ceph user name to run the command under
    :type service: str
    :param key: The key to search for.
    :type key: str
    :return: Returns the value of that key or None if not found.
    :rtype: Optional[str]
    """
    try:
        output = check_output(
            ['ceph', '--id', service,
             'config-key', 'get', str(key)]).decode('UTF-8')
        return output
    except CalledProcessError as e:
        log("Monitor config-key get failed with message: {}"
            .format(e.output))
        return None


def monitor_key_exists(service, key):
    """Search for existence of key in the monitor cluster.

    :param service: The Ceph user name to run the command under.
    :type service: str
    :param key: The key to search for.
    :type key: str
    :return: Returns True if the key exists, False if not.
    :rtype: bool
    :raises: CalledProcessError if an unknown error occurs.
    """
    try:
        check_call(
            ['ceph', '--id', service,
             'config-key', 'exists', str(key)])
        # I can return true here regardless because Ceph returns
        # ENOENT if the key wasn't found
        return True
    except CalledProcessError as e:
        if e.returncode == errno.ENOENT:
            return False
        else:
            log("Unknown error from ceph config-get exists: {} {}"
                .format(e.returncode, e.output))
            raise


def get_erasure_profile(service, name):
    """Get an existing erasure code profile if it exists.

    :param service: The Ceph user name to run the command under.
    :type service: str
    :param name: Name of profile.
    :type name: str
    :returns: Dictionary with profile data.
    :rtype: Optional[Dict[str]]
    """
    try:
        out = check_output(['ceph', '--id', service,
                            'osd', 'erasure-code-profile', 'get',
                            name, '--format=json'])
        if six.PY3:
            out = out.decode('UTF-8')
        return json.loads(out)
    except (CalledProcessError, OSError, ValueError):
        return None


def pool_set(service, pool_name, key, value):
    """Sets a value for a RADOS pool in ceph.

    :param service: The Ceph user name to run the command under.
    :type service: str
    :param pool_name: Name of pool to set property on.
    :type pool_name: str
    :param key: Property key.
    :type key: str
    :param value: Value, will be coerced into str and shifted to lowercase.
    :type value: str
    :raises: CalledProcessError
    """
    cmd = [
        'ceph', '--id', service,
        'osd', 'pool', 'set', pool_name, key, str(value).lower()]
    check_call(cmd)


def snapshot_pool(service, pool_name, snapshot_name):
    """Snapshots a RADOS pool in Ceph.

    :param service: The Ceph user name to run the command under.
    :type service: str
    :param pool_name: Name of pool to snapshot.
    :type pool_name: str
    :param snapshot_name: Name of snapshot to create.
    :type snapshot_name: str
    :raises: CalledProcessError
    """
    cmd = [
        'ceph', '--id', service,
        'osd', 'pool', 'mksnap', pool_name, snapshot_name]
    check_call(cmd)


def remove_pool_snapshot(service, pool_name, snapshot_name):
    """Remove a snapshot from a RADOS pool in Ceph.

    :param service: The Ceph user name to run the command under.
    :type service: str
    :param pool_name: Name of pool to remove snapshot from.
    :type pool_name: str
    :param snapshot_name: Name of snapshot to remove.
    :type snapshot_name: str
    :raises: CalledProcessError
    """
    cmd = [
        'ceph', '--id', service,
        'osd', 'pool', 'rmsnap', pool_name, snapshot_name]
    check_call(cmd)


def set_pool_quota(service, pool_name, max_bytes=None, max_objects=None):
    """Set byte quota on a RADOS pool in Ceph.

    :param service: The Ceph user name to run the command under
    :type service: str
    :param pool_name: Name of pool
    :type pool_name: str
    :param max_bytes: Maximum bytes quota to apply
    :type max_bytes: int
    :param max_objects: Maximum objects quota to apply
    :type max_objects: int
    :raises: subprocess.CalledProcessError
    """
    cmd = [
        'ceph', '--id', service,
        'osd', 'pool', 'set-quota', pool_name]
    if max_bytes:
        cmd = cmd + ['max_bytes', str(max_bytes)]
    if max_objects:
        cmd = cmd + ['max_objects', str(max_objects)]
    check_call(cmd)


def remove_pool_quota(service, pool_name):
    """Remove byte quota on a RADOS pool in Ceph.

    :param service: The Ceph user name to run the command under.
    :type service: str
    :param pool_name: Name of pool to remove quota from.
    :type pool_name: str
    :raises: CalledProcessError
    """
    cmd = [
        'ceph', '--id', service,
        'osd', 'pool', 'set-quota', pool_name, 'max_bytes', '0']
    check_call(cmd)


def remove_erasure_profile(service, profile_name):
    """Remove erasure code profile.

    :param service: The Ceph user name to run the command under
    :type service: str
    :param profile_name: Name of profile to remove.
    :type profile_name: str
    :raises: CalledProcessError
    """
    cmd = [
        'ceph', '--id', service,
        'osd', 'erasure-code-profile', 'rm', profile_name]
    check_call(cmd)


def create_erasure_profile(service, profile_name,
                           erasure_plugin_name='jerasure',
                           failure_domain=None,
                           data_chunks=2, coding_chunks=1,
                           locality=None, durability_estimator=None,
                           helper_chunks=None,
                           scalar_mds=None,
                           crush_locality=None,
                           device_class=None,
                           erasure_plugin_technique=None):
    """Create a new erasure code profile if one does not already exist for it.

    Profiles are considered immutable so will not be updated if the named
    profile already exists.

    Please refer to [0] for more details.

    0: http://docs.ceph.com/docs/master/rados/operations/erasure-code-profile/

    :param service: The Ceph user name to run the command under.
    :type service: str
    :param profile_name: Name of profile.
    :type profile_name: str
    :param erasure_plugin_name: Erasure code plugin.
    :type erasure_plugin_name: str
    :param failure_domain: Failure domain, one of:
                           ('chassis', 'datacenter', 'host', 'osd', 'pdu',
                            'pod', 'rack', 'region', 'room', 'root', 'row').
    :type failure_domain: str
    :param data_chunks: Number of data chunks.
    :type data_chunks: int
    :param coding_chunks: Number of coding chunks.
    :type coding_chunks: int
    :param locality: Locality.
    :type locality: int
    :param durability_estimator: Durability estimator.
    :type durability_estimator: int
    :param helper_chunks: int
    :type helper_chunks: int
    :param device_class: Restrict placement to devices of specific class.
    :type device_class: str
    :param scalar_mds: one of ['isa', 'jerasure', 'shec']
    :type scalar_mds: str
    :param crush_locality: LRC locality faulure domain, one of:
                           ('chassis', 'datacenter', 'host', 'osd', 'pdu', 'pod',
                            'rack', 'region', 'room', 'root', 'row') or unset.
    :type crush_locaity: str
    :param erasure_plugin_technique: Coding technique for EC plugin
    :type erasure_plugin_technique: str
    :return: None.  Can raise CalledProcessError, ValueError or AssertionError
    """
    if erasure_profile_exists(service, profile_name):
        log('EC profile {} exists, skipping update'.format(profile_name),
            level=WARNING)
        return

    plugin_techniques = {
        'jerasure': [
            'reed_sol_van',
            'reed_sol_r6_op',
            'cauchy_orig',
            'cauchy_good',
            'liberation',
            'blaum_roth',
            'liber8tion'
        ],
        'lrc': [],
        'isa': [
            'reed_sol_van',
            'cauchy',
        ],
        'shec': [
            'single',
            'multiple'
        ],
        'clay': [],
    }
    failure_domains = [
        'chassis', 'datacenter',
        'host', 'osd',
        'pdu', 'pod',
        'rack', 'region',
        'room', 'root',
        'row',
    ]
    device_classes = [
        'ssd',
        'hdd',
        'nvme'
    ]

    validator(erasure_plugin_name, six.string_types,
              list(plugin_techniques.keys()))

    cmd = [
        'ceph', '--id', service,
        'osd', 'erasure-code-profile', 'set', profile_name,
        'plugin={}'.format(erasure_plugin_name),
        'k={}'.format(str(data_chunks)),
        'm={}'.format(str(coding_chunks)),
    ]

    if erasure_plugin_technique:
        validator(erasure_plugin_technique, six.string_types,
                  plugin_techniques[erasure_plugin_name])
        cmd.append('technique={}'.format(erasure_plugin_technique))

    luminous_or_later = cmp_pkgrevno('ceph-common', '12.0.0') >= 0

    # Set failure domain from options if not provided in args
    if not failure_domain and config('customize-failure-domain'):
        # Defaults to 'host' so just need to deal with
        # setting 'rack' if feature is enabled
        failure_domain = 'rack'

    if failure_domain:
        validator(failure_domain, six.string_types, failure_domains)
        # failure_domain changed in luminous
        if luminous_or_later:
            cmd.append('crush-failure-domain={}'.format(failure_domain))
        else:
            cmd.append('ruleset-failure-domain={}'.format(failure_domain))

    # device class new in luminous
    if luminous_or_later and device_class:
        validator(device_class, six.string_types, device_classes)
        cmd.append('crush-device-class={}'.format(device_class))
    else:
        log('Skipping device class configuration (ceph < 12.0.0)',
            level=DEBUG)

    # Add plugin specific information
    if erasure_plugin_name == 'lrc':
        # LRC mandatory configuration
        if locality:
            cmd.append('l={}'.format(str(locality)))
        else:
            raise ValueError("locality must be provided for lrc plugin")
        # LRC optional configuration
        if crush_locality:
            validator(crush_locality, six.string_types, failure_domains)
            cmd.append('crush-locality={}'.format(crush_locality))

    if erasure_plugin_name == 'shec':
        # SHEC optional configuration
        if durability_estimator:
            cmd.append('c={}'.format((durability_estimator)))

    if erasure_plugin_name == 'clay':
        # CLAY optional configuration
        if helper_chunks:
            cmd.append('d={}'.format(str(helper_chunks)))
        if scalar_mds:
            cmd.append('scalar-mds={}'.format(scalar_mds))

    check_call(cmd)


def rename_pool(service, old_name, new_name):
    """Rename a Ceph pool from old_name to new_name.

    :param service: The Ceph user name to run the command under.
    :type service: str
    :param old_name: Name of pool subject to rename.
    :type old_name: str
    :param new_name: Name to rename pool to.
    :type new_name: str
    """
    validator(value=old_name, valid_type=six.string_types)
    validator(value=new_name, valid_type=six.string_types)

    cmd = [
        'ceph', '--id', service,
        'osd', 'pool', 'rename', old_name, new_name]
    check_call(cmd)


def erasure_profile_exists(service, name):
    """Check to see if an Erasure code profile already exists.

    :param service: The Ceph user name to run the command under
    :type service: str
    :param name: Name of profile to look for.
    :type name: str
    :returns: True if it exists, False otherwise.
    :rtype: bool
    """
    validator(value=name, valid_type=six.string_types)
    try:
        check_call(['ceph', '--id', service,
                    'osd', 'erasure-code-profile', 'get',
                    name])
        return True
    except CalledProcessError:
        return False


def get_cache_mode(service, pool_name):
    """Find the current caching mode of the pool_name given.

    :param service: The Ceph user name to run the command under
    :type service: str
    :param pool_name: Name of pool.
    :type pool_name: str
    :returns: Current cache mode.
    :rtype: Optional[int]
    """
    validator(value=service, valid_type=six.string_types)
    validator(value=pool_name, valid_type=six.string_types)
    out = check_output(['ceph', '--id', service,
                        'osd', 'dump', '--format=json'])
    if six.PY3:
        out = out.decode('UTF-8')
    try:
        osd_json = json.loads(out)
        for pool in osd_json['pools']:
            if pool['pool_name'] == pool_name:
                return pool['cache_mode']
        return None
    except ValueError:
        raise


def pool_exists(service, name):
    """Check to see if a RADOS pool already exists."""
    try:
        out = check_output(['rados', '--id', service, 'lspools'])
        if six.PY3:
            out = out.decode('UTF-8')
    except CalledProcessError:
        return False

    return name in out.split()


def get_osds(service, device_class=None):
    """Return a list of all Ceph Object Storage Daemons currently in the
    cluster (optionally filtered by storage device class).

    :param device_class: Class of storage device for OSD's
    :type device_class: str
    """
    luminous_or_later = cmp_pkgrevno('ceph-common', '12.0.0') >= 0
    if luminous_or_later and device_class:
        out = check_output(['ceph', '--id', service,
                            'osd', 'crush', 'class',
                            'ls-osd', device_class,
                            '--format=json'])
    else:
        out = check_output(['ceph', '--id', service,
                            'osd', 'ls',
                            '--format=json'])
    if six.PY3:
        out = out.decode('UTF-8')
    return json.loads(out)


def install():
    """Basic Ceph client installation."""
    ceph_dir = "/etc/ceph"
    if not os.path.exists(ceph_dir):
        os.mkdir(ceph_dir)

    apt_install('ceph-common', fatal=True)


def rbd_exists(service, pool, rbd_img):
    """Check to see if a RADOS block device exists."""
    try:
        out = check_output(['rbd', 'list', '--id',
                            service, '--pool', pool])
        if six.PY3:
            out = out.decode('UTF-8')
    except CalledProcessError:
        return False

    return rbd_img in out


def create_rbd_image(service, pool, image, sizemb):
    """Create a new RADOS block device."""
    cmd = ['rbd', 'create', image, '--size', str(sizemb), '--id', service,
           '--pool', pool]
    check_call(cmd)


def update_pool(client, pool, settings):
    """Update pool properties.

    :param client: Client/User-name to authenticate with.
    :type client: str
    :param pool: Name of pool to operate on
    :type pool: str
    :param settings: Dictionary with key/value pairs to set.
    :type settings: Dict[str, str]
    :raises: CalledProcessError
    """
    cmd = ['ceph', '--id', client, 'osd', 'pool', 'set', pool]
    for k, v in six.iteritems(settings):
        check_call(cmd + [k, v])


def set_app_name_for_pool(client, pool, name):
    """Calls `osd pool application enable` for the specified pool name

    :param client: Name of the ceph client to use
    :type client: str
    :param pool: Pool to set app name for
    :type pool: str
    :param name: app name for the specified pool
    :type name: str

    :raises: CalledProcessError if ceph call fails
    """
    if cmp_pkgrevno('ceph-common', '12.0.0') >= 0:
        cmd = ['ceph', '--id', client, 'osd', 'pool',
               'application', 'enable', pool, name]
        check_call(cmd)


def create_pool(service, name, replicas=3, pg_num=None):
    """Create a new RADOS pool."""
    if pool_exists(service, name):
        log("Ceph pool {} already exists, skipping creation".format(name),
            level=WARNING)
        return

    if not pg_num:
        # Calculate the number of placement groups based
        # on upstream recommended best practices.
        osds = get_osds(service)
        if osds:
            pg_num = (len(osds) * 100 // replicas)
        else:
            # NOTE(james-page): Default to 200 for older ceph versions
            # which don't support OSD query from cli
            pg_num = 200

    cmd = ['ceph', '--id', service, 'osd', 'pool', 'create', name, str(pg_num)]
    check_call(cmd)

    update_pool(service, name, settings={'size': str(replicas)})


def delete_pool(service, name):
    """Delete a RADOS pool from ceph."""
    cmd = ['ceph', '--id', service, 'osd', 'pool', 'delete', name,
           '--yes-i-really-really-mean-it']
    check_call(cmd)


def _keyfile_path(service):
    return KEYFILE.format(service)


def _keyring_path(service):
    return KEYRING.format(service)


def add_key(service, key):
    """Add a key to a keyring.

    Creates the keyring if it doesn't already exist.

    Logs and returns if the key is already in the keyring.
    """
    keyring = _keyring_path(service)
    if os.path.exists(keyring):
        with open(keyring, 'r') as ring:
            if key in ring.read():
                log('Ceph keyring exists at %s and has not changed.' % keyring,
                    level=DEBUG)
                return
            log('Updating existing keyring %s.' % keyring, level=DEBUG)

    cmd = ['ceph-authtool', keyring, '--create-keyring',
           '--name=client.{}'.format(service), '--add-key={}'.format(key)]
    check_call(cmd)
    log('Created new ceph keyring at %s.' % keyring, level=DEBUG)


def create_keyring(service, key):
    """Deprecated. Please use the more accurately named 'add_key'"""
    return add_key(service, key)


def delete_keyring(service):
    """Delete an existing Ceph keyring."""
    keyring = _keyring_path(service)
    if not os.path.exists(keyring):
        log('Keyring does not exist at %s' % keyring, level=WARNING)
        return

    os.remove(keyring)
    log('Deleted ring at %s.' % keyring, level=INFO)


def create_key_file(service, key):
    """Create a file containing key."""
    keyfile = _keyfile_path(service)
    if os.path.exists(keyfile):
        log('Keyfile exists at %s.' % keyfile, level=WARNING)
        return

    with open(keyfile, 'w') as fd:
        fd.write(key)

    log('Created new keyfile at %s.' % keyfile, level=INFO)


def get_ceph_nodes(relation='ceph'):
    """Query named relation to determine current nodes."""
    hosts = []
    for r_id in relation_ids(relation):
        for unit in related_units(r_id):
            hosts.append(relation_get('private-address', unit=unit, rid=r_id))

    return hosts


def configure(service, key, auth, use_syslog):
    """Perform basic configuration of Ceph."""
    add_key(service, key)
    create_key_file(service, key)
    hosts = get_ceph_nodes()
    with open('/etc/ceph/ceph.conf', 'w') as ceph_conf:
        ceph_conf.write(CEPH_CONF.format(auth=auth,
                                         keyring=_keyring_path(service),
                                         mon_hosts=",".join(map(str, hosts)),
                                         use_syslog=use_syslog))
    modprobe('rbd')


def image_mapped(name):
    """Determine whether a RADOS block device is mapped locally."""
    try:
        out = check_output(['rbd', 'showmapped'])
        if six.PY3:
            out = out.decode('UTF-8')
    except CalledProcessError:
        return False

    return name in out


def map_block_storage(service, pool, image):
    """Map a RADOS block device for local use."""
    cmd = [
        'rbd',
        'map',
        '{}/{}'.format(pool, image),
        '--user',
        service,
        '--secret',
        _keyfile_path(service),
    ]
    check_call(cmd)


def filesystem_mounted(fs):
    """Determine whether a filesystem is already mounted."""
    return fs in [f for f, m in mounts()]


def make_filesystem(blk_device, fstype='ext4', timeout=10):
    """Make a new filesystem on the specified block device."""
    count = 0
    e_noent = errno.ENOENT
    while not os.path.exists(blk_device):
        if count >= timeout:
            log('Gave up waiting on block device %s' % blk_device,
                level=ERROR)
            raise IOError(e_noent, os.strerror(e_noent), blk_device)

        log('Waiting for block device %s to appear' % blk_device,
            level=DEBUG)
        count += 1
        time.sleep(1)
    else:
        log('Formatting block device %s as filesystem %s.' %
            (blk_device, fstype), level=INFO)
        check_call(['mkfs', '-t', fstype, blk_device])


def place_data_on_block_device(blk_device, data_src_dst):
    """Migrate data in data_src_dst to blk_device and then remount."""
    # mount block device into /mnt
    mount(blk_device, '/mnt')
    # copy data to /mnt
    copy_files(data_src_dst, '/mnt')
    # umount block device
    umount('/mnt')
    # Grab user/group ID's from original source
    _dir = os.stat(data_src_dst)
    uid = _dir.st_uid
    gid = _dir.st_gid
    # re-mount where the data should originally be
    # TODO: persist is currently a NO-OP in core.host
    mount(blk_device, data_src_dst, persist=True)
    # ensure original ownership of new mount.
    os.chown(data_src_dst, uid, gid)


def copy_files(src, dst, symlinks=False, ignore=None):
    """Copy files from src to dst."""
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            shutil.copytree(s, d, symlinks, ignore)
        else:
            shutil.copy2(s, d)


def ensure_ceph_storage(service, pool, rbd_img, sizemb, mount_point,
                        blk_device, fstype, system_services=[],
                        replicas=3):
    """NOTE: This function must only be called from a single service unit for
    the same rbd_img otherwise data loss will occur.

    Ensures given pool and RBD image exists, is mapped to a block device,
    and the device is formatted and mounted at the given mount_point.

    If formatting a device for the first time, data existing at mount_point
    will be migrated to the RBD device before being re-mounted.

    All services listed in system_services will be stopped prior to data
    migration and restarted when complete.
    """
    # Ensure pool, RBD image, RBD mappings are in place.
    if not pool_exists(service, pool):
        log('Creating new pool {}.'.format(pool), level=INFO)
        create_pool(service, pool, replicas=replicas)

    if not rbd_exists(service, pool, rbd_img):
        log('Creating RBD image ({}).'.format(rbd_img), level=INFO)
        create_rbd_image(service, pool, rbd_img, sizemb)

    if not image_mapped(rbd_img):
        log('Mapping RBD Image {} as a Block Device.'.format(rbd_img),
            level=INFO)
        map_block_storage(service, pool, rbd_img)

    # make file system
    # TODO: What happens if for whatever reason this is run again and
    # the data is already in the rbd device and/or is mounted??
    # When it is mounted already, it will fail to make the fs
    # XXX: This is really sketchy!  Need to at least add an fstab entry
    #      otherwise this hook will blow away existing data if its executed
    #      after a reboot.
    if not filesystem_mounted(mount_point):
        make_filesystem(blk_device, fstype)

        for svc in system_services:
            if service_running(svc):
                log('Stopping services {} prior to migrating data.'
                    .format(svc), level=DEBUG)
                service_stop(svc)

        place_data_on_block_device(blk_device, mount_point)

        for svc in system_services:
            log('Starting service {} after migrating data.'
                .format(svc), level=DEBUG)
            service_start(svc)


def ensure_ceph_keyring(service, user=None, group=None,
                        relation='ceph', key=None):
    """Ensures a ceph keyring is created for a named service and optionally
    ensures user and group ownership.

    @returns boolean: Flag to indicate whether a key was successfully written
                      to disk based on either relation data or a supplied key
    """
    if not key:
        for rid in relation_ids(relation):
            for unit in related_units(rid):
                key = relation_get('key', rid=rid, unit=unit)
                if key:
                    break

    if not key:
        return False

    add_key(service=service, key=key)
    keyring = _keyring_path(service)
    if user and group:
        check_call(['chown', '%s.%s' % (user, group), keyring])

    return True


class CephBrokerRq(object):
    """Ceph broker request.

    Multiple operations can be added to a request and sent to the Ceph broker
    to be executed.

    Request is json-encoded for sending over the wire.

    The API is versioned and defaults to version 1.
    """

    def __init__(self, api_version=1, request_id=None, raw_request_data=None):
        """Initialize CephBrokerRq object.

        Builds a new empty request or rebuilds a request from on-wire JSON
        data.

        :param api_version: API version for request (default: 1).
        :type api_version: Optional[int]
        :param request_id: Unique identifier for request.
                           (default: string representation of generated UUID)
        :type request_id: Optional[str]
        :param raw_request_data: JSON-encoded string to build request from.
        :type raw_request_data: Optional[str]
        :raises: KeyError
        """
        if raw_request_data:
            request_data = json.loads(raw_request_data)
            self.api_version = request_data['api-version']
            self.request_id = request_data['request-id']
            self.set_ops(request_data['ops'])
        else:
            self.api_version = api_version
            if request_id:
                self.request_id = request_id
            else:
                self.request_id = str(uuid.uuid1())
            self.ops = []

    def add_op(self, op):
        """Add an op if it is not already in the list.

        :param op: Operation to add.
        :type op: dict
        """
        if op not in self.ops:
            self.ops.append(op)

    def add_op_request_access_to_group(self, name, namespace=None,
                                       permission=None, key_name=None,
                                       object_prefix_permissions=None):
        """
        Adds the requested permissions to the current service's Ceph key,
        allowing the key to access only the specified pools or
        object prefixes. object_prefix_permissions should be a dictionary
        keyed on the permission with the corresponding value being a list
        of prefixes to apply that permission to.
            {
                'rwx': ['prefix1', 'prefix2'],
                'class-read': ['prefix3']}
        """
        self.add_op({
            'op': 'add-permissions-to-key', 'group': name,
            'namespace': namespace,
            'name': key_name or service_name(),
            'group-permission': permission,
            'object-prefix-permissions': object_prefix_permissions})

    def add_op_create_pool(self, name, replica_count=3, pg_num=None,
                           weight=None, group=None, namespace=None,
                           app_name=None, max_bytes=None, max_objects=None):
        """DEPRECATED: Use ``add_op_create_replicated_pool()`` or
                       ``add_op_create_erasure_pool()`` instead.
        """
        return self.add_op_create_replicated_pool(
            name, replica_count=replica_count, pg_num=pg_num, weight=weight,
            group=group, namespace=namespace, app_name=app_name,
            max_bytes=max_bytes, max_objects=max_objects)

    # Use function parameters and docstring to define types in a compatible
    # manner.
    #
    # NOTE: Our caller should always use a kwarg Dict when calling us so
    # no need to maintain fixed order/position for parameters. Please keep them
    # sorted by name when adding new ones.
    def _partial_build_common_op_create(self,
                                        app_name=None,
                                        compression_algorithm=None,
                                        compression_mode=None,
                                        compression_required_ratio=None,
                                        compression_min_blob_size=None,
                                        compression_min_blob_size_hdd=None,
                                        compression_min_blob_size_ssd=None,
                                        compression_max_blob_size=None,
                                        compression_max_blob_size_hdd=None,
                                        compression_max_blob_size_ssd=None,
                                        group=None,
                                        max_bytes=None,
                                        max_objects=None,
                                        namespace=None,
                                        rbd_mirroring_mode='pool',
                                        weight=None):
        """Build common part of a create pool operation.

        :param app_name: Tag pool with application name. Note that there is
                         certain protocols emerging upstream with regard to
                         meaningful application names to use.
                         Examples are 'rbd' and 'rgw'.
        :type app_name: Optional[str]
        :param compression_algorithm: Compressor to use, one of:
                                      ('lz4', 'snappy', 'zlib', 'zstd')
        :type compression_algorithm: Optional[str]
        :param compression_mode: When to compress data, one of:
                                 ('none', 'passive', 'aggressive', 'force')
        :type compression_mode: Optional[str]
        :param compression_required_ratio: Minimum compression ratio for data
                                           chunk, if the requested ratio is not
                                           achieved the compressed version will
                                           be thrown away and the original
                                           stored.
        :type compression_required_ratio: Optional[float]
        :param compression_min_blob_size: Chunks smaller than this are never
                                          compressed (unit: bytes).
        :type compression_min_blob_size: Optional[int]
        :param compression_min_blob_size_hdd: Chunks smaller than this are not
                                              compressed when destined to
                                              rotational media (unit: bytes).
        :type compression_min_blob_size_hdd: Optional[int]
        :param compression_min_blob_size_ssd: Chunks smaller than this are not
                                              compressed when destined to flash
                                              media (unit: bytes).
        :type compression_min_blob_size_ssd: Optional[int]
        :param compression_max_blob_size: Chunks larger than this are broken
                                          into N * compression_max_blob_size
                                          chunks before being compressed
                                          (unit: bytes).
        :type compression_max_blob_size: Optional[int]
        :param compression_max_blob_size_hdd: Chunks larger than this are
                                              broken into
                                              N * compression_max_blob_size_hdd
                                              chunks before being compressed
                                              when destined for rotational
                                              media (unit: bytes)
        :type compression_max_blob_size_hdd: Optional[int]
        :param compression_max_blob_size_ssd: Chunks larger than this are
                                              broken into
                                              N * compression_max_blob_size_ssd
                                              chunks before being compressed
                                              when destined for flash media
                                              (unit: bytes).
        :type compression_max_blob_size_ssd: Optional[int]
        :param group: Group to add pool to
        :type group: Optional[str]
        :param max_bytes: Maximum bytes quota to apply
        :type max_bytes: Optional[int]
        :param max_objects: Maximum objects quota to apply
        :type max_objects: Optional[int]
        :param namespace: Group namespace
        :type namespace: Optional[str]
        :param rbd_mirroring_mode: Pool mirroring mode used when Ceph RBD
                                   mirroring is enabled.
        :type rbd_mirroring_mode: Optional[str]
        :param weight: The percentage of data that is expected to be contained
                       in the pool from the total available space on the OSDs.
                       Used to calculate number of Placement Groups to create
                       for pool.
        :type weight: Optional[float]
        :returns: Dictionary with kwarg name as key.
        :rtype: Dict[str,any]
        :raises: AssertionError
        """
        return {
            'app-name': app_name,
            'compression-algorithm': compression_algorithm,
            'compression-mode': compression_mode,
            'compression-required-ratio': compression_required_ratio,
            'compression-min-blob-size': compression_min_blob_size,
            'compression-min-blob-size-hdd': compression_min_blob_size_hdd,
            'compression-min-blob-size-ssd': compression_min_blob_size_ssd,
            'compression-max-blob-size': compression_max_blob_size,
            'compression-max-blob-size-hdd': compression_max_blob_size_hdd,
            'compression-max-blob-size-ssd': compression_max_blob_size_ssd,
            'group': group,
            'max-bytes': max_bytes,
            'max-objects': max_objects,
            'group-namespace': namespace,
            'rbd-mirroring-mode': rbd_mirroring_mode,
            'weight': weight,
        }

    def add_op_create_replicated_pool(self, name, replica_count=3, pg_num=None,
                                      **kwargs):
        """Adds an operation to create a replicated pool.

        Refer to docstring for ``_partial_build_common_op_create`` for
        documentation of keyword arguments.

        :param name: Name of pool to create
        :type name: str
        :param replica_count: Number of copies Ceph should keep of your data.
        :type replica_count: int
        :param pg_num: Request specific number of Placement Groups to create
                       for pool.
        :type pg_num: int
        :raises: AssertionError if provided data is of invalid type/range
        """
        if pg_num and kwargs.get('weight'):
            raise ValueError('pg_num and weight are mutually exclusive')

        op = {
            'op': 'create-pool',
            'name': name,
            'replicas': replica_count,
            'pg_num': pg_num,
        }
        op.update(self._partial_build_common_op_create(**kwargs))

        # Initialize Pool-object to validate type and range of ops.
        pool = ReplicatedPool('dummy-service', op=op)
        pool.validate()

        self.add_op(op)

    def add_op_create_erasure_pool(self, name, erasure_profile=None,
                                   allow_ec_overwrites=False, **kwargs):
        """Adds an operation to create a erasure coded pool.

        Refer to docstring for ``_partial_build_common_op_create`` for
        documentation of keyword arguments.

        :param name: Name of pool to create
        :type name: str
        :param erasure_profile: Name of erasure code profile to use.  If not
                                set the ceph-mon unit handling the broker
                                request will set its default value.
        :type erasure_profile: str
        :param allow_ec_overwrites: allow EC pools to be overridden
        :type allow_ec_overwrites: bool
        :raises: AssertionError if provided data is of invalid type/range
        """
        op = {
            'op': 'create-pool',
            'name': name,
            'pool-type': 'erasure',
            'erasure-profile': erasure_profile,
            'allow-ec-overwrites': allow_ec_overwrites,
        }
        op.update(self._partial_build_common_op_create(**kwargs))

        # Initialize Pool-object to validate type and range of ops.
        pool = ErasurePool('dummy-service', op)
        pool.validate()

        self.add_op(op)

    def add_op_create_erasure_profile(self, name,
                                      erasure_type='jerasure',
                                      erasure_technique=None,
                                      k=None, m=None,
                                      failure_domain=None,
                                      lrc_locality=None,
                                      shec_durability_estimator=None,
                                      clay_helper_chunks=None,
                                      device_class=None,
                                      clay_scalar_mds=None,
                                      lrc_crush_locality=None):
        """Adds an operation to create a erasure coding profile.

        :param name: Name of profile to create
        :type name: str
        :param erasure_type: Which of the erasure coding plugins should be used
        :type erasure_type: string
        :param erasure_technique: EC plugin technique to use
        :type erasure_technique: string
        :param k: Number of data chunks
        :type k: int
        :param m: Number of coding chunks
        :type m: int
        :param lrc_locality: Group the coding and data chunks into sets of size locality
                             (lrc plugin)
        :type lrc_locality: int
        :param durability_estimator: The number of parity chunks each of which includes
                                     a data chunk in its calculation range (shec plugin)
        :type durability_estimator: int
        :param helper_chunks: The number of helper chunks to use for recovery operations
                              (clay plugin)
        :type: helper_chunks: int
        :param failure_domain: Type of failure domain from Ceph bucket types
                               to be used
        :type failure_domain: string
        :param device_class: Device class to use for profile (ssd, hdd)
        :type device_class: string
        :param clay_scalar_mds: Plugin to use for CLAY layered construction
                                (jerasure|isa|shec)
        :type clay_scaler_mds: string
        :param lrc_crush_locality: Type of crush bucket in which set of chunks
                                   defined by lrc_locality will be stored.
        :type lrc_crush_locality: string
        """
        self.add_op({'op': 'create-erasure-profile',
                     'name': name,
                     'k': k,
                     'm': m,
                     'l': lrc_locality,
                     'c': shec_durability_estimator,
                     'd': clay_helper_chunks,
                     'erasure-type': erasure_type,
                     'erasure-technique': erasure_technique,
                     'failure-domain': failure_domain,
                     'device-class': device_class,
                     'scalar-mds': clay_scalar_mds,
                     'crush-locality': lrc_crush_locality})

    def set_ops(self, ops):
        """Set request ops to provided value.

        Useful for injecting ops that come from a previous request
        to allow comparisons to ensure validity.
        """
        self.ops = ops

    @property
    def request(self):
        return json.dumps({'api-version': self.api_version, 'ops': self.ops,
                           'request-id': self.request_id})

    def _ops_equal(self, other):
        keys_to_compare = [
            'replicas', 'name', 'op', 'pg_num', 'group-permission',
            'object-prefix-permissions',
        ]
        keys_to_compare += list(self._partial_build_common_op_create().keys())
        if len(self.ops) == len(other.ops):
            for req_no in range(0, len(self.ops)):
                for key in keys_to_compare:
                    if self.ops[req_no].get(key) != other.ops[req_no].get(key):
                        return False
        else:
            return False
        return True

    def __eq__(self, other):
        if not isinstance(other, self.__class__):
            return False
        if self.api_version == other.api_version and \
                self._ops_equal(other):
            return True
        else:
            return False

    def __ne__(self, other):
        return not self.__eq__(other)


class CephBrokerRsp(object):
    """Ceph broker response.

    Response is json-decoded and contents provided as methods/properties.

    The API is versioned and defaults to version 1.
    """

    def __init__(self, encoded_rsp):
        self.api_version = None
        self.rsp = json.loads(encoded_rsp)

    @property
    def request_id(self):
        return self.rsp.get('request-id')

    @property
    def exit_code(self):
        return self.rsp.get('exit-code')

    @property
    def exit_msg(self):
        return self.rsp.get('stderr')


# Ceph Broker Conversation:
# If a charm needs an action to be taken by ceph it can create a CephBrokerRq
# and send that request to ceph via the ceph relation. The CephBrokerRq has a
# unique id so that the client can identity which CephBrokerRsp is associated
# with the request. Ceph will also respond to each client unit individually
# creating a response key per client unit eg glance/0 will get a CephBrokerRsp
# via key broker-rsp-glance-0
#
# To use this the charm can just do something like:
#
# from charmhelpers.contrib.storage.linux.ceph import (
#     send_request_if_needed,
#     is_request_complete,
#     CephBrokerRq,
# )
#
# @hooks.hook('ceph-relation-changed')
# def ceph_changed():
#     rq = CephBrokerRq()
#     rq.add_op_create_pool(name='poolname', replica_count=3)
#
#     if is_request_complete(rq):
#         <Request complete actions>
#     else:
#         send_request_if_needed(get_ceph_request())
#
# CephBrokerRq and CephBrokerRsp are serialized into JSON. Below is an example
# of glance having sent a request to ceph which ceph has successfully processed
#  'ceph:8': {
#      'ceph/0': {
#          'auth': 'cephx',
#          'broker-rsp-glance-0': '{"request-id": "0bc7dc54", "exit-code": 0}',
#          'broker_rsp': '{"request-id": "0da543b8", "exit-code": 0}',
#          'ceph-public-address': '10.5.44.103',
#          'key': 'AQCLDttVuHXINhAAvI144CB09dYchhHyTUY9BQ==',
#          'private-address': '10.5.44.103',
#      },
#      'glance/0': {
#          'broker_req': ('{"api-version": 1, "request-id": "0bc7dc54", '
#                         '"ops": [{"replicas": 3, "name": "glance", '
#                         '"op": "create-pool"}]}'),
#          'private-address': '10.5.44.109',
#      },
#  }

def get_previous_request(rid):
    """Return the last ceph broker request sent on a given relation

    :param rid: Relation id to query for request
    :type rid: str
    :returns: CephBrokerRq object or None if relation data not found.
    :rtype: Optional[CephBrokerRq]
    """
    broker_req = relation_get(attribute='broker_req', rid=rid,
                              unit=local_unit())
    if broker_req:
        return CephBrokerRq(raw_request_data=broker_req)


def get_request_states(request, relation='ceph'):
    """Return a dict of requests per relation id with their corresponding
       completion state.

    This allows a charm, which has a request for ceph, to see whether there is
    an equivalent request already being processed and if so what state that
    request is in.

    @param request: A CephBrokerRq object
    """
    complete = []
    requests = {}
    for rid in relation_ids(relation):
        complete = False
        previous_request = get_previous_request(rid)
        if request == previous_request:
            sent = True
            complete = is_request_complete_for_rid(previous_request, rid)
        else:
            sent = False
            complete = False

        requests[rid] = {
            'sent': sent,
            'complete': complete,
        }

    return requests


def is_request_sent(request, relation='ceph'):
    """Check to see if a functionally equivalent request has already been sent

    Returns True if a similair request has been sent

    @param request: A CephBrokerRq object
    """
    states = get_request_states(request, relation=relation)
    for rid in states.keys():
        if not states[rid]['sent']:
            return False

    return True


def is_request_complete(request, relation='ceph'):
    """Check to see if a functionally equivalent request has already been
    completed

    Returns True if a similair request has been completed

    @param request: A CephBrokerRq object
    """
    states = get_request_states(request, relation=relation)
    for rid in states.keys():
        if not states[rid]['complete']:
            return False

    return True


def is_request_complete_for_rid(request, rid):
    """Check if a given request has been completed on the given relation

    @param request: A CephBrokerRq object
    @param rid: Relation ID
    """
    broker_key = get_broker_rsp_key()
    for unit in related_units(rid):
        rdata = relation_get(rid=rid, unit=unit)
        if rdata.get(broker_key):
            rsp = CephBrokerRsp(rdata.get(broker_key))
            if rsp.request_id == request.request_id:
                if not rsp.exit_code:
                    return True
        else:
            # The remote unit sent no reply targeted at this unit so either the
            # remote ceph cluster does not support unit targeted replies or it
            # has not processed our request yet.
            if rdata.get('broker_rsp'):
                request_data = json.loads(rdata['broker_rsp'])
                if request_data.get('request-id'):
                    log('Ignoring legacy broker_rsp without unit key as remote '
                        'service supports unit specific replies', level=DEBUG)
                else:
                    log('Using legacy broker_rsp as remote service does not '
                        'supports unit specific replies', level=DEBUG)
                    rsp = CephBrokerRsp(rdata['broker_rsp'])
                    if not rsp.exit_code:
                        return True

    return False


def get_broker_rsp_key():
    """Return broker response key for this unit

    This is the key that ceph is going to use to pass request status
    information back to this unit
    """
    return 'broker-rsp-' + local_unit().replace('/', '-')


def send_request_if_needed(request, relation='ceph'):
    """Send broker request if an equivalent request has not already been sent

    @param request: A CephBrokerRq object
    """
    if is_request_sent(request, relation=relation):
        log('Request already sent but not complete, not sending new request',
            level=DEBUG)
    else:
        for rid in relation_ids(relation):
            log('Sending request {}'.format(request.request_id), level=DEBUG)
            relation_set(relation_id=rid, broker_req=request.request)
            relation_set(relation_id=rid, relation_settings={'unit-name': local_unit()})


def has_broker_rsp(rid=None, unit=None):
    """Return True if the broker_rsp key is 'truthy' (i.e. set to something) in the relation data.

    :param rid: The relation to check (default of None means current relation)
    :type rid: Union[str, None]
    :param unit: The remote unit to check (default of None means current unit)
    :type unit: Union[str, None]
    :returns: True if broker key exists and is set to something 'truthy'
    :rtype: bool
    """
    rdata = relation_get(rid=rid, unit=unit) or {}
    broker_rsp = rdata.get(get_broker_rsp_key())
    return True if broker_rsp else False


def is_broker_action_done(action, rid=None, unit=None):
    """Check whether broker action has completed yet.

    @param action: name of action to be performed
    @returns True if action complete otherwise False
    """
    rdata = relation_get(rid=rid, unit=unit) or {}
    broker_rsp = rdata.get(get_broker_rsp_key())
    if not broker_rsp:
        return False

    rsp = CephBrokerRsp(broker_rsp)
    unit_name = local_unit().partition('/')[2]
    key = "unit_{}_ceph_broker_action.{}".format(unit_name, action)
    kvstore = kv()
    val = kvstore.get(key=key)
    if val and val == rsp.request_id:
        return True

    return False


def mark_broker_action_done(action, rid=None, unit=None):
    """Mark action as having been completed.

    @param action: name of action to be performed
    @returns None
    """
    rdata = relation_get(rid=rid, unit=unit) or {}
    broker_rsp = rdata.get(get_broker_rsp_key())
    if not broker_rsp:
        return

    rsp = CephBrokerRsp(broker_rsp)
    unit_name = local_unit().partition('/')[2]
    key = "unit_{}_ceph_broker_action.{}".format(unit_name, action)
    kvstore = kv()
    kvstore.set(key=key, value=rsp.request_id)
    kvstore.flush()


class CephConfContext(object):
    """Ceph config (ceph.conf) context.

    Supports user-provided Ceph configuration settings. Use can provide a
    dictionary as the value for the config-flags charm option containing
    Ceph configuration settings keyede by their section in ceph.conf.
    """
    def __init__(self, permitted_sections=None):
        self.permitted_sections = permitted_sections or []

    def __call__(self):
        conf = config('config-flags')
        if not conf:
            return {}

        conf = config_flags_parser(conf)
        if not isinstance(conf, dict):
            log("Provided config-flags is not a dictionary - ignoring",
                level=WARNING)
            return {}

        permitted = self.permitted_sections
        if permitted:
            diff = set(conf.keys()).difference(set(permitted))
            if diff:
                log("Config-flags contains invalid keys '%s' - they will be "
                    "ignored" % (', '.join(diff)), level=WARNING)

        ceph_conf = {}
        for key in conf:
            if permitted and key not in permitted:
                log("Ignoring key '%s'" % key, level=WARNING)
                continue

            ceph_conf[key] = conf[key]
        return ceph_conf


class CephOSDConfContext(CephConfContext):
    """Ceph config (ceph.conf) context.

    Consolidates settings from config-flags via CephConfContext with
    settings provided by the mons. The config-flag values are preserved in
    conf['osd'], settings from the mons which do not clash with config-flag
    settings are in conf['osd_from_client'] and finally settings which do
    clash are in conf['osd_from_client_conflict']. Rather than silently drop
    the conflicting settings they are provided in the context so they can be
    rendered commented out to give some visibility to the admin.
    """

    def __init__(self, permitted_sections=None):
        super(CephOSDConfContext, self).__init__(
            permitted_sections=permitted_sections)
        try:
            self.settings_from_mons = get_osd_settings('mon')
        except OSDSettingConflict:
            log(
                "OSD settings from mons are inconsistent, ignoring them",
                level=WARNING)
            self.settings_from_mons = {}

    def filter_osd_from_mon_settings(self):
        """Filter settings from client relation against config-flags.

        :returns: A tuple (
            ,config-flag values,
            ,client settings which do not conflict with config-flag values,
            ,client settings which confilct with config-flag values)
        :rtype: (OrderedDict, OrderedDict, OrderedDict)
        """
        ceph_conf = super(CephOSDConfContext, self).__call__()
        conflicting_entries = {}
        clear_entries = {}
        for key, value in self.settings_from_mons.items():
            if key in ceph_conf.get('osd', {}):
                if ceph_conf['osd'][key] != value:
                    conflicting_entries[key] = value
            else:
                clear_entries[key] = value
        clear_entries = _order_dict_by_key(clear_entries)
        conflicting_entries = _order_dict_by_key(conflicting_entries)
        return ceph_conf, clear_entries, conflicting_entries

    def __call__(self):
        """Construct OSD config context.

        Standard context with two additional special keys.
            osd_from_client_conflict: client settings which confilct with
                                      config-flag values
            osd_from_client: settings which do not conflict with config-flag
                             values

        :returns: OSD config context dict.
        :rtype: dict
        """
        conf, osd_clear, osd_conflict = self.filter_osd_from_mon_settings()
        conf['osd_from_client_conflict'] = osd_conflict
        conf['osd_from_client'] = osd_clear
        return conf
