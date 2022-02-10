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

import sys
import uuid

from copy import deepcopy

from charmhelpers.contrib.openstack import context as os_context

from charmhelpers.contrib.openstack.utils import (
    os_restart_on_change as restart_on_change,
    series_upgrade_prepare,
    series_upgrade_complete,
    is_hook_allowed,
    CompareOpenStackReleases,
    os_release,
)

from charmhelpers.contrib.openstack.deferred_events import (
    configure_deferred_restarts,
)

from charmhelpers.core.hookenv import (
    Hooks,
    UnregisteredHookError,
    config,
    log,
    relation_set,
    relation_ids,
)

from charmhelpers.core.sysctl import create as create_sysctl

from charmhelpers.core.host import (
    is_container,
)

from charmhelpers.core.unitdata import kv

from neutron_ovs_utils import (
    DHCP_PACKAGES,
    DVR_PACKAGES,
    L3HA_PACKAGES,
    METADATA_PACKAGES,
    OVS_DEFAULT,
    USE_FQDN_KEY,
    configure_ovs,
    get_shared_secret,
    register_configs,
    restart_map,
    use_dvr,
    use_l3ha,
    enable_nova_metadata,
    enable_local_dhcp,
    install_packages,
    install_l3ha_packages,
    purge_packages,
    assess_status,
    install_tmpfilesd,
    pause_unit_helper,
    resume_unit_helper,
    determine_purge_packages,
    purge_sriov_systemd_files,
    use_fqdn_hint,
    deferrable_services,
)

hooks = Hooks()
CONFIGS = register_configs()


@hooks.hook('install.real')
def install():
    install_packages()

    # Start migration to agent registration with FQDNs for newly installed
    # units with OpenStack release Stein or newer.
    release = os_release('neutron-common')
    if CompareOpenStackReleases(release) >= 'stein':
        db = kv()
        db.set(USE_FQDN_KEY, True)
        db.flush()


# NOTE(wolsen): Do NOT add restart_on_change decorator without consideration
# for the implications of modifications to the /etc/default/openvswitch-switch.
@hooks.hook('upgrade-charm')
def upgrade_charm():
    # Tidy up any prior installation of obsolete sriov startup
    # scripts
    purge_sriov_systemd_files()

    if OVS_DEFAULT in restart_map():
        # In the 16.10 release of the charms, the code changed from managing
        # the /etc/default/openvswitch-switch file only when dpdk was enabled
        # to always managing this file. Thus, an upgrade of the charm from a
        # release prior to 16.10 or higher will always cause the contents of
        # the file to change and will trigger a restart of the
        # openvswitch-switch service, which in turn causes a temporary
        # network outage. To prevent this outage, determine if the
        # /etc/default/openvswitch-switch file needs to be migrated and if
        # so, migrate the file but do NOT restart the openvswitch-switch
        # service.
        # See bug LP #1712444
        with open(OVS_DEFAULT, 'r') as f:
            # The 'Service restart triggered ...' line was added to the
            # OVS_DEFAULT template in the 16.10 version of the charm to allow
            # restarts so we use this as the key to see if the file needs
            # migrating.
            if 'Service restart triggered' not in f.read():
                CONFIGS.write(OVS_DEFAULT)


@hooks.hook('neutron-plugin-relation-changed')
@hooks.hook('config-changed')
# NOTE(fnordahl): we need to act immediately to changes to OVS_DEFAULT in-line
# so ignore it here to avoid restarting the services twice. LP: #1906280
@restart_on_change({cfg: services
                    for cfg, services in restart_map().items()
                    if cfg != OVS_DEFAULT})
def config_changed(check_deferred_restarts=True):
    configure_deferred_restarts(deferrable_services())
    # policy_rcd.remove_policy_file()
    # if we are paused, delay doing any config changed hooks.
    # It is forced on the resume.
    allowed, reason = is_hook_allowed(
        'config-changed',
        check_deferred_restarts=check_deferred_restarts)
    if not allowed:
        log(reason, "WARN")
        return

    install_packages()
    install_tmpfilesd()

    # NOTE(jamespage): purge any packages as a result of py3 switch
    #                  at rocky.
    packages_to_purge = determine_purge_packages()
    request_nova_compute_restart = False
    if packages_to_purge:
        purge_packages(packages_to_purge)
        request_nova_compute_restart = True

    sysctl_settings = config('sysctl')
    if not is_container() and sysctl_settings:
        create_sysctl(sysctl_settings,
                      '/etc/sysctl.d/50-openvswitch.conf')

    # NOTE(fnordahl): It is important to write config to disk and perhaps
    # restart the openvswitch-swith service prior to attempting to do run-time
    # configuration of OVS as we may have to pass options to `ovs-ctl` for
    # `ovs-vswitchd` to run at all. LP: #1906280
    # TODO: make restart_on_change use contextlib.contextmanager
    @restart_on_change({cfg: services
                        for cfg, services in restart_map().items()
                        if cfg == OVS_DEFAULT})
    def _restart_before_runtime_config_when_required():
        CONFIGS.write_all()
    _restart_before_runtime_config_when_required()
    configure_ovs()

    for rid in relation_ids('neutron-plugin'):
        neutron_plugin_joined(
            relation_id=rid,
            request_restart=request_nova_compute_restart)


@hooks.hook('neutron-plugin-api-relation-changed')
# NOTE(fnordahl): we need to act immediately to changes to OVS_DEFAULT in-line
# so ignore it here to avoid restarting the services twice. LP: #1906280
@restart_on_change({cfg: services
                    for cfg, services in restart_map().items()
                    if cfg != OVS_DEFAULT})
def neutron_plugin_api_changed():
    packages_to_purge = []
    if use_dvr():
        install_packages()
        # per 17.08 release notes L3HA + DVR is a Newton+ feature
        _os_release = os_release('neutron-common', base='icehouse')
        if (use_l3ha() and
                CompareOpenStackReleases(_os_release) >= 'newton'):
            install_l3ha_packages()

        # NOTE(hopem): don't uninstall keepalived if not using l3ha since that
        # results in neutron-l3-agent also being uninstalled (see LP 1819499).
    else:
        packages_to_purge = deepcopy(DVR_PACKAGES)
        packages_to_purge.extend(L3HA_PACKAGES)

    if packages_to_purge:
        purge_packages(packages_to_purge)

    # NOTE(fnordahl): It is important to write config to disk and perhaps
    # restart the openvswitch-swith service prior to attempting to do run-time
    # configuration of OVS as we may have to pass options to `ovs-ctl` for
    # `ovs-vswitchd` to run at all. LP: #1906280
    # TODO: make restart_on_change use contextlib.contextmanager
    @restart_on_change({cfg: service
                        for cfg, service in restart_map().items()
                        if cfg == OVS_DEFAULT})
    def _restart_before_runtime_config_when_required():
        CONFIGS.write_all()
    _restart_before_runtime_config_when_required()
    configure_ovs()
    # If dvr setting has changed, need to pass that on
    for rid in relation_ids('neutron-plugin'):
        neutron_plugin_joined(relation_id=rid)


@hooks.hook('neutron-plugin-relation-joined')
def neutron_plugin_joined(relation_id=None, request_restart=False):
    secret = None
    if not is_container():
        if enable_local_dhcp():
            install_packages()
        else:
            pkgs = deepcopy(DHCP_PACKAGES)
            # NOTE: only purge metadata packages if dvr is not
            #       in use as this will remove the l3 agent
            #       see https://pad.lv/1515008
            if not use_dvr():
                # NOTE(fnordahl) do not remove ``haproxy``, the principal
                # charm may have use for it. LP: #1832739
                pkgs.extend(set(METADATA_PACKAGES)-set(['haproxy']))
            purge_packages(pkgs)
        secret = get_shared_secret() if enable_nova_metadata() else None
    rel_data = {
        'metadata-shared-secret': secret,
    }
    host_info = os_context.HostInfoContext()()
    if use_fqdn_hint() and host_info.get('host_fqdn'):
        rel_data.update({'host': host_info['host_fqdn']})
    if request_restart:
        rel_data['restart-nonce'] = str(uuid.uuid4())
    relation_set(relation_id=relation_id, **rel_data)


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
    CONFIGS.write_all()


@hooks.hook('neutron-control-relation-changed')
@restart_on_change(restart_map(),
                   stopstart=True)
def restart_check():
    CONFIGS.write_all()


@hooks.hook('pre-series-upgrade')
def pre_series_upgrade():
    log("Running prepare series upgrade hook", "INFO")
    series_upgrade_prepare(
        pause_unit_helper, CONFIGS)


@hooks.hook('post-series-upgrade')
def post_series_upgrade():
    log("Running complete series upgrade hook", "INFO")
    series_upgrade_complete(
        resume_unit_helper, CONFIGS)


@hooks.hook('update-status')
def dummy_update_status():
    """Dummy function to silence missing hook log entry"""
    pass


def main():
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        log('Unknown hook {} - skipping.'.format(e))
    assess_status(CONFIGS)


if __name__ == '__main__':
    main()
