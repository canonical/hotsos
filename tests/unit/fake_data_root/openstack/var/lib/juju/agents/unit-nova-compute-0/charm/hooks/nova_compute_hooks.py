#!/usr/bin/env python3
#
# Copyright 2016-2021 Canonical Ltd
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

import base64
import json
import platform
import sys
import uuid
import os
import subprocess
import grp
import shutil

import charmhelpers.core.unitdata as unitdata

from charmhelpers.core.hookenv import (
    Hooks,
    config,
    is_relation_made,
    local_unit,
    log,
    DEBUG,
    relation_ids,
    remote_service_name,
    related_units,
    relation_get,
    relation_set,
    service_name,
    UnregisteredHookError,
    status_set,
)
from charmhelpers.core.templating import (
    render
)
from charmhelpers.core.host import (
    service_restart,
    service_running,
    service_start,
    service_stop,
    write_file,
    umount,
    is_container,
    mkdir,
)
from charmhelpers.fetch import (
    apt_install,
    apt_purge,
    apt_update,
    filter_installed_packages,
)

import charmhelpers.contrib.openstack.context as ch_context

from charmhelpers.contrib.openstack.utils import (
    CompareOpenStackReleases,
    configure_installation_source,
    is_unit_paused_set,
    openstack_upgrade_available,
    os_release,
    pausable_restart_on_change as restart_on_change,
    series_upgrade_complete,
    series_upgrade_prepare,
)

from charmhelpers.contrib.storage.linux.ceph import (
    ensure_ceph_keyring,
    CephBrokerRq,
    CephBrokerRsp,
    delete_keyring,
    is_broker_action_done,
    mark_broker_action_done,
    get_broker_rsp_key,
    get_request_states,
    get_previous_request,
    send_application_name,
)
from charmhelpers.payload.execd import execd_preinstall
from nova_compute_utils import (
    create_libvirt_secret,
    determine_packages,
    import_authorized_keys,
    import_keystone_ca_cert,
    initialize_ssh_keys,
    migration_enabled,
    do_openstack_upgrade,
    public_ssh_key,
    restart_map,
    services,
    register_configs,
    NOVA_CONF,
    ceph_config_file, CEPH_SECRET,
    CEPH_BACKEND_SECRET,
    enable_shell, disable_shell,
    configure_lxd,
    fix_path_ownership,
    assert_charm_supports_ipv6,
    install_hugepages,
    get_hugepage_number,
    assess_status,
    set_ppc64_cpu_smt_state,
    remove_libvirt_network,
    network_manager,
    libvirt_daemon,
    LIBVIRT_TYPES,
    configure_local_ephemeral_storage,
    pause_unit_helper,
    resume_unit_helper,
    get_availability_zone,
    remove_old_packages,
    MULTIPATH_PACKAGES,
    USE_FQDN_KEY,
)

from charmhelpers.contrib.network.ip import (
    get_relation_ip,
)

from charmhelpers.core.unitdata import kv

from nova_compute_context import (
    nova_metadata_requirement,
    CEPH_SECRET_UUID,
    assert_libvirt_rbd_imagebackend_allowed,
    NovaAPIAppArmorContext,
    NovaComputeAppArmorContext,
    NovaNetworkAppArmorContext,
)
from charmhelpers.contrib.charmsupport import nrpe
from charmhelpers.core.sysctl import create as create_sysctl
from charmhelpers.contrib.hardening.harden import harden

from socket import gethostname

import charmhelpers.contrib.openstack.vaultlocker as vaultlocker

hooks = Hooks()
CONFIGS = register_configs()
MIGRATION_AUTH_TYPES = ["ssh"]
LIBVIRTD_PID = '/var/run/libvirtd.pid'


@hooks.hook('install.real')
@harden()
def install():
    status_set('maintenance', 'Executing pre-install')
    execd_preinstall()
    configure_installation_source(config('openstack-origin'))

    status_set('maintenance', 'Installing apt packages')
    apt_update()
    apt_install(determine_packages(), fatal=True)

    # Start migration to agent registration with FQDNs for newly installed
    # units with OpenStack release Stein or newer.
    release = os_release('nova-common')
    if CompareOpenStackReleases(release) >= 'stein':
        db = kv()
        db.set(USE_FQDN_KEY, True)
        db.flush()

    install_vaultlocker()


@hooks.hook('config-changed')
@restart_on_change(restart_map())
@harden()
def config_changed():

    if is_unit_paused_set():
        log("Do not run config_changed when paused", "WARNING")
        return

    if config('ephemeral-unmount'):
        umount(config('ephemeral-unmount'), persist=True)

    if config('prefer-ipv6'):
        status_set('maintenance', 'configuring ipv6')
        assert_charm_supports_ipv6()

    if (migration_enabled() and
            config('migration-auth-type') not in MIGRATION_AUTH_TYPES):
        message = ("Invalid migration-auth-type")
        status_set('blocked', message)
        raise Exception(message)
    global CONFIGS
    send_remote_restart = False
    if not config('action-managed-upgrade'):
        if openstack_upgrade_available('nova-common'):
            status_set('maintenance', 'Running openstack upgrade')
            do_openstack_upgrade(CONFIGS)
            send_remote_restart = True

    sysctl_settings = config('sysctl')
    if sysctl_settings and not is_container():
        create_sysctl(
            sysctl_settings,
            '/etc/sysctl.d/50-nova-compute.conf',
            # Some keys in the config may not exist in /proc/sys/net/.
            # For example, the conntrack module may not be loaded when
            # using lxd drivers insteam of kvm. In these cases, we
            # simply ignore the missing keys, rather than making time
            # consuming calls out to the filesystem to check for their
            # existence.
            ignore=True)

    remove_libvirt_network('default')

    if migration_enabled() and config('migration-auth-type') == 'ssh':
        # Check-in with nova-c-c and register new ssh key, if it has just been
        # generated.
        status_set('maintenance', 'SSH key exchange')
        initialize_ssh_keys()
        import_authorized_keys()

    if config('enable-resize') is True:
        enable_shell(user='nova')
        status_set('maintenance', 'SSH key exchange')
        initialize_ssh_keys(user='nova')
        import_authorized_keys(user='nova', prefix='nova')
    else:
        disable_shell(user='nova')

    if config('instances-path') is not None:
        fp = config('instances-path')
        if not os.path.exists(fp):
            mkdir(path=fp, owner='nova', group='nova', perms=0o775)
        fix_path_ownership(fp, user='nova')

    for rid in relation_ids('cloud-compute'):
        compute_joined(rid)

    for rid in relation_ids('neutron-plugin'):
        neutron_plugin_joined(rid, remote_restart=send_remote_restart)

    for rid in relation_ids('nova-ceilometer'):
        nova_ceilometer_joined(rid, remote_restart=send_remote_restart)

    if is_relation_made("nrpe-external-master"):
        update_nrpe_config()

    if config('hugepages'):
        install_hugepages()

    # Disable smt for ppc64, required for nova/libvirt/kvm
    arch = platform.machine()
    log('CPU architecture: {}'.format(arch))
    if arch in ['ppc64el', 'ppc64le']:
        set_ppc64_cpu_smt_state('off')

    # NOTE(jamespage): trigger any configuration related changes
    #                  for cephx permissions restrictions and
    #                  keys on disk for ceph-access backends
    for rid in relation_ids('ceph'):
        for unit in related_units(rid):
            ceph_changed(rid=rid, unit=unit)
    for rid in relation_ids('ceph-access'):
        for unit in related_units(rid):
            ceph_access(rid=rid, unit=unit)

    update_all_configs()

    install_vaultlocker()
    install_multipath()

    configure_local_ephemeral_storage()

    check_and_start_iscsid()


def update_all_configs():

    CONFIGS.write_all()

    NovaComputeAppArmorContext().setup_aa_profile()
    if (network_manager() in ['flatmanager', 'flatdhcpmanager'] and
            config('multi-host').lower() == 'yes'):
        NovaAPIAppArmorContext().setup_aa_profile()
        NovaNetworkAppArmorContext().setup_aa_profile()


def install_vaultlocker():
    """Determine whether vaultlocker is required and install"""
    if config('encrypt'):
        installed = len(filter_installed_packages(['vaultlocker'])) == 0
        if not installed:
            apt_install('vaultlocker', fatal=True)


def install_multipath():
    if config('use-multipath'):
        installed = len(filter_installed_packages(MULTIPATH_PACKAGES)) == 0
        if not installed:
            apt_install(MULTIPATH_PACKAGES, fatal=True)


@hooks.hook('amqp-relation-joined')
def amqp_joined(relation_id=None):
    relation_set(relation_id=relation_id,
                 username=config('rabbit-user'),
                 vhost=config('rabbit-vhost'))


@hooks.hook('amqp-relation-changed')
@hooks.hook('amqp-relation-departed')
@restart_on_change(restart_map())
def amqp_changed():
    if 'amqp' not in CONFIGS.complete_contexts():
        log('amqp relation incomplete. Peer not ready?')
        return
    CONFIGS.write(NOVA_CONF)


@hooks.hook('image-service-relation-changed')
@restart_on_change(restart_map())
def image_service_changed():
    if 'image-service' not in CONFIGS.complete_contexts():
        log('image-service relation incomplete. Peer not ready?')
        return
    CONFIGS.write(NOVA_CONF)


@hooks.hook('ephemeral-backend-relation-changed',
            'ephemeral-backend-relation-broken')
@restart_on_change(restart_map())
def ephemeral_backend_hook():
    if 'ephemeral-backend' not in CONFIGS.complete_contexts():
        log('ephemeral-backend relation incomplete. Peer not ready?')
        return
    CONFIGS.write(NOVA_CONF)


@hooks.hook('cloud-compute-relation-joined')
def compute_joined(rid=None):
    # NOTE(james-page) in MAAS environments the actual hostname is a CNAME
    # record so won't get scanned based on private-address which is an IP
    # add the hostname configured locally to the relation.
    settings = {
        'hostname': gethostname(),
        'private-address': get_relation_ip(
            'migration', cidr_network=config('libvirt-migration-network')),
    }

    az = get_availability_zone()
    if az:
        relation_set(relation_id=rid, availability_zone=az)

    if migration_enabled():
        auth_type = config('migration-auth-type')
        settings['migration_auth_type'] = auth_type
        if auth_type == 'ssh':
            settings['ssh_public_key'] = public_ssh_key()
        relation_set(relation_id=rid, **settings)
    if config('enable-resize'):
        settings['nova_ssh_public_key'] = public_ssh_key(user='nova')
        relation_set(relation_id=rid, **settings)


@hooks.hook('cloud-compute-relation-changed')
@restart_on_change(restart_map())
def compute_changed():
    # rewriting all configs to pick up possible net or vol manager
    # config advertised from controller.
    update_all_configs()
    import_authorized_keys()
    import_authorized_keys(user='nova', prefix='nova')
    import_keystone_ca_cert()


@hooks.hook('ironic-api-relation-changed')
@restart_on_change(restart_map())
def ironic_api_changed():
    CONFIGS.write(NOVA_CONF)


@hooks.hook('ceph-access-relation-joined')
@hooks.hook('ceph-relation-joined')
@restart_on_change(restart_map())
def ceph_joined():
    pkgs = filter_installed_packages(['ceph-common'])
    if pkgs:
        status_set('maintenance', 'Installing ceph-common package')
        apt_install(pkgs, fatal=True)
        # Bug 1427660
        if not is_unit_paused_set() and config('virt-type') in LIBVIRT_TYPES:
            service_restart(libvirt_daemon())
    send_application_name()


def get_ceph_request():
    rq = CephBrokerRq()
    if (config('libvirt-image-backend') == 'rbd' and
            assert_libvirt_rbd_imagebackend_allowed()):
        pool_name = config('rbd-pool')
        replicas = config('ceph-osd-replication-count')
        weight = config('ceph-pool-weight')
        bluestore_compression = ch_context.CephBlueStoreCompressionContext()

        if config('pool-type') == 'erasure-coded':
            # General EC plugin config
            plugin = config('ec-profile-plugin')
            technique = config('ec-profile-technique')
            device_class = config('ec-profile-device-class')
            metadata_pool_name = (
                config('ec-rbd-metadata-pool') or
                "{}-metadata".format(pool_name)
            )
            bdm_k = config('ec-profile-k')
            bdm_m = config('ec-profile-m')
            # LRC plugin config
            bdm_l = config('ec-profile-locality')
            crush_locality = config('ec-profile-crush-locality')
            # SHEC plugin config
            bdm_c = config('ec-profile-durability-estimator')
            # CLAY plugin config
            bdm_d = config('ec-profile-helper-chunks')
            scalar_mds = config('ec-profile-scalar-mds')
            # Profile name
            profile_name = (
                config('ec-profile-name') or
                "{}-profile".format(pool_name)
            )
            # Metadata sizing is approximately 1% of overall data weight
            # but is in effect driven by the number of rbd's rather than
            # their size - so it can be very lightweight.
            metadata_weight = weight * 0.01
            # Resize data pool weight to accommodate metadata weight
            weight = weight - metadata_weight
            # Create metadata pool
            rq.add_op_create_pool(
                name=metadata_pool_name, replica_count=replicas,
                weight=metadata_weight, group='vms', app_name='rbd'
            )

            # Create erasure profile
            rq.add_op_create_erasure_profile(
                name=profile_name,
                k=bdm_k, m=bdm_m,
                lrc_locality=bdm_l,
                lrc_crush_locality=crush_locality,
                shec_durability_estimator=bdm_c,
                clay_helper_chunks=bdm_d,
                clay_scalar_mds=scalar_mds,
                device_class=device_class,
                erasure_type=plugin,
                erasure_technique=technique
            )

            # Create EC data pool

            # NOTE(fnordahl): once we deprecate Python 3.5 support we can do
            # the unpacking of the BlueStore compression arguments as part of
            # the function arguments. Until then we need to build the dict
            # prior to the function call.
            kwargs = {
                'name': pool_name,
                'erasure_profile': profile_name,
                'weight': weight,
                'group': "vms",
                'app_name': "rbd",
                'allow_ec_overwrites': True
            }
            kwargs.update(bluestore_compression.get_kwargs())
            rq.add_op_create_erasure_pool(**kwargs)
        else:
            kwargs = {
                'name': pool_name,
                'replica_count': replicas,
                'weight': weight,
                'group': 'vms',
                'app_name': 'rbd',
            }
            kwargs.update(bluestore_compression.get_kwargs())
            rq.add_op_create_replicated_pool(**kwargs)

    if config('restrict-ceph-pools'):
        rq.add_op_request_access_to_group(
            name="volumes",
            object_prefix_permissions={'class-read': ['rbd_children']},
            permission='rwx')
        rq.add_op_request_access_to_group(
            name="images",
            object_prefix_permissions={'class-read': ['rbd_children']},
            permission='rwx')
        rq.add_op_request_access_to_group(
            name="vms",
            object_prefix_permissions={'class-read': ['rbd_children']},
            permission='rwx')
    return rq


@hooks.hook('ceph-relation-changed')
@restart_on_change(restart_map())
def ceph_changed(rid=None, unit=None):
    if 'ceph' not in CONFIGS.complete_contexts():
        log('ceph relation incomplete. Peer not ready?')
        return

    if not ensure_ceph_keyring(service=service_name(), user='nova',
                               group='nova'):
        log('Could not create ceph keyring: peer not ready?')
        return

    CONFIGS.write(ceph_config_file())
    CONFIGS.write(CEPH_SECRET)
    CONFIGS.write(NOVA_CONF)

    # With some refactoring, this can move into NovaComputeCephContext
    # and allow easily extended to support other compute flavors.
    key = relation_get(attribute='key', rid=rid, unit=unit)
    if config('virt-type') in ['kvm', 'qemu', 'lxc'] and key:
        create_libvirt_secret(secret_file=CEPH_SECRET,
                              secret_uuid=CEPH_SECRET_UUID, key=key)

    try:
        _handle_ceph_request()
    except ValueError as e:
        # The end user has most likely provided a invalid value for a
        # configuration option. Just log the traceback here, the end
        # user will be notified by assess_status() called at the end of
        # the hook execution.
        log('Caught ValueError, invalid value provided for '
            'configuration?: "{}"'.format(str(e)),
            level=DEBUG)


# TODO: Refactor this method moving part of this logic to charmhelpers,
# refacting the existing ones.
def _handle_ceph_request():
    """Handles the logic for sending and acknowledging Ceph broker requests."""

    # First, we create a request. We will test if this request is equivalent
    # to a previous one. If it is not, we will send it.
    request = get_ceph_request()

    log("New ceph request {} created.".format(request.request_id), level=DEBUG)

    # Here we will know if the new request is equivalent, and if it is, whether
    # it has completed, or just sent.
    states = get_request_states(request, relation='ceph')

    log("Request states: {}.".format(states), level=DEBUG)

    complete = True
    sent = True

    # According to existing ceph broker messaging logic, we are expecting only
    # 1 rid.
    for rid in states.keys():
        if not states[rid]['complete']:
            complete = False
        if not states[rid]['sent']:
            sent = False
        if not sent and not complete:
            break

    # If either complete or sent is True, then get_request_states has validated
    # that the current request is equivalent to a previously sent request.
    if complete:
        log('Previous request complete.')

        # If the request is complete, we need to restart nova once and mark it
        # restarted. The broker response comes from a specific unit, and can
        # only be read when this hook is invoked by the remote unit (the
        # broker), unless specifically queried for the given unit. Therefore,
        # we iterate across all units to find which has the broker response,
        # and we process the response regardless of this execution context.
        broker_rid, broker_unit = _get_broker_rid_unit_for_previous_request()

        # If we cannot determine which unit has the response, then it means
        # there is no response yet.
        if (broker_rid, broker_unit) == (None, None):
            log("Aborting because there is no broker response "
                "for any unit at the moment.", level=DEBUG)
            return

        # Ensure that nova-compute is restarted since only now can we
        # guarantee that ceph resources are ready, but only if not paused.
        if (not is_unit_paused_set() and
                not is_broker_action_done('nova_compute_restart', broker_rid,
                                          broker_unit)):
            log('Restarting Nova Compute as per request '
                '{}.'.format(request.request_id), level=DEBUG)
            service_restart('nova-compute')
            mark_broker_action_done('nova_compute_restart',
                                    broker_rid, broker_unit)
    else:
        if sent:
            log("Request {} already sent, not sending "
                "another.".format(request.request_id), level=DEBUG)
        else:
            log("Request {} not sent, sending it "
                "now.".format(request.request_id), level=DEBUG)
            for rid in relation_ids('ceph'):
                log('Sending request {}'.format(request.request_id),
                    level=DEBUG)
                relation_set(relation_id=rid, broker_req=request.request)


# TODO: Move this method to charmhelpers while refactoring the existing ones
def _get_broker_rid_unit_for_previous_request():
    """Gets the broker rid and unit combination that has a response for the
     previous sent request."""
    broker_key = get_broker_rsp_key()

    log("Broker key is {}.".format(broker_key), level=DEBUG)

    for rid in relation_ids('ceph'):
        previous_request = get_previous_request(rid)
        for unit in related_units(rid):
            rdata = relation_get(rid=rid, unit=unit)
            if rdata.get(broker_key):
                rsp = CephBrokerRsp(rdata.get(broker_key))
                if rsp.request_id == previous_request.request_id:
                    log("Found broker rid/unit: {}/{}".format(rid, unit),
                        level=DEBUG)
                    return rid, unit
    log("There is no broker response for any unit at the moment.", level=DEBUG)
    return None, None


@hooks.hook('ceph-relation-broken')
def ceph_broken():
    service = service_name()
    delete_keyring(service=service)
    update_all_configs()


@hooks.hook('amqp-relation-broken', 'image-service-relation-broken')
@restart_on_change(restart_map())
def relation_broken():
    update_all_configs()


@hooks.hook('upgrade-charm.real')
@harden()
def upgrade_charm():
    apt_install(filter_installed_packages(determine_packages()),
                fatal=True)
    # NOTE: ensure psutil install for hugepages configuration
    status_set('maintenance', 'Installing apt packages')
    apt_install(filter_installed_packages(['python-psutil']))
    packages_removed = remove_old_packages()
    if packages_removed and not is_unit_paused_set():
        log("Package purge detected, restarting services", "INFO")
        for s in services():
            service_restart(s)

    for r_id in relation_ids('amqp'):
        amqp_joined(relation_id=r_id)

    if is_relation_made('nrpe-external-master'):
        update_nrpe_config()

    # Fix previously wrongly created path permissions
    # LP: https://bugs.launchpad.net/charm-cinder-ceph/+bug/1779676
    asok_path = '/var/run/ceph/'
    gid = grp.getgrnam("kvm").gr_gid
    if gid and os.path.isdir(asok_path) and gid != os.stat(asok_path).st_gid:
        log("{} not owned by group 'kvm', fixing permissions."
            .format(asok_path))
        shutil.chown(asok_path, group='kvm')


@hooks.hook('nova-ceilometer-relation-joined')
def nova_ceilometer_joined(relid=None, remote_restart=False):
    if remote_restart:
        rel_settings = {
            'restart-trigger': str(uuid.uuid4())}
        relation_set(relation_id=relid, relation_settings=rel_settings)


@hooks.hook('nova-ceilometer-relation-changed')
@restart_on_change(restart_map())
def nova_ceilometer_relation_changed():
    update_all_configs()


@hooks.hook('nrpe-external-master-relation-joined',
            'nrpe-external-master-relation-changed')
def update_nrpe_config():
    # python-dbus is used by check_upstart_job
    apt_install('python-dbus')
    hostname = nrpe.get_nagios_hostname()
    current_unit = nrpe.get_nagios_unit_name()
    nrpe_setup = nrpe.NRPE(hostname=hostname)
    monitored_services = services()
    try:
        # qemu-kvm is a one-shot service
        monitored_services.remove('qemu-kvm')
    except ValueError:
        pass
    nrpe.add_init_service_checks(nrpe_setup, monitored_services, current_unit)
    nrpe_setup.write()


@hooks.hook('neutron-plugin-relation-joined')
def neutron_plugin_joined(relid=None, remote_restart=False):
    rel_settings = {
        'hugepage_number': get_hugepage_number(),
        'default_availability_zone': get_availability_zone()
    }
    if remote_restart:
        rel_settings['restart-trigger'] = str(uuid.uuid4())
    relation_set(relation_id=relid,
                 **rel_settings)


@hooks.hook('neutron-plugin-relation-changed')
@restart_on_change(restart_map())
def neutron_plugin_changed():
    enable_nova_metadata, _ = nova_metadata_requirement()
    if enable_nova_metadata:
        apt_update()
        apt_install(filter_installed_packages(['nova-api-metadata']),
                    fatal=True)
    else:
        apt_purge('nova-api-metadata', fatal=True)
    service_restart_handler(default_service='nova-compute')
    CONFIGS.write(NOVA_CONF)


# TODO(jamespage): Move this into charmhelpers for general reuse.
def service_restart_handler(relation_id=None, unit=None,
                            default_service=None):
    '''Handler for detecting requests from subordinate
    charms for restarts of services'''
    restart_nonce = relation_get(attribute='restart-nonce',
                                 unit=unit,
                                 rid=relation_id)
    db = unitdata.kv()
    nonce_key = 'restart-nonce'
    if restart_nonce != db.get(nonce_key):
        if not is_unit_paused_set():
            service = relation_get(attribute='remote-service',
                                   unit=unit,
                                   rid=relation_id) or default_service
            if service:
                service_restart(service)
        db.set(nonce_key, restart_nonce)
        db.flush()


@hooks.hook('lxd-relation-joined')
def lxd_joined(relid=None):
    relation_set(relation_id=relid,
                 user='nova')


@hooks.hook('lxd-relation-changed')
@restart_on_change(restart_map())
def lxc_changed():
    nonce = relation_get('nonce')
    db = kv()
    if nonce and db.get('lxd-nonce') != nonce:
        db.set('lxd-nonce', nonce)
        configure_lxd(user='nova')
        CONFIGS.write(NOVA_CONF)


@hooks.hook('ceph-access-relation-changed')
def ceph_access(rid=None, unit=None):
    '''Setup libvirt secret for specific ceph backend access'''
    def _configure_keyring(service_name, key, uuid):
        if config('virt-type') in LIBVIRT_TYPES:
            secrets_filename = CEPH_BACKEND_SECRET.format(service_name)
            render(os.path.basename(CEPH_SECRET), secrets_filename,
                   context={'ceph_secret_uuid': uuid,
                            'service_name': service_name})
            create_libvirt_secret(secret_file=secrets_filename,
                                  secret_uuid=uuid,
                                  key=key)
        # NOTE(jamespage): LXD ceph integration via host rbd mapping, so
        #                  install keyring for rbd commands to use
        ensure_ceph_keyring(service=service_name,
                            user='nova', group='nova',
                            key=key)

    ceph_keyrings = relation_get('keyrings')
    if ceph_keyrings:
        for keyring in json.loads(ceph_keyrings):
            _configure_keyring(
                keyring['name'], keyring['key'], keyring['secret-uuid'])
    else:
        # NOTE: keep backwards compatibility with previous relation data
        key = relation_get('key', unit, rid)
        uuid = relation_get('secret-uuid', unit, rid)
        if key and uuid:
            _configure_keyring(remote_service_name(rid), key, uuid)


@hooks.hook('secrets-storage-relation-joined')
def secrets_storage_joined(relation_id=None):
    relation_set(relation_id=relation_id,
                 secret_backend=vaultlocker.VAULTLOCKER_BACKEND,
                 isolated=True,
                 access_address=get_relation_ip('secrets-storage'),
                 hostname=gethostname())


@hooks.hook('secrets-storage-relation-changed')
def secrets_storage_changed():
    vault_ca = relation_get('vault_ca')
    if vault_ca:
        vault_ca = base64.decodebytes(json.loads(vault_ca).encode())
        write_file('/usr/local/share/ca-certificates/vault-ca.crt',
                   vault_ca, perms=0o644)
        subprocess.check_call(['update-ca-certificates', '--fresh'])
    configure_local_ephemeral_storage()


@hooks.hook('storage.real')
def storage_changed():
    configure_local_ephemeral_storage()


@hooks.hook('cloud-credentials-relation-joined')
def cloud_credentials_joined():
    svc_name = local_unit().split('/')[0].replace('-', '_')
    relation_set(username=svc_name)


@hooks.hook('cloud-credentials-relation-changed')
@restart_on_change(restart_map())
def cloud_credentials_changed():
    CONFIGS.write(NOVA_CONF)


def check_and_start_iscsid():
    if not service_running('iscsid'):
        service_start('iscsid')


@hooks.hook('update-status')
@harden()
def update_status():
    log('Updating status.')


@hooks.hook('pre-series-upgrade')
def pre_series_upgrade():
    log("Running prepare series upgrade hook", "INFO")
    series_upgrade_prepare(
        pause_unit_helper, CONFIGS)


@hooks.hook('post-series-upgrade')
def post_series_upgrade():
    log("Running complete series upgrade hook", "INFO")
    service_stop('nova-compute')
    service_stop(libvirt_daemon())
    # After package upgrade the service is broken and leaves behind a
    # PID file which causes the service to fail to start.
    # Remove this before restart
    if os.path.exists(LIBVIRTD_PID):
        os.unlink(LIBVIRTD_PID)
    series_upgrade_complete(
        resume_unit_helper, CONFIGS)


@hooks.hook('shared-db-relation-joined')
def shared_db_relation_joined():
    release = os_release('nova-common')
    if CompareOpenStackReleases(release) >= 'ussuri':
        log("shared-db is only required for nova-network which is NOT "
            "available in Ussuri and later.  Please remove the relation.",
            "WARNING")


def main():
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        log('Unknown hook {} - skipping.'.format(e))
    assess_status(CONFIGS)


if __name__ == '__main__':
    main()
