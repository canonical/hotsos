# Copyright 2016 Canonical Ltd
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

import collections
import json
import os

from subprocess import check_call, check_output, CalledProcessError
from tempfile import NamedTemporaryFile

from charms_ceph.utils import (
    get_cephfs,
    get_osd_weight
)
from charms_ceph.crush_utils import Crushmap

from charmhelpers.core.hookenv import (
    log,
    DEBUG,
    INFO,
    ERROR,
)
from charmhelpers.contrib.storage.linux.ceph import (
    create_erasure_profile,
    delete_pool,
    erasure_profile_exists,
    get_osds,
    monitor_key_get,
    monitor_key_set,
    pool_exists,
    pool_set,
    remove_pool_snapshot,
    rename_pool,
    snapshot_pool,
    validator,
    ErasurePool,
    BasePool,
    ReplicatedPool,
)

# This comes from http://docs.ceph.com/docs/master/rados/operations/pools/
# This should do a decent job of preventing people from passing in bad values.
# It will give a useful error message

POOL_KEYS = {
    # "Ceph Key Name": [Python type, [Valid Range]]
    "size": [int],
    "min_size": [int],
    "crash_replay_interval": [int],
    "pgp_num": [int],  # = or < pg_num
    "crush_ruleset": [int],
    "hashpspool": [bool],
    "nodelete": [bool],
    "nopgchange": [bool],
    "nosizechange": [bool],
    "write_fadvise_dontneed": [bool],
    "noscrub": [bool],
    "nodeep-scrub": [bool],
    "hit_set_type": [str, ["bloom", "explicit_hash",
                           "explicit_object"]],
    "hit_set_count": [int, [1, 1]],
    "hit_set_period": [int],
    "hit_set_fpp": [float, [0.0, 1.0]],
    "cache_target_dirty_ratio": [float],
    "cache_target_dirty_high_ratio": [float],
    "cache_target_full_ratio": [float],
    "target_max_bytes": [int],
    "target_max_objects": [int],
    "cache_min_flush_age": [int],
    "cache_min_evict_age": [int],
    "fast_read": [bool],
    "allow_ec_overwrites": [bool],
    "compression_mode": [str, ["none", "passive", "aggressive", "force"]],
    "compression_algorithm": [str, ["lz4", "snappy", "zlib", "zstd"]],
    "compression_required_ratio": [float, [0.0, 1.0]],
    "crush_rule": [str],
}

CEPH_BUCKET_TYPES = [
    'osd',
    'host',
    'chassis',
    'rack',
    'row',
    'pdu',
    'pod',
    'room',
    'datacenter',
    'region',
    'root'
]


def decode_req_encode_rsp(f):
    """Decorator to decode incoming requests and encode responses."""

    def decode_inner(req):
        return json.dumps(f(json.loads(req)))

    return decode_inner


@decode_req_encode_rsp
def process_requests(reqs):
    """Process Ceph broker request(s).

    This is a versioned api. API version must be supplied by the client making
    the request.

    :param reqs: dict of request parameters.
    :returns: dict. exit-code and reason if not 0
    """
    request_id = reqs.get('request-id')
    try:
        version = reqs.get('api-version')
        if version == 1:
            log('Processing request {}'.format(request_id), level=DEBUG)
            resp = process_requests_v1(reqs['ops'])
            if request_id:
                resp['request-id'] = request_id

            return resp

    except Exception as exc:
        log(str(exc), level=ERROR)
        msg = ("Unexpected error occurred while processing requests: %s" %
               reqs)
        log(msg, level=ERROR)
        return {'exit-code': 1, 'stderr': msg}

    msg = ("Missing or invalid api version ({})".format(version))
    resp = {'exit-code': 1, 'stderr': msg}
    if request_id:
        resp['request-id'] = request_id

    return resp


def handle_create_erasure_profile(request, service):
    """Create an erasure profile.

    :param request: dict of request operations and params
    :param service: The ceph client to run the command under.
    :returns: dict. exit-code and reason if not 0
    """
    # "isa" | "lrc" | "shec" | "clay" or it defaults to "jerasure"
    erasure_type = request.get('erasure-type')
    # dependent on erasure coding type
    erasure_technique = request.get('erasure-technique')
    # "host" | "rack" | ...
    failure_domain = request.get('failure-domain')
    name = request.get('name')
    # Binary Distribution Matrix (BDM) parameters
    bdm_k = request.get('k')
    bdm_m = request.get('m')
    # LRC parameters
    bdm_l = request.get('l')
    crush_locality = request.get('crush-locality')
    # SHEC parameters
    bdm_c = request.get('c')
    # CLAY parameters
    bdm_d = request.get('d')
    scalar_mds = request.get('scalar-mds')
    # Device Class
    device_class = request.get('device-class')

    if failure_domain and failure_domain not in CEPH_BUCKET_TYPES:
        msg = "failure-domain must be one of {}".format(CEPH_BUCKET_TYPES)
        log(msg, level=ERROR)
        return {'exit-code': 1, 'stderr': msg}

    create_erasure_profile(service=service,
                           erasure_plugin_name=erasure_type,
                           profile_name=name,
                           failure_domain=failure_domain,
                           data_chunks=bdm_k,
                           coding_chunks=bdm_m,
                           locality=bdm_l,
                           durability_estimator=bdm_d,
                           helper_chunks=bdm_c,
                           scalar_mds=scalar_mds,
                           crush_locality=crush_locality,
                           device_class=device_class,
                           erasure_plugin_technique=erasure_technique)

    return {'exit-code': 0}


def handle_add_permissions_to_key(request, service):
    """Groups are defined by the key cephx.groups.(namespace-)?-(name). This
    key will contain a dict serialized to JSON with data about the group,
    including pools and members.

    A group can optionally have a namespace defined that will be used to
    further restrict pool access.
    """
    resp = {'exit-code': 0}

    service_name = request.get('name')
    group_name = request.get('group')
    group_namespace = request.get('group-namespace')
    if group_namespace:
        group_name = "{}-{}".format(group_namespace, group_name)
    group = get_group(group_name=group_name)
    service_obj = get_service_groups(service=service_name,
                                     namespace=group_namespace)
    if request.get('object-prefix-permissions'):
        service_obj['object_prefix_perms'] = request.get(
            'object-prefix-permissions')
    format("Service object: {}".format(service_obj))
    permission = request.get('group-permission') or "rwx"
    if service_name not in group['services']:
        group['services'].append(service_name)
    save_group(group=group, group_name=group_name)
    if permission not in service_obj['group_names']:
        service_obj['group_names'][permission] = []
    if group_name not in service_obj['group_names'][permission]:
        service_obj['group_names'][permission].append(group_name)
    save_service(service=service_obj, service_name=service_name)
    service_obj['groups'] = _build_service_groups(service_obj,
                                                  group_namespace)
    update_service_permissions(service_name, service_obj, group_namespace)

    return resp


def handle_set_key_permissions(request, service):
    """Ensure the key has the requested permissions."""
    permissions = request.get('permissions')
    client = request.get('client')
    call = ['ceph', '--id', service, 'auth', 'caps',
            'client.{}'.format(client)] + permissions
    try:
        check_call(call)
    except CalledProcessError as e:
        log("Error updating key capabilities: {}".format(e), level=ERROR)


def update_service_permissions(service, service_obj=None, namespace=None):
    """Update the key permissions for the named client in Ceph"""
    if not service_obj:
        service_obj = get_service_groups(service=service, namespace=namespace)
    permissions = pool_permission_list_for_service(service_obj)
    call = ['ceph', 'auth', 'caps', 'client.{}'.format(service)] + permissions
    try:
        check_call(call)
    except CalledProcessError as e:
        log("Error updating key capabilities: {}".format(e))


def add_pool_to_group(pool, group, namespace=None):
    """Add a named pool to a named group"""
    group_name = group
    if namespace:
        group_name = "{}-{}".format(namespace, group_name)
    group = get_group(group_name=group_name)
    if pool not in group['pools']:
        group["pools"].append(pool)
    save_group(group, group_name=group_name)
    for service in group['services']:
        update_service_permissions(service, namespace=namespace)


def pool_permission_list_for_service(service):
    """Build the permission string for Ceph for a given service"""
    permissions = []
    permission_types = collections.OrderedDict()
    for permission, group in sorted(service["group_names"].items()):
        if permission not in permission_types:
            permission_types[permission] = []
        for item in group:
            permission_types[permission].append(item)
    for permission, groups in permission_types.items():
        permission = "allow {}".format(permission)
        for group in groups:
            for pool in service['groups'][group].get('pools', []):
                permissions.append("{} pool={}".format(permission, pool))
    for permission, prefixes in sorted(
            service.get("object_prefix_perms", {}).items()):
        for prefix in prefixes:
            permissions.append("allow {} object_prefix {}".format(permission,
                                                                  prefix))
    return ['mon', 'allow r, allow command "osd blacklist"',
            'osd', ', '.join(permissions)]


def get_service_groups(service, namespace=None):
    """Services are objects stored with some metadata, they look like (for a
    service named "nova"):
    {
        group_names: {'rwx': ['images']},
        groups: {}
    }
    After populating the group, it looks like:
    {
        group_names: {'rwx': ['images']},
        groups: {
            'images': {
                pools: ['glance'],
                services: ['nova']
            }
        }
    }
    """
    service_json = monitor_key_get(service='admin',
                                   key="cephx.services.{}".format(service))
    try:
        service = json.loads(service_json)
    except (TypeError, ValueError):
        service = None
    if service:
        service['groups'] = _build_service_groups(service, namespace)
    else:
        service = {'group_names': {}, 'groups': {}}
    return service


def _build_service_groups(service, namespace=None):
    """Rebuild the 'groups' dict for a service group

    :returns: dict: dictionary keyed by group name of the following
                    format:

                    {
                        'images': {
                            pools: ['glance'],
                            services: ['nova', 'glance]
                         },
                         'vms':{
                            pools: ['nova'],
                            services: ['nova']
                         }
                    }
    """
    all_groups = {}
    for groups in service['group_names'].values():
        for group in groups:
            name = group
            if namespace:
                name = "{}-{}".format(namespace, name)
            all_groups[group] = get_group(group_name=name)
    return all_groups


def get_group(group_name):
    """A group is a structure to hold data about a named group, structured as:
    {
        pools: ['glance'],
        services: ['nova']
    }
    """
    group_key = get_group_key(group_name=group_name)
    group_json = monitor_key_get(service='admin', key=group_key)
    try:
        group = json.loads(group_json)
    except (TypeError, ValueError):
        group = None
    if not group:
        group = {
            'pools': [],
            'services': []
        }
    return group


def save_service(service_name, service):
    """Persist a service in the monitor cluster"""
    service['groups'] = {}
    return monitor_key_set(service='admin',
                           key="cephx.services.{}".format(service_name),
                           value=json.dumps(service, sort_keys=True))


def save_group(group, group_name):
    """Persist a group in the monitor cluster"""
    group_key = get_group_key(group_name=group_name)
    return monitor_key_set(service='admin',
                           key=group_key,
                           value=json.dumps(group, sort_keys=True))


def get_group_key(group_name):
    """Build group key"""
    return 'cephx.groups.{}'.format(group_name)


def handle_erasure_pool(request, service):
    """Create a new erasure coded pool.

    :param request: dict of request operations and params.
    :param service: The ceph client to run the command under.
    :returns: dict. exit-code and reason if not 0.
    """
    pool_name = request.get('name')
    erasure_profile = request.get('erasure-profile')
    group_name = request.get('group')

    if erasure_profile is None:
        erasure_profile = "default-canonical"

    if group_name:
        group_namespace = request.get('group-namespace')
        # Add the pool to the group named "group_name"
        add_pool_to_group(pool=pool_name,
                          group=group_name,
                          namespace=group_namespace)

    # TODO: Default to 3/2 erasure coding. I believe this requires min 5 osds
    if not erasure_profile_exists(service=service, name=erasure_profile):
        # TODO: Fail and tell them to create the profile or default
        msg = ("erasure-profile {} does not exist.  Please create it with: "
               "create-erasure-profile".format(erasure_profile))
        log(msg, level=ERROR)
        return {'exit-code': 1, 'stderr': msg}

    try:
        pool = ErasurePool(service=service,
                           op=request)
    except KeyError:
        msg = "Missing parameter."
        log(msg, level=ERROR)
        return {'exit-code': 1, 'stderr': msg}

    # Ok make the erasure pool
    if not pool_exists(service=service, name=pool_name):
        log("Creating pool '{}' (erasure_profile={})"
            .format(pool.name, erasure_profile), level=INFO)
        pool.create()

    # Set/update properties that are allowed to change after pool creation.
    pool.update()


def handle_replicated_pool(request, service):
    """Create a new replicated pool.

    :param request: dict of request operations and params.
    :param service: The ceph client to run the command under.
    :returns: dict. exit-code and reason if not 0.
    """
    pool_name = request.get('name')
    group_name = request.get('group')

    # Optional params
    # NOTE: Check this against the handling in the Pool classes, reconcile and
    # remove.
    pg_num = request.get('pg_num')
    replicas = request.get('replicas')
    if pg_num:
        # Cap pg_num to max allowed just in case.
        osds = get_osds(service)
        if osds:
            pg_num = min(pg_num, (len(osds) * 100 // replicas))
            request.update({'pg_num': pg_num})

    if group_name:
        group_namespace = request.get('group-namespace')
        # Add the pool to the group named "group_name"
        add_pool_to_group(pool=pool_name,
                          group=group_name,
                          namespace=group_namespace)

    try:
        pool = ReplicatedPool(service=service,
                              op=request)
    except KeyError:
        msg = "Missing parameter."
        log(msg, level=ERROR)
        return {'exit-code': 1, 'stderr': msg}

    if not pool_exists(service=service, name=pool_name):
        log("Creating pool '{}' (replicas={})".format(pool.name, replicas),
            level=INFO)
        pool.create()
    else:
        log("Pool '{}' already exists - skipping create".format(pool.name),
            level=DEBUG)

    # Set/update properties that are allowed to change after pool creation.
    pool.update()


def handle_create_cache_tier(request, service):
    """Create a cache tier on a cold pool.  Modes supported are
    "writeback" and "readonly".

    :param request: dict of request operations and params
    :param service: The ceph client to run the command under.
    :returns: dict. exit-code and reason if not 0
    """
    # mode = "writeback" | "readonly"
    storage_pool = request.get('cold-pool')
    cache_pool = request.get('hot-pool')
    cache_mode = request.get('mode')

    if cache_mode is None:
        cache_mode = "writeback"

    # cache and storage pool must exist first
    if not pool_exists(service=service, name=storage_pool) or not pool_exists(
            service=service, name=cache_pool):
        msg = ("cold-pool: {} and hot-pool: {} must exist. Please create "
               "them first".format(storage_pool, cache_pool))
        log(msg, level=ERROR)
        return {'exit-code': 1, 'stderr': msg}

    p = BasePool(service=service, name=storage_pool)
    p.add_cache_tier(cache_pool=cache_pool, mode=cache_mode)


def handle_remove_cache_tier(request, service):
    """Remove a cache tier from the cold pool.

    :param request: dict of request operations and params
    :param service: The ceph client to run the command under.
    :returns: dict. exit-code and reason if not 0
    """
    storage_pool = request.get('cold-pool')
    cache_pool = request.get('hot-pool')
    # cache and storage pool must exist first
    if not pool_exists(service=service, name=storage_pool) or not pool_exists(
            service=service, name=cache_pool):
        msg = ("cold-pool: {} or hot-pool: {} doesn't exist. Not "
               "deleting cache tier".format(storage_pool, cache_pool))
        log(msg, level=ERROR)
        return {'exit-code': 1, 'stderr': msg}

    pool = BasePool(name=storage_pool, service=service)
    pool.remove_cache_tier(cache_pool=cache_pool)


def handle_set_pool_value(request, service, coerce=False):
    """Sets an arbitrary pool value.

    :param request: dict of request operations and params
    :param service: The ceph client to run the command under.
    :param coerce: Try to parse/coerce the value into the correct type.
                   Used by the action code that only gets Str from Juju
    :returns: dict. exit-code and reason if not 0
    """
    # Set arbitrary pool values
    params = {'pool': request.get('name'),
              'key': request.get('key'),
              'value': request.get('value')}
    if params['key'] not in POOL_KEYS:
        msg = "Invalid key '{}'".format(params['key'])
        log(msg, level=ERROR)
        return {'exit-code': 1, 'stderr': msg}

    # Get the validation method
    validator_params = POOL_KEYS[params['key']]
    # BUG: #1838650 - the function needs to try to coerce the value param to
    # the type required for the validator to pass.  Note, if this blows, then
    # the param isn't parsable to the correct type.
    if coerce:
        try:
            params['value'] = validator_params[0](params['value'])
        except ValueError:
            raise RuntimeError("Value {} isn't of type {}"
                               .format(params['value'], validator_params[0]))
    # end of BUG: #1838650
    if len(validator_params) == 1:
        # Validate that what the user passed is actually legal per Ceph's rules
        validator(params['value'], validator_params[0])
    else:
        # Validate that what the user passed is actually legal per Ceph's rules
        validator(params['value'], validator_params[0], validator_params[1])

    # Set the value
    pool_set(service=service, pool_name=params['pool'], key=params['key'],
             value=params['value'])


def handle_rgw_regionmap_update(request, service):
    """Change the radosgw region map.

    :param request: dict of request operations and params
    :param service: The ceph client to run the command under.
    :returns: dict. exit-code and reason if not 0
    """
    name = request.get('client-name')
    if not name:
        msg = "Missing rgw-region or client-name params"
        log(msg, level=ERROR)
        return {'exit-code': 1, 'stderr': msg}
    try:
        check_output(['radosgw-admin',
                      '--id', service,
                      'regionmap', 'update', '--name', name])
    except CalledProcessError as err:
        log(err.output, level=ERROR)
        return {'exit-code': 1, 'stderr': err.output}


def handle_rgw_regionmap_default(request, service):
    """Create a radosgw region map.

    :param request: dict of request operations and params
    :param service: The ceph client to run the command under.
    :returns: dict. exit-code and reason if not 0
    """
    region = request.get('rgw-region')
    name = request.get('client-name')
    if not region or not name:
        msg = "Missing rgw-region or client-name params"
        log(msg, level=ERROR)
        return {'exit-code': 1, 'stderr': msg}
    try:
        check_output(
            [
                'radosgw-admin',
                '--id', service,
                'regionmap',
                'default',
                '--rgw-region', region,
                '--name', name])
    except CalledProcessError as err:
        log(err.output, level=ERROR)
        return {'exit-code': 1, 'stderr': err.output}


def handle_rgw_zone_set(request, service):
    """Create a radosgw zone.

    :param request: dict of request operations and params
    :param service: The ceph client to run the command under.
    :returns: dict. exit-code and reason if not 0
    """
    json_file = request.get('zone-json')
    name = request.get('client-name')
    region_name = request.get('region-name')
    zone_name = request.get('zone-name')
    if not json_file or not name or not region_name or not zone_name:
        msg = "Missing json-file or client-name params"
        log(msg, level=ERROR)
        return {'exit-code': 1, 'stderr': msg}
    infile = NamedTemporaryFile(delete=False)
    with open(infile.name, 'w') as infile_handle:
        infile_handle.write(json_file)
    try:
        check_output(
            [
                'radosgw-admin',
                '--id', service,
                'zone',
                'set',
                '--rgw-zone', zone_name,
                '--infile', infile.name,
                '--name', name,
            ]
        )
    except CalledProcessError as err:
        log(err.output, level=ERROR)
        return {'exit-code': 1, 'stderr': err.output}
    os.unlink(infile.name)


def handle_put_osd_in_bucket(request, service):
    """Move an osd into a specified crush bucket.

    :param request: dict of request operations and params
    :param service: The ceph client to run the command under.
    :returns: dict. exit-code and reason if not 0
    """
    osd_id = request.get('osd')
    target_bucket = request.get('bucket')
    if not osd_id or not target_bucket:
        msg = "Missing OSD ID or Bucket"
        log(msg, level=ERROR)
        return {'exit-code': 1, 'stderr': msg}
    crushmap = Crushmap()
    try:
        crushmap.ensure_bucket_is_present(target_bucket)
        check_output(
            [
                'ceph',
                '--id', service,
                'osd',
                'crush',
                'set',
                str(osd_id),
                str(get_osd_weight(osd_id)),
                "root={}".format(target_bucket)
            ]
        )

    except Exception as exc:
        msg = "Failed to move OSD " \
              "{} into Bucket {} :: {}".format(osd_id, target_bucket, exc)
        log(msg, level=ERROR)
        return {'exit-code': 1, 'stderr': msg}


def handle_rgw_create_user(request, service):
    """Create a new rados gateway user.

    :param request: dict of request operations and params
    :param service: The ceph client to run the command under.
    :returns: dict. exit-code and reason if not 0
    """
    user_id = request.get('rgw-uid')
    display_name = request.get('display-name')
    name = request.get('client-name')
    if not name or not display_name or not user_id:
        msg = "Missing client-name, display-name or rgw-uid"
        log(msg, level=ERROR)
        return {'exit-code': 1, 'stderr': msg}
    try:
        create_output = check_output(
            [
                'radosgw-admin',
                '--id', service,
                'user',
                'create',
                '--uid', user_id,
                '--display-name', display_name,
                '--name', name,
                '--system'
            ]
        )
        try:
            user_json = json.loads(str(create_output.decode('UTF-8')))
            return {'exit-code': 0, 'user': user_json}
        except ValueError as err:
            log(err, level=ERROR)
            return {'exit-code': 1, 'stderr': err}

    except CalledProcessError as err:
        log(err.output, level=ERROR)
        return {'exit-code': 1, 'stderr': err.output}


def handle_create_cephfs(request, service):
    """Create a new cephfs.

    :param request: The broker request
    :param service: The ceph client to run the command under.
    :returns: dict. exit-code and reason if not 0
    """
    cephfs_name = request.get('mds_name')
    data_pool = request.get('data_pool')
    extra_pools = request.get('extra_pools', None) or []
    metadata_pool = request.get('metadata_pool')
    # Check if the user params were provided
    if not cephfs_name or not data_pool or not metadata_pool:
        msg = "Missing mds_name, data_pool or metadata_pool params"
        log(msg, level=ERROR)
        return {'exit-code': 1, 'stderr': msg}

    # Sanity check that the required pools exist
    for pool_name in [data_pool, metadata_pool] + extra_pools:
        if not pool_exists(service=service, name=pool_name):
            msg = "CephFS pool {} does not exist. Cannot create CephFS".format(
                pool_name)
            log(msg, level=ERROR)
            return {'exit-code': 1, 'stderr': msg}

    if get_cephfs(service=service):
        # CephFS new has already been called
        log("CephFS already created")
        return

        # Finally create CephFS
    try:
        check_output(["ceph",
                      '--id', service,
                      "fs", "new", cephfs_name,
                      metadata_pool,
                      data_pool])
    except CalledProcessError as err:
        if err.returncode == 22:
            log("CephFS already created")
            return
        else:
            log(err.output, level=ERROR)
            return {'exit-code': 1, 'stderr': err.output}
    for pool_name in extra_pools:
        cmd = ["ceph", '--id', service, "fs", "add_data_pool", cephfs_name,
               pool_name]
        try:
            check_output(cmd)
        except CalledProcessError as err:
            log(err.output, level=ERROR)
            return {'exit-code': 1, 'stderr': err.output}


def handle_rgw_region_set(request, service):
    # radosgw-admin region set --infile us.json --name client.radosgw.us-east-1
    """Set the rados gateway region.

    :param request: dict. The broker request.
    :param service: The ceph client to run the command under.
    :returns: dict. exit-code and reason if not 0
    """
    json_file = request.get('region-json')
    name = request.get('client-name')
    region_name = request.get('region-name')
    zone_name = request.get('zone-name')
    if not json_file or not name or not region_name or not zone_name:
        msg = "Missing json-file or client-name params"
        log(msg, level=ERROR)
        return {'exit-code': 1, 'stderr': msg}
    infile = NamedTemporaryFile(delete=False)
    with open(infile.name, 'w') as infile_handle:
        infile_handle.write(json_file)
    try:
        check_output(
            [
                'radosgw-admin',
                '--id', service,
                'region',
                'set',
                '--rgw-zone', zone_name,
                '--infile', infile.name,
                '--name', name,
            ]
        )
    except CalledProcessError as err:
        log(err.output, level=ERROR)
        return {'exit-code': 1, 'stderr': err.output}
    os.unlink(infile.name)


def process_requests_v1(reqs):
    """Process v1 requests.

    Takes a list of requests (dicts) and processes each one. If an error is
    found, processing stops and the client is notified in the response.

    Returns a response dict containing the exit code (non-zero if any
    operation failed along with an explanation).
    """
    ret = None
    log("Processing {} ceph broker requests".format(len(reqs)), level=INFO)
    for req in reqs:
        op = req.get('op')
        log("Processing op='{}'".format(op), level=DEBUG)
        # Use admin client since we do not have other client key locations
        # setup to use them for these operations.
        svc = 'admin'
        if op == "create-pool":
            pool_type = req.get('pool-type')  # "replicated" | "erasure"

            # Default to replicated if pool_type isn't given
            if pool_type == 'erasure':
                ret = handle_erasure_pool(request=req, service=svc)
            else:
                ret = handle_replicated_pool(request=req, service=svc)
        elif op == "create-cephfs":
            ret = handle_create_cephfs(request=req, service=svc)
        elif op == "create-cache-tier":
            ret = handle_create_cache_tier(request=req, service=svc)
        elif op == "remove-cache-tier":
            ret = handle_remove_cache_tier(request=req, service=svc)
        elif op == "create-erasure-profile":
            ret = handle_create_erasure_profile(request=req, service=svc)
        elif op == "delete-pool":
            pool = req.get('name')
            ret = delete_pool(service=svc, name=pool)
        elif op == "rename-pool":
            old_name = req.get('name')
            new_name = req.get('new-name')
            ret = rename_pool(service=svc, old_name=old_name,
                              new_name=new_name)
        elif op == "snapshot-pool":
            pool = req.get('name')
            snapshot_name = req.get('snapshot-name')
            ret = snapshot_pool(service=svc, pool_name=pool,
                                snapshot_name=snapshot_name)
        elif op == "remove-pool-snapshot":
            pool = req.get('name')
            snapshot_name = req.get('snapshot-name')
            ret = remove_pool_snapshot(service=svc, pool_name=pool,
                                       snapshot_name=snapshot_name)
        elif op == "set-pool-value":
            ret = handle_set_pool_value(request=req, service=svc)
        elif op == "rgw-region-set":
            ret = handle_rgw_region_set(request=req, service=svc)
        elif op == "rgw-zone-set":
            ret = handle_rgw_zone_set(request=req, service=svc)
        elif op == "rgw-regionmap-update":
            ret = handle_rgw_regionmap_update(request=req, service=svc)
        elif op == "rgw-regionmap-default":
            ret = handle_rgw_regionmap_default(request=req, service=svc)
        elif op == "rgw-create-user":
            ret = handle_rgw_create_user(request=req, service=svc)
        elif op == "move-osd-to-bucket":
            ret = handle_put_osd_in_bucket(request=req, service=svc)
        elif op == "add-permissions-to-key":
            ret = handle_add_permissions_to_key(request=req, service=svc)
        elif op == 'set-key-permissions':
            ret = handle_set_key_permissions(request=req, service=svc)
        else:
            msg = "Unknown operation '{}'".format(op)
            log(msg, level=ERROR)
            return {'exit-code': 1, 'stderr': msg}

    if type(ret) == dict and 'exit-code' in ret:
        return ret

    return {'exit-code': 0}
