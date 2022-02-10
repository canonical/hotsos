#!/usr/bin/env python3
#
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

import copy
import glob
import os
import shutil
import sys
import traceback

_path = os.path.dirname(os.path.realpath(__file__))
_root = os.path.abspath(os.path.join(_path, '..'))


def _add_path(path):
    if path not in sys.path:
        sys.path.insert(1, path)


_add_path(_root)


import pcmk

from charmhelpers.core.hookenv import (
    is_leader,
    log,
    DEBUG,
    INFO,
    ERROR,
    related_units,
    relation_ids,
    relation_set,
    relation_type,
    remote_unit,
    config,
    Hooks,
    UnregisteredHookError,
    status_set,
)

from charmhelpers.core.host import (
    service_stop,
    service_running,
    lsb_release,
    CompareHostReleases,
    get_distrib_codename,
)

from charmhelpers.contrib.network.ip import (
    get_relation_ip,
)

from charmhelpers.contrib.openstack.utils import (
    is_unit_paused_set,
    set_unit_upgrading,
    clear_unit_upgrading,
    clear_unit_paused,
)

from charmhelpers.fetch import (
    apt_install,
    apt_purge,
    filter_installed_packages,
    apt_mark,
)

from utils import (
    get_corosync_conf,
    assert_charm_supports_ipv6,
    get_cluster_nodes,
    get_member_ready_nodes,
    get_pcmkr_key,
    parse_data,
    configure_corosync,
    configure_stonith,
    configure_monitor_host,
    configure_cluster_global,
    configure_pacemaker_remote_resources,
    configure_pacemaker_remote_stonith_resource,
    configure_peer_stonith_resource,
    configure_resources_on_remotes,
    enable_lsb_services,
    disable_lsb_services,
    disable_upstart_services,
    get_ip_addr_from_resource_params,
    validate_dns_ha,
    setup_maas_api,
    setup_ocf_files,
    set_unit_status,
    set_cluster_symmetry,
    ocf_file_exists,
    kill_legacy_ocf_daemon_process,
    try_pcmk_wait,
    maintenance_mode,
    needs_maas_dns_migration,
    write_maas_dns_address,
    MAASConfigIncomplete,
    pause_unit,
    resume_unit,
    set_waiting_unit_series_upgrade,
    clear_waiting_unit_series_upgrade,
    is_waiting_unit_series_upgrade_set,
    get_series_upgrade_notifications,
    disable_ha_services,
    enable_ha_services,
    notify_peers_of_series_upgrade,
    clear_series_upgrade_notification,
    get_hostname,
    disable_stonith,
    is_stonith_configured,
    emit_systemd_overrides_file,
    trigger_corosync_update_from_leader,
    emit_corosync_conf,
    assess_status_helper,
)

from charmhelpers.contrib.charmsupport import nrpe

hooks = Hooks()

COROSYNC_CONF = '/etc/corosync/corosync.conf'
COROSYNC_DEFAULT = '/etc/default/corosync'
COROSYNC_AUTHKEY = '/etc/corosync/authkey'

COROSYNC_CONF_FILES = [
    COROSYNC_DEFAULT,
    COROSYNC_AUTHKEY,
    COROSYNC_CONF
]

PACKAGES = ['crmsh', 'corosync', 'pacemaker', 'python3-netaddr', 'ipmitool',
            'libmonitoring-plugin-perl', 'python3-requests-oauthlib']

SUPPORTED_TRANSPORTS = ['udp', 'udpu', 'multicast', 'unicast']
DEPRECATED_TRANSPORT_VALUES = {"multicast": "udp", "unicast": "udpu"}


@hooks.hook('install.real')
def install():
    pkgs = copy.deepcopy(PACKAGES)
    ubuntu_release = lsb_release()['DISTRIB_CODENAME'].lower()
    if CompareHostReleases(ubuntu_release) < 'xenial':
        # use libnagios on anything older than Xenial
        pkgs.remove('libmonitoring-plugin-perl')
        pkgs.append('libnagios-plugin-perl')

        pkgs.remove('python3-netaddr')
        pkgs.append('python-netaddr')

    elif CompareHostReleases(ubuntu_release) >= 'bionic':
        pkgs.append('python3-libmaas')

    # NOTE(dosaboy): we currently disallow upgrades due to bug #1382842. This
    # should be removed once the pacemaker package is fixed.
    status_set('maintenance', 'Installing apt packages')
    apt_install(filter_installed_packages(pkgs), fatal=True)
    setup_ocf_files()


def get_transport():
    transport = config('corosync_transport')
    val = DEPRECATED_TRANSPORT_VALUES.get(transport, transport)
    if val not in ['udp', 'udpu']:
        msg = ("Unsupported corosync_transport type '%s' - supported "
               "types are: %s" % (transport, ', '.join(SUPPORTED_TRANSPORTS)))
        status_set('blocked', msg)
        raise ValueError(msg)
    return val


def run_initial_setup():
    """Run global setup."""
    failure_timeout = config('failure_timeout')
    cluster_recheck_interval = config('cluster_recheck_interval')
    configure_cluster_global(failure_timeout, cluster_recheck_interval)
    configure_monitor_host()
    if not is_stonith_configured():
        disable_stonith()


@hooks.hook('config-changed')
def config_changed():

    # if we are paused, delay doing any config changed hooks.
    # It is forced on the resume.
    if is_unit_paused_set():
        log("Unit is pause or upgrading. Skipping config_changed", "WARN")
        return

    setup_ocf_files()

    if config('prefer-ipv6'):
        assert_charm_supports_ipv6()

    corosync_key = config('corosync_key')
    if not corosync_key:
        message = 'No Corosync key supplied, cannot proceed'
        status_set('blocked', message)
        raise Exception(message)

    enable_lsb_services('pacemaker')

    for rid in relation_ids('hanode'):
        hanode_relation_joined(rid)

    status_set('maintenance', "Setting up corosync")
    if configure_corosync():
        try_pcmk_wait()
        if is_leader():
            run_initial_setup()

    update_nrpe_config()

    cfg = config()
    if (is_leader() and
            cfg.previous('maintenance-mode') != cfg['maintenance-mode']):
        maintenance_mode(cfg['maintenance-mode'])

    if config('no_quorum_policy').lower() in ['ignore', 'freeze',
                                              'stop', 'suicide']:
        pcmk.set_property("no-quorum-policy",
                          config('no_quorum_policy').lower())
    else:
        message = 'Invalid setting for no_quorum_policy'
        status_set('blocked', message)
    status_set(*assess_status_helper())


def migrate_maas_dns():
    """
    Migrates the MAAS DNS HA configuration to write local IP address
    information to files.
    """
    if not needs_maas_dns_migration():
        log("MAAS DNS migration is not necessary.", INFO)
        return

    for relid in relation_ids('ha'):
        for unit in related_units(relid):
            resources = parse_data(relid, unit, 'resources')
            resource_params = parse_data(relid, unit, 'resource_params')

            if True in [ra.startswith('ocf:maas')
                        for ra in resources.values()]:
                for resource in resource_params.keys():
                    if resource.endswith("_hostname"):
                        res_ipaddr = get_ip_addr_from_resource_params(
                            resource_params[resource])
                        log("Migrating MAAS DNS resource %s" % resource, INFO)
                        write_maas_dns_address(resource, res_ipaddr)


@hooks.hook('upgrade-charm.real')
def upgrade_charm():
    install()
    migrate_maas_dns()
    emit_systemd_overrides_file()
    update_nrpe_config()


@hooks.hook('hanode-relation-joined')
def hanode_relation_joined(relid=None):
    relation_set(
        relation_id=relid,
        relation_settings={
            'private-address': get_relation_ip('hanode'),
            'hostname': get_hostname()}
    )


@hooks.hook('hanode-relation-changed')
def hanode_relation_changed(relid=None):
    ubuntu_rel = lsb_release()['DISTRIB_CODENAME'].lower()
    log("Checking if any units have notified about a series upgrade", INFO)
    series_notifications = get_series_upgrade_notifications(relid)
    for unit, from_release in series_notifications.items():
        # from_release is the release that the peer is currently on and is
        # therefore upgrading from.
        if CompareHostReleases(ubuntu_rel) <= from_release:
            log("Shutting down services for peer upgrade", INFO)
            disable_ha_services()
            log("Setting waiting-unit-upgrade to True", INFO)
            set_waiting_unit_series_upgrade()
        else:
            log(
                "Already series ahead of peer, no shutdown needed",
                INFO)
    if is_waiting_unit_series_upgrade_set():
        log("Unit is waiting for upgrade", INFO)
    else:
        log("No units have notified a series upgrade", INFO)
        ha_relation_changed()


@hooks.hook('hanode-relation-departed')
def hanode_relation_departed(relid=None):
    if config('maintenance-mode'):
        log('pcmk is in maintenance mode - skip any action', DEBUG)
        return

    # Note(aluria): all units will update corosync.conf list of nodes
    # in the aim of having up to date stored configurations. However,
    # corosync reloads (or restarts) won't be triggered at this point
    # (update-ring action will do)
    if emit_corosync_conf():
        log('corosync.conf updated')
    else:
        log('corosync.conf not updated')


@hooks.hook('ha-relation-joined',
            'ha-relation-changed',
            'peer-availability-relation-joined',
            'peer-availability-relation-changed',
            'pacemaker-remote-relation-changed')
def ha_relation_changed():
    # Check that we are related to a principle and that
    # it has already provided the required corosync configuration
    if not get_corosync_conf():
        log('Unable to configure corosync right now, deferring configuration',
            level=INFO)
        return

    relids_hanode = relation_ids('hanode')
    if relids_hanode:
        log('Ready to form cluster - informing peers', level=DEBUG)
        relation_set(relation_id=relids_hanode[0], ready=True)

        # If a trigger-corosync-update attribute exists in the relation,
        # the Juju leader may have requested all its peers to update
        # the corosync.conf list of nodes. If it's the case, no other
        # action will be run (a future hook re: ready=True may trigger
        # other logic)
        # NOTE(lourot): it's not necessary to test for
        # `remote_unit() != principal_unit()` here as this is only False (both
        # units are the same) when the relation type is `ha`.
        if (relation_type() == 'hanode' and
            trigger_corosync_update_from_leader(remote_unit(),
                                                relids_hanode[0])):
            return

    else:
        log('Ready to form cluster, but not related to peers just yet',
            level=INFO)
        return

    # Check that there's enough nodes in order to perform the
    # configuration of the HA cluster
    if len(get_cluster_nodes()) < int(config('cluster_count')):
        log('Not enough nodes in cluster, deferring configuration',
            level=INFO)
        return

    relids = relation_ids('ha') or relation_ids('juju-info')
    if len(relids) == 1:  # Should only ever be one of these
        # Obtain relation information
        relid = relids[0]
        units = related_units(relid)
        if len(units) < 1:
            log('No principle unit found, deferring configuration',
                level=INFO)
            return

        unit = units[0]
        log('Parsing cluster configuration using rid: %s, unit: %s' %
            (relid, unit), level=DEBUG)
        resources = parse_data(relid, unit, 'resources')
        delete_resources = parse_data(relid, unit, 'delete_resources')
        resource_params = parse_data(relid, unit, 'resource_params')
        groups = parse_data(relid, unit, 'groups')
        ms = parse_data(relid, unit, 'ms')
        orders = parse_data(relid, unit, 'orders')
        colocations = parse_data(relid, unit, 'colocations')
        clones = parse_data(relid, unit, 'clones')
        locations = parse_data(relid, unit, 'locations')
        init_services = parse_data(relid, unit, 'init_services')
    else:
        log('Related to %s ha services' % (len(relids)), level=DEBUG)
        return

    if True in [ra.startswith('ocf:openstack')
                for ra in resources.values()]:
        apt_install('openstack-resource-agents')
    if True in [ra.startswith('ocf:ceph')
                for ra in resources.values()]:
        apt_install('ceph-resource-agents')

    if True in [ra.startswith('ocf:maas')
                for ra in resources.values()]:
        try:
            validate_dns_ha()
        except MAASConfigIncomplete as ex:
            log(ex.args[0], level=ERROR)
            status_set('blocked', ex.args[0])
            # if an exception is raised the hook will end up in error state
            # which will obfuscate the workload status and message.
            return

        log('Setting up access to MAAS API', level=INFO)
        setup_maas_api()
        # Update resource_parms for DNS resources to include MAAS URL and
        # credentials
        for resource in resource_params.keys():
            if resource.endswith("_hostname"):
                res_ipaddr = get_ip_addr_from_resource_params(
                    resource_params[resource])
                resource_params[resource] += (
                    ' maas_url="{}" maas_credentials="{}"'
                    ''.format(config('maas_url'),
                              config('maas_credentials')))
                write_maas_dns_address(resource, res_ipaddr)

    # NOTE: this should be removed in 15.04 cycle as corosync
    # configuration should be set directly on subordinate
    configure_corosync()
    try_pcmk_wait()

    # Only configure the cluster resources
    # from the oldest peer unit.
    if is_leader():
        run_initial_setup()
        log('Setting cluster symmetry', level=INFO)
        set_cluster_symmetry()
        log('Deleting Resources' % (delete_resources), level=DEBUG)
        for res_name in delete_resources:
            if pcmk.crm_opt_exists(res_name):
                if ocf_file_exists(res_name, resources):
                    log('Stopping and deleting resource %s' % res_name,
                        level=DEBUG)
                    if pcmk.crm_res_running(res_name):
                        pcmk.commit('crm -w -F resource stop %s' % res_name)
                else:
                    log('Cleanuping and deleting resource %s' % res_name,
                        level=DEBUG)
                    pcmk.commit('crm resource cleanup %s' % res_name)
                # Daemon process may still be running after the upgrade.
                kill_legacy_ocf_daemon_process(res_name)

                # Stop the resource before the deletion (LP: #1838528)
                log('Stopping %s' % res_name, level=INFO)
                pcmk.commit('crm -w -F resource stop %s' % res_name)
                log('Deleting %s' % res_name, level=INFO)
                pcmk.commit('crm -w -F configure delete %s' % res_name)

        log('Configuring Resources: %s' % (resources), level=DEBUG)
        for res_name, res_type in resources.items():
            # disable the service we are going to put in HA
            if res_type.split(':')[0] == "lsb":
                disable_lsb_services(res_type.split(':')[1])
                if service_running(res_type.split(':')[1]):
                    service_stop(res_type.split(':')[1])
            elif (len(init_services) != 0 and
                  res_name in init_services and
                  init_services[res_name]):
                disable_upstart_services(init_services[res_name])
                if service_running(init_services[res_name]):
                    service_stop(init_services[res_name])
            # Put the services in HA, if not already done so
            # if not pcmk.is_resource_present(res_name):
            if not pcmk.crm_opt_exists(res_name):
                if res_name not in resource_params:
                    cmd = 'crm -w -F configure primitive %s %s' % (res_name,
                                                                   res_type)
                else:
                    cmd = ('crm -w -F configure primitive %s %s %s' %
                           (res_name, res_type, resource_params[res_name]))

                pcmk.commit(cmd)
                log('%s' % cmd, level=DEBUG)
                if config('monitor_host'):
                    cmd = ('crm -F configure location Ping-%s %s rule '
                           '-inf: pingd lte 0' % (res_name, res_name))
                    pcmk.commit(cmd)

            else:
                # the resource already exists so it will be updated.
                code = pcmk.crm_update_resource(res_name, res_type,
                                                resource_params.get(res_name))
                if code != 0:
                    msg = "Cannot update pcmkr resource: {}".format(res_name)
                    status_set('blocked', msg)
                    raise Exception(msg)

        log('Configuring Groups: %s' % (groups), level=DEBUG)
        for grp_name, grp_params in groups.items():
            if not pcmk.crm_opt_exists(grp_name):
                cmd = ('crm -w -F configure group %s %s' %
                       (grp_name, grp_params))
                pcmk.commit(cmd)
                log('%s' % cmd, level=DEBUG)

        log('Configuring Master/Slave (ms): %s' % (ms), level=DEBUG)
        for ms_name, ms_params in ms.items():
            if not pcmk.crm_opt_exists(ms_name):
                cmd = 'crm -w -F configure ms %s %s' % (ms_name, ms_params)
                pcmk.commit(cmd)
                log('%s' % cmd, level=DEBUG)

        log('Configuring Orders: %s' % (orders), level=DEBUG)
        for ord_name, ord_params in orders.items():
            if not pcmk.crm_opt_exists(ord_name):
                cmd = 'crm -w -F configure order %s %s' % (ord_name,
                                                           ord_params)
                pcmk.commit(cmd)
                log('%s' % cmd, level=DEBUG)

        log('Configuring Clones: %s' % clones, level=DEBUG)
        for cln_name, cln_params in clones.items():
            if not pcmk.crm_opt_exists(cln_name):
                cmd = 'crm -w -F configure clone %s %s' % (cln_name,
                                                           cln_params)
                pcmk.commit(cmd)
                log('%s' % cmd, level=DEBUG)

        # Ordering is important here, colocation and location constraints
        # reference resources. All resources referenced by the constraints
        # need to exist otherwise constraint creation will fail.

        log('Configuring Colocations: %s' % colocations, level=DEBUG)
        for col_name, col_params in colocations.items():
            if not pcmk.crm_opt_exists(col_name):
                cmd = 'crm -w -F configure colocation %s %s' % (col_name,
                                                                col_params)
                pcmk.commit(cmd)
                log('%s' % cmd, level=DEBUG)

        log('Configuring Locations: %s' % locations, level=DEBUG)
        for loc_name, loc_params in locations.items():
            if not pcmk.crm_opt_exists(loc_name):
                cmd = 'crm -w -F configure location %s %s' % (loc_name,
                                                              loc_params)
                pcmk.commit(cmd)
                log('%s' % cmd, level=DEBUG)

        for res_name, res_type in resources.items():
            if len(init_services) != 0 and res_name in init_services:
                # Checks that the resources are running and started.
                # Ensure that clones are excluded as the resource is
                # not directly controllable (dealt with below)
                # Ensure that groups are cleaned up as a whole rather
                # than as individual resources.
                if (res_name not in clones.values() and
                    res_name not in groups.values() and
                        not pcmk.crm_res_running(res_name)):
                    # Just in case, cleanup the resources to ensure they get
                    # started in case they failed for some unrelated reason.
                    cmd = 'crm resource cleanup %s' % res_name
                    pcmk.commit(cmd)

        for cl_name in clones:
            # Always cleanup clones
            cmd = 'crm resource cleanup %s' % cl_name
            pcmk.commit(cmd)

        for grp_name in groups:
            # Always cleanup groups
            cmd = 'crm resource cleanup %s' % grp_name
            pcmk.commit(cmd)

        # All members of the cluster need to be registered before resources
        # that reference them can be created.
        if len(get_member_ready_nodes()) >= int(config('cluster_count')):
            log('Configuring any remote nodes', level=INFO)
            remote_resources = configure_pacemaker_remote_resources()
            resources.update(remote_resources)
            configure_resources_on_remotes(
                resources=resources,
                clones=clones,
                groups=groups)

            stonith_resources = {}
            stonith_remote_res = configure_pacemaker_remote_stonith_resource()
            stonith_resources.update(stonith_remote_res)
            if stonith_remote_res:
                stonith_peer_res = configure_peer_stonith_resource()
                stonith_resources.update(stonith_peer_res)
            configure_resources_on_remotes(
                resources=stonith_resources,
                clones=clones,
                groups=groups)
            configure_stonith()
        else:
            log('Deferring configuration of any remote nodes', level=INFO)

    for rel_id in relation_ids('ha'):
        relation_set(relation_id=rel_id, clustered="yes")

    # Inform peers that local configuration is complete and this member
    # is ready
    for rel_id in relids_hanode:
        relation_set(relation_id=rel_id, member_ready=True)


@hooks.hook()
def stop():
    # The pcmk.delete_node handles several known failure modes so
    # failure_is_fatal=True actually helps as it causes retries.
    node = get_hostname()
    pcmk.set_node_status_to_maintenance(node)
    pcmk.delete_node(node, failure_is_fatal=True)

    apt_purge(['corosync', 'pacemaker'], fatal=True)


@hooks.hook('nrpe-external-master-relation-joined',
            'nrpe-external-master-relation-changed')
def update_nrpe_config():
    # Validate options (DEPRECATED)
    valid_alerts = ['ignore', 'warning', 'critical']
    if config('failed_actions_alert_type').lower() not in valid_alerts:
        status_set('blocked',
                   'The value of option failed_actions_alert_type must be '
                   'among {}'.format(valid_alerts))
        return
    if config('failed_actions_threshold') < 0:
        status_set('blocked',
                   'The value of option failed_actions_threshold must be a '
                   'positive integer')
        return

    scripts_src = os.path.join(os.environ["CHARM_DIR"], "files",
                               "nrpe")

    scripts_dst = "/usr/local/lib/nagios/plugins"
    if not os.path.exists(scripts_dst):
        os.makedirs(scripts_dst)
    for fname in glob.glob(os.path.join(scripts_src, "*")):
        if os.path.isfile(fname):
            shutil.copy2(fname,
                         os.path.join(scripts_dst, os.path.basename(fname)))

    sudoers_src = os.path.join(os.environ["CHARM_DIR"], "files",
                               "sudoers")
    sudoers_dst = "/etc/sudoers.d"
    for fname in glob.glob(os.path.join(sudoers_src, "*")):
        if os.path.isfile(fname):
            shutil.copy2(fname,
                         os.path.join(sudoers_dst, os.path.basename(fname)))

    hostname = nrpe.get_nagios_hostname()
    current_unit = nrpe.get_nagios_unit_name()

    nrpe_setup = nrpe.NRPE(hostname=hostname)

    apt_install('python-dbus')

    check_crm_cmd = 'check_crm -s'
    check_crm_cmd += ' --failedactions={}'.format(
        config('failed_actions_alert_type').lower()
    )
    if config('failed_actions_threshold'):
        check_crm_cmd += ' --failcount={}'.format(
            config('failed_actions_threshold')
        )
    for err_type in ['warn', 'crit']:
        check_crm_cmd += ' --failcount-{}={}'.format(
            err_type,
            config('res_failcount_{}'.format(err_type)) or 0)

    if nrpe.NRPE.does_nrpe_conf_dir_exist():
        # corosync/crm checks

        # LP #1902919 - corosync version 2.99 changed the ring status output
        # for udp/udpu to hardcode the status to always report 'OK'. This
        # results in the check providing no value over what is provided by the
        # crm_status check. A version check on the package would be more ideal,
        # however populating the apt-cache object is expensive to run on each
        # config-changed hook, so use the faster check of comparing the
        # release name.
        ring_check = {
            'shortname': 'corosync_rings',
            'description': 'Check Corosync rings {}'.format(current_unit),
            'check_cmd': 'check_corosync_rings',
        }
        if CompareHostReleases(get_distrib_codename()) < 'eoan':
            nrpe_setup.add_check(**ring_check)
        else:
            nrpe_setup.remove_check(**ring_check)

        nrpe_setup.add_check(
            shortname='crm_status',
            description='Check crm status {}'.format(current_unit),
            check_cmd=check_crm_cmd)

        # process checks
        nrpe_setup.add_check(
            shortname='corosync_proc',
            description='Check Corosync process {}'.format(current_unit),
            check_cmd='check_procs -c 1:1 -C corosync'
        )
        nrpe_setup.add_check(
            shortname='pacemakerd_proc',
            description='Check Pacemakerd process {}'.format(current_unit),
            check_cmd='check_procs -c 1:1 -C pacemakerd'
        )

        nrpe_setup.write()


@hooks.hook('pre-series-upgrade')
def series_upgrade_prepare():
    set_unit_upgrading()
    # HA services are shutdown when the unit receives series upgrade
    # notifications from peers so cannot pause services.
    if not is_unit_paused_set() and not is_waiting_unit_series_upgrade_set():
        pause_unit()
    notify_peers_of_series_upgrade()
    # mark crmsh package as manually installed
    # so it does not get uninstalled on release upgrade
    # from xenial to bionic
    apt_mark('crmsh', 'manual')


@hooks.hook('post-series-upgrade')
def series_upgrade_complete():
    log("Running complete series upgrade hook", "INFO")
    clear_unit_paused()
    clear_unit_upgrading()
    config_changed()
    enable_ha_services()
    log("Resuming unit")
    resume_unit()
    clear_series_upgrade_notification()
    log("Setting waiting-unit-upgrade to False", INFO)
    clear_waiting_unit_series_upgrade()


@hooks.hook('pacemaker-remote-relation-joined')
def send_auth_key():
    key = get_pcmkr_key()
    if key:
        for rel_id in relation_ids('pacemaker-remote'):
            relation_set(
                relation_id=rel_id,
                **{'pacemaker-key': key})


@hooks.hook('update-status')
def dummy_update_status():
    """Provide implementation to silence missing hook handler error

    See bug/1837639
    """
    pass


if __name__ == '__main__':
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        log('Unknown hook {} - skipping.'.format(e), level=DEBUG)
    try:
        set_unit_status()
    except Exception:
        log(traceback.format_exc(), level=ERROR)
        raise
