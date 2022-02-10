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
import glob
import json
import netifaces
import os
import shutil
import socket
import subprocess
import sys
import traceback

sys.path.append('lib')
import charms_ceph.utils as ceph
from charmhelpers.core import hookenv
from charmhelpers.core.hookenv import (
    log,
    DEBUG,
    ERROR,
    INFO,
    WARNING,
    config,
    relation_ids,
    related_units,
    relation_get,
    relation_set,
    relations_of_type,
    Hooks,
    local_unit,
    UnregisteredHookError,
    service_name,
    status_get,
    status_set,
    storage_get,
    storage_list,
    application_version_set,
)
from charmhelpers.core.host import (
    add_to_updatedb_prunepath,
    cmp_pkgrevno,
    is_container,
    lsb_release,
    mkdir,
    service_reload,
    service_restart,
    umount,
    write_file,
    CompareHostReleases,
    file_hash,
)
from charmhelpers.fetch import (
    add_source,
    apt_install,
    apt_update,
    filter_installed_packages,
    get_upstream_version,
)
from charmhelpers.core.sysctl import create as create_sysctl
import charmhelpers.contrib.openstack.context as ch_context
from charmhelpers.contrib.openstack.context import (
    AppArmorContext,
)
from utils import (
    is_osd_bootstrap_ready,
    import_osd_bootstrap_key,
    import_osd_upgrade_key,
    get_host_ip,
    get_networks,
    assert_charm_supports_ipv6,
    render_template,
    get_public_addr,
    get_cluster_addr,
    get_blacklist,
    get_journal_devices,
    should_enable_discard,
    _upgrade_keyring,
)
from charmhelpers.contrib.openstack.alternatives import install_alternative
from charmhelpers.contrib.network.ip import (
    get_ipv6_addr,
    format_ipv6_addr,
    get_relation_ip,
)
import charmhelpers.contrib.storage.linux.ceph as ch_ceph
from charmhelpers.contrib.storage.linux.utils import (
    is_device_mounted,
    is_block_device,
)
from charmhelpers.contrib.charmsupport import nrpe
from charmhelpers.contrib.hardening.harden import harden

from charmhelpers.contrib.openstack.utils import (
    clear_unit_paused,
    clear_unit_upgrading,
    get_os_codename_install_source,
    is_unit_paused_set,
    is_unit_upgrading_set,
    set_unit_paused,
    set_unit_upgrading,
)

from charmhelpers.core.unitdata import kv

import charmhelpers.contrib.openstack.vaultlocker as vaultlocker

hooks = Hooks()
STORAGE_MOUNT_PATH = '/var/lib/ceph'

# cron.d related files
CRON_CEPH_CHECK_FILE = '/etc/cron.d/check-osd-services'


def check_for_upgrade():

    if not os.path.exists(_upgrade_keyring):
        log("Ceph upgrade keyring not detected, skipping upgrade checks.")
        return

    c = hookenv.config()
    old_version = ceph.resolve_ceph_version(c.previous('source') or
                                            'distro')
    log('old_version: {}'.format(old_version))
    new_version = ceph.resolve_ceph_version(hookenv.config('source') or
                                            'distro')
    log('new_version: {}'.format(new_version))

    old_version_os = get_os_codename_install_source(c.previous('source') or
                                                    'distro')
    new_version_os = get_os_codename_install_source(hookenv.config('source'))

    # May be in a previous upgrade that was failed if the directories
    # still need an ownership update. Check this condition.
    resuming_upgrade = ceph.dirs_need_ownership_update('osd')

    if (ceph.UPGRADE_PATHS.get(old_version) == new_version) or\
       resuming_upgrade:
        if old_version == new_version:
            log('Attempting to resume possibly failed upgrade.',
                INFO)
        else:
            log("{} to {} is a valid upgrade path. Proceeding.".format(
                old_version, new_version))

        emit_cephconf(upgrading=True)
        ceph.roll_osd_cluster(new_version=new_version,
                              upgrade_key='osd-upgrade')
        emit_cephconf(upgrading=False)
        notify_mon_of_upgrade(new_version)
    elif (old_version == new_version and
          old_version_os < new_version_os):
        # See LP: #1778823
        add_source(hookenv.config('source'), hookenv.config('key'))
        log(("The installation source has changed yet there is no new major "
             "version of Ceph in this new source. As a result no package "
             "upgrade will take effect. Please upgrade manually if you need "
             "to."), level=INFO)
    else:
        # Log a helpful error message
        log("Invalid upgrade path from {} to {}.  "
            "Valid paths are: {}".format(old_version,
                                         new_version,
                                         ceph.pretty_print_upgrade_paths()),
            level=ERROR)


def notify_mon_of_upgrade(release):
    for relation_id in relation_ids('mon'):
        log('Notifying relation {} of upgrade to {}'.format(
            relation_id, release))
        relation_set(relation_id=relation_id,
                     relation_settings=dict(ceph_release=release))


def tune_network_adapters():
    interfaces = netifaces.interfaces()
    for interface in interfaces:
        if interface == "lo":
            # Skip the loopback
            continue
        log("Looking up {} for possible sysctl tuning.".format(interface))
        ceph.tune_nic(interface)


def aa_profile_changed(service_name='ceph-osd-all'):
    """
    Reload AA profile and restart OSD processes.
    """
    log("Loading new AppArmor profile")
    service_reload('apparmor')
    log("Restarting ceph-osd services with new AppArmor profile")
    if ceph.systemd():
        for osd_id in ceph.get_local_osd_ids():
            service_restart('ceph-osd@{}'.format(osd_id))
    else:
        service_restart(service_name)


def copy_profile_into_place():
    """
    Copy the apparmor profiles included with the charm
    into the /etc/apparmor.d directory.

    File are only copied if they have changed at source
    to avoid overwriting any aa-complain mode flags set

    :returns: flag indicating if any profiles where newly
              installed or changed
    :rtype: boolean
    """
    db = kv()
    changes = False
    apparmor_dir = os.path.join(os.sep, 'etc', 'apparmor.d')
    for x in glob.glob('files/apparmor/*'):
        db_key = 'hash:{}'.format(x)
        new_hash = file_hash(x)
        previous_hash = db.get(db_key)
        if new_hash != previous_hash:
            log('Installing apparmor profile for {}'
                .format(os.path.basename(x)))
            shutil.copy(x, apparmor_dir)
            db.set(db_key, new_hash)
            db.flush()
            changes = True
    return changes


class CephOsdAppArmorContext(AppArmorContext):
    """"Apparmor context for ceph-osd binary"""
    def __init__(self):
        super(CephOsdAppArmorContext, self).__init__()
        self.aa_profile = 'usr.bin.ceph-osd'

    def __call__(self):
        super(CephOsdAppArmorContext, self).__call__()
        if not self.ctxt:
            return self.ctxt
        self._ctxt.update({'aa_profile': self.aa_profile})
        return self.ctxt


def use_vaultlocker():
    """Determine whether vaultlocker should be used for OSD encryption

    :returns: whether vaultlocker should be used for key management
    :rtype: bool
    :raises: ValueError if vaultlocker is enable but ceph < 12.2.4"""
    if (config('osd-encrypt') and
            config('osd-encrypt-keymanager') == ceph.VAULT_KEY_MANAGER):
        if cmp_pkgrevno('ceph', '12.2.4') < 0:
            msg = ('vault usage only supported with ceph >= 12.2.4')
            status_set('blocked', msg)
            raise ValueError(msg)
        else:
            return True
    return False


def use_bluestore():
    """Determine whether bluestore should be used for OSD's

    :returns: whether bluestore disk format should be used
    :rtype: bool"""
    if cmp_pkgrevno('ceph', '12.2.0') < 0:
        return False
    return config('bluestore')


def install_apparmor_profile():
    """
    Install ceph apparmor profiles and configure
    based on current setting of 'aa-profile-mode'
    configuration option.
    """
    changes = copy_profile_into_place()
    # NOTE(jamespage): If any profiles where changed or
    #                  freshly installed then force
    #                  re-assertion of the current profile mode
    #                  to avoid complain->enforce side effects
    if changes or config().changed('aa-profile-mode'):
        aa_context = CephOsdAppArmorContext()
        aa_context.setup_aa_profile()
        aa_profile_changed()


def install_udev_rules():
    """
    Install and reload udev rules for ceph-volume LV
    permissions
    """
    if is_container():
        log('Skipping udev rule installation '
            'as unit is in a container', level=DEBUG)
        return
    for x in glob.glob('files/udev/*'):
        shutil.copy(x, '/lib/udev/rules.d')
    subprocess.check_call(['udevadm', 'control',
                           '--reload-rules'])


@hooks.hook('install.real')
@harden()
def install():
    add_source(config('source'), config('key'))
    apt_update(fatal=True)
    apt_install(packages=ceph.determine_packages(), fatal=True)
    if config('autotune'):
        log('The autotune config is deprecated and planned '
            'for removal in the next release.', level=WARNING)
        tune_network_adapters()
    install_udev_rules()


def az_info():
    az_info = ""
    config_az = config("availability_zone")
    juju_az_info = os.environ.get('JUJU_AVAILABILITY_ZONE')
    if juju_az_info:
        # NOTE(jamespage): avoid conflicting key with root
        #                  of crush hierarchy
        if juju_az_info == 'default':
            juju_az_info = 'default-rack'
        az_info = "{} rack={}".format(az_info, juju_az_info)
    if config_az:
        # NOTE(jamespage): avoid conflicting key with root
        #                  of crush hierarchy
        if config_az == 'default':
            config_az = 'default-row'
        az_info = "{} row={}".format(az_info, config_az)
    if az_info != "":
        log("AZ Info: " + az_info)
        return az_info


def use_short_objects():
    '''
    Determine whether OSD's should be configured with
    limited object name lengths.

    @return: boolean indicating whether OSD's should be limited
    '''
    if cmp_pkgrevno('ceph', "10.2.0") >= 0:
        if config('osd-format') in ('ext4'):
            return True
        devices = config('osd-devices')
        if not devices:
            return False

        for device in devices.split():
            if device and not device.startswith('/dev'):
                # TODO: determine format of directory based
                #       OSD location
                return True
    return False


def get_ceph_context(upgrading=False):
    """Returns the current context dictionary for generating ceph.conf

    :param upgrading: bool - determines if the context is invoked as
                      part of an upgrade procedure. Setting this to true
                      causes settings useful during an upgrade to be
                      defined in the ceph.conf file
    """
    mon_hosts = get_mon_hosts()
    log('Monitor hosts are ' + repr(mon_hosts))

    networks = get_networks('ceph-public-network')
    public_network = ', '.join(networks)

    networks = get_networks('ceph-cluster-network')
    cluster_network = ', '.join(networks)

    cephcontext = {
        'auth_supported': get_auth(),
        'mon_hosts': ' '.join(mon_hosts),
        'fsid': get_fsid(),
        'old_auth': cmp_pkgrevno('ceph', "0.51") < 0,
        'crush_initial_weight': config('crush-initial-weight'),
        'osd_journal_size': config('osd-journal-size'),
        'osd_max_backfills': config('osd-max-backfills'),
        'osd_recovery_max_active': config('osd-recovery-max-active'),
        'use_syslog': str(config('use-syslog')).lower(),
        'ceph_public_network': public_network,
        'ceph_cluster_network': cluster_network,
        'loglevel': config('loglevel'),
        'dio': str(config('use-direct-io')).lower(),
        'short_object_len': use_short_objects(),
        'upgrade_in_progress': upgrading,
        'bluestore': use_bluestore(),
        'bluestore_experimental': cmp_pkgrevno('ceph', '12.1.0') < 0,
        'bluestore_block_wal_size': config('bluestore-block-wal-size'),
        'bluestore_block_db_size': config('bluestore-block-db-size'),
    }

    try:
        cephcontext['bdev_discard'] = get_bdev_enable_discard()
    except ValueError as ex:
        # the user set bdev-enable-discard to a non valid value, so logging the
        # issue as a warning and falling back to False/disable
        log(str(ex), level=WARNING)
        cephcontext['bdev_discard'] = False

    if config('prefer-ipv6'):
        dynamic_ipv6_address = get_ipv6_addr()[0]
        if not public_network:
            cephcontext['public_addr'] = dynamic_ipv6_address
        if not cluster_network:
            cephcontext['cluster_addr'] = dynamic_ipv6_address
    else:
        cephcontext['public_addr'] = get_public_addr()
        cephcontext['cluster_addr'] = get_cluster_addr()

    if config('customize-failure-domain'):
        az = az_info()
        if az:
            cephcontext['crush_location'] = "root=default {} host={}" \
                .format(az, socket.gethostname())
        else:
            log(
                "Your Juju environment doesn't"
                "have support for Availability Zones"
            )

    # NOTE(dosaboy): these sections must correspond to what is supported in the
    #                config template.
    sections = ['global', 'osd']
    cephcontext.update(
        ch_ceph.CephOSDConfContext(permitted_sections=sections)())
    cephcontext.update(
        ch_context.CephBlueStoreCompressionContext()())
    return cephcontext


def emit_cephconf(upgrading=False):
    # Install ceph.conf as an alternative to support
    # co-existence with other charms that write this file
    charm_ceph_conf = "/var/lib/charm/{}/ceph.conf".format(service_name())
    mkdir(os.path.dirname(charm_ceph_conf), owner=ceph.ceph_user(),
          group=ceph.ceph_user())
    context = get_ceph_context(upgrading)
    write_file(charm_ceph_conf, render_template('ceph.conf', context),
               ceph.ceph_user(), ceph.ceph_user(), 0o644)
    install_alternative('ceph.conf', '/etc/ceph/ceph.conf',
                        charm_ceph_conf, 90)


@hooks.hook('config-changed')
@harden()
def config_changed():
    # Determine whether vaultlocker is required and install
    if use_vaultlocker():
        installed = len(filter_installed_packages(['vaultlocker'])) == 0
        if not installed:
            apt_install('vaultlocker', fatal=True)

    # Check if an upgrade was requested
    check_for_upgrade()

    # Preflight checks
    if config('osd-format') not in ceph.DISK_FORMATS:
        log('Invalid OSD disk format configuration specified', level=ERROR)
        sys.exit(1)

    if config('prefer-ipv6'):
        assert_charm_supports_ipv6()

    sysctl_dict = config('sysctl')
    if sysctl_dict:
        create_sysctl(sysctl_dict, '/etc/sysctl.d/50-ceph-osd-charm.conf')

    e_mountpoint = config('ephemeral-unmount')
    if e_mountpoint and ceph.filesystem_mounted(e_mountpoint):
        umount(e_mountpoint)
    prepare_disks_and_activate()
    install_apparmor_profile()
    add_to_updatedb_prunepath(STORAGE_MOUNT_PATH)


@hooks.hook('storage.real')
def prepare_disks_and_activate():
    if use_vaultlocker():
        # NOTE: vault/vaultlocker preflight check
        vault_kv = vaultlocker.VaultKVContext(vaultlocker.VAULTLOCKER_BACKEND)
        context = vault_kv()
        if not vault_kv.complete:
            log('Deferring OSD preparation as vault not ready',
                level=DEBUG)
            return
        else:
            log('Vault ready, writing vaultlocker configuration',
                level=DEBUG)
            vaultlocker.write_vaultlocker_conf(context)

    osd_journal = get_journal_devices()
    if not osd_journal.isdisjoint(set(get_devices())):
        raise ValueError('`osd-journal` and `osd-devices` options must not'
                         'overlap.')
    log("got journal devs: {}".format(osd_journal), level=DEBUG)

    # pre-flight check of eligible device pristinity
    devices = get_devices()

    # if a device has been previously touched we need to consider it as
    # non-pristine. If it needs to be re-processed it has to be zapped
    # via the respective action which also clears the unitdata entry.
    db = kv()
    touched_devices = db.get('osd-devices', [])
    devices = [dev for dev in devices if dev not in touched_devices]
    log('Skipping osd devices previously processed by this unit: {}'
        .format(touched_devices))
    # filter osd-devices that are file system paths
    devices = [dev for dev in devices if dev.startswith('/dev')]
    # filter osd-devices that does not exist on this unit
    devices = [dev for dev in devices if os.path.exists(dev)]
    # filter osd-devices that are already mounted
    devices = [dev for dev in devices if not is_device_mounted(dev)]
    # filter osd-devices that are active bluestore devices
    devices = [dev for dev in devices
               if not ceph.is_active_bluestore_device(dev)]
    # filter osd-devices that are used as dmcrypt devices
    devices = [dev for dev in devices
               if not ceph.is_mapped_luks_device(dev)]

    log('Checking for pristine devices: "{}"'.format(devices), level=DEBUG)
    if not all(ceph.is_pristine_disk(dev) for dev in devices):
        status_set('blocked',
                   'Non-pristine devices detected, consult '
                   '`list-disks`, `zap-disk` and `blacklist-*` actions.')
        return

    if is_osd_bootstrap_ready():
        log('ceph bootstrapped, rescanning disks')
        emit_cephconf()
        bluestore = use_bluestore()
        ceph.udevadm_settle()
        for dev in get_devices():
            ceph.osdize(dev, config('osd-format'),
                        osd_journal,
                        config('ignore-device-errors'),
                        config('osd-encrypt'),
                        bluestore,
                        config('osd-encrypt-keymanager'))
            # Make it fast!
            if config('autotune'):
                log('The autotune config is deprecated and planned '
                    'for removal in the next release.', level=WARNING)
                ceph.tune_dev(dev)
        ceph.start_osds(get_devices())

    # Notify MON cluster as to how many OSD's this unit bootstrapped
    # into the cluster
    for r_id in relation_ids('mon'):
        relation_set(
            relation_id=r_id,
            relation_settings={
                'bootstrapped-osds': len(db.get('osd-devices', [])),
                'ceph_release': ceph.resolve_ceph_version(
                    hookenv.config('source') or 'distro'
                )
            }
        )


def get_mon_hosts():
    hosts = []
    for relid in relation_ids('mon'):
        for unit in related_units(relid):
            addr = \
                relation_get('ceph-public-address',
                             unit,
                             relid) or get_host_ip(
                    relation_get(
                        'private-address',
                        unit,
                        relid))

            if addr:
                hosts.append('{}'.format(format_ipv6_addr(addr) or addr))

    return sorted(hosts)


def get_fsid():
    return get_conf('fsid')


def get_auth():
    return get_conf('auth')


def get_conf(name):
    for relid in relation_ids('mon'):
        for unit in related_units(relid):
            conf = relation_get(name,
                                unit, relid)
            if conf:
                return conf
    return None


def get_devices():
    devices = []
    if config('osd-devices'):
        for path in config('osd-devices').split(' '):
            path = path.strip()
            # Ensure that only block devices
            # are considered for evaluation as block devices.
            # This avoids issues with relative directories
            # being passed via configuration, and ensures that
            # the path to a block device provided by the user
            # is used, rather than its target which may change
            # between reboots in the case of bcache devices.
            if is_block_device(path):
                devices.append(path)
            # Make sure its a device which is specified using an
            # absolute path so that the current working directory
            # or any relative path under this directory is not used
            elif os.path.isabs(path):
                devices.append(os.path.realpath(path))

    # List storage instances for the 'osd-devices'
    # store declared for this charm too, and add
    # their block device paths to the list.
    storage_ids = storage_list('osd-devices')
    devices.extend((storage_get('location', s) for s in storage_ids))

    # Filter out any devices in the action managed unit-local device blacklist
    _blacklist = get_blacklist()
    return [device for device in devices if device not in _blacklist]


def get_bdev_enable_discard():
    bdev_enable_discard = config('bdev-enable-discard').lower()
    if bdev_enable_discard in ['enable', 'enabled']:
        return True
    elif bdev_enable_discard == 'auto':
        return should_enable_discard(get_devices())
    elif bdev_enable_discard in ['disable', 'disabled']:
        return False
    else:
        raise ValueError(("Invalid value for configuration "
                          "bdev-enable-discard: %s") % bdev_enable_discard)


@hooks.hook('mon-relation-changed',
            'mon-relation-departed')
def mon_relation():
    bootstrap_key = relation_get('osd_bootstrap_key')
    upgrade_key = relation_get('osd_upgrade_key')
    if get_fsid() and get_auth() and bootstrap_key:
        log('mon has provided conf- scanning disks')
        emit_cephconf()
        import_osd_bootstrap_key(bootstrap_key)
        import_osd_upgrade_key(upgrade_key)
        prepare_disks_and_activate()
        _, settings, _ = (ch_ceph.CephOSDConfContext()
                          .filter_osd_from_mon_settings())
        ceph.apply_osd_settings(settings)
    else:
        log('mon cluster has not yet provided conf')


@hooks.hook('upgrade-charm.real')
@harden()
def upgrade_charm():
    apt_install(packages=filter_installed_packages(ceph.determine_packages()),
                fatal=True)
    if get_fsid() and get_auth():
        emit_cephconf()
    install_udev_rules()
    remap_resolved_targets()
    maybe_refresh_nrpe_files()
    # NOTE(jamespage): https://pad.lv/1861996
    # ensure number of bootstrapped OSD's is presented to ceph-mon
    prepare_disks_and_activate()


def remap_resolved_targets():
    '''Remap any previous fully resolved target devices to provided names'''
    # NOTE(jamespage): Deal with any prior provided dev to
    # target device resolution which occurred in prior
    # releases of the charm - the user provided value
    # should be used in preference to the target path
    # to the block device as in some instances this
    # is not consistent between reboots (bcache).
    db = kv()
    touched_devices = db.get('osd-devices', [])
    osd_devices = get_devices()
    for dev in osd_devices:
        real_path = os.path.realpath(dev)
        if real_path != dev and real_path in touched_devices:
            log('Device {} already processed by charm using '
                'actual device path {}, updating block device '
                'usage with provided device path '
                'and skipping'.format(dev,
                                      real_path))
            touched_devices.remove(real_path)
            touched_devices.append(dev)
    db.set('osd-devices', touched_devices)
    db.flush()


@hooks.hook('nrpe-external-master-relation-joined',
            'nrpe-external-master-relation-changed')
def update_nrpe_config():
    # python-dbus is used by check_upstart_job
    # fasteners is used by apt_install collect_ceph_osd_services.py
    pkgs = ['python3-dbus']
    if CompareHostReleases(lsb_release()['DISTRIB_CODENAME']) >= 'bionic':
        pkgs.append('python3-fasteners')
    apt_install(pkgs)

    # copy the check and collect files over to the plugins directory
    charm_dir = os.environ.get('CHARM_DIR', '')
    nagios_plugins = '/usr/local/lib/nagios/plugins'
    # Grab nagios user/group ID's from original source
    _dir = os.stat(nagios_plugins)
    uid = _dir.st_uid
    gid = _dir.st_gid
    for name in ('collect_ceph_osd_services.py', 'check_ceph_osd_services.py'):
        target = os.path.join(nagios_plugins, name)
        shutil.copy(os.path.join(charm_dir, 'files', 'nagios', name), target)
        os.chown(target, uid, gid)

    hostname = nrpe.get_nagios_hostname()
    current_unit = nrpe.get_nagios_unit_name()

    # BUG#1810749 - the nagios user can't access /var/lib/ceph/.. and that's a
    # GOOD THING, as it keeps ceph secure from Nagios.  However, to check
    # whether ceph is okay, the check_systemd.py or 'status ceph-osd' still
    # needs to be called with the contents of ../osd/ceph-*/whoami files.  To
    # get around this conundrum, instead a cron.d job that runs as root will
    # perform the checks every minute, and write to a temporary file the
    # results, and the nrpe check will grep this file and error out (return 2)
    # if the first 3 characters of a line are not 'OK:'.

    cmd = ('MAILTO=""\n'
           '* * * * * root '
           '/usr/local/lib/nagios/plugins/collect_ceph_osd_services.py'
           ' 2>&1 | logger -t check-osd\n')
    with open(CRON_CEPH_CHECK_FILE, "wt") as f:
        f.write(cmd)

    nrpe_cmd = '/usr/local/lib/nagios/plugins/check_ceph_osd_services.py'

    nrpe_setup = nrpe.NRPE(hostname=hostname)
    nrpe_setup.add_check(
        shortname='ceph-osd',
        description='process check {%s}' % current_unit,
        check_cmd=nrpe_cmd
    )
    nrpe_setup.write()


def maybe_refresh_nrpe_files():
    """if the nrpe-external-master relation exists then refresh the nrpe
    configuration -- this is called during a charm upgrade
    """
    if relations_of_type('nrpe-external-master'):
        update_nrpe_config()


@hooks.hook('secrets-storage-relation-joined')
def secrets_storage_joined(relation_id=None):
    relation_set(relation_id=relation_id,
                 secret_backend='charm-vaultlocker',
                 isolated=True,
                 access_address=get_relation_ip('secrets-storage'),
                 unit_name=local_unit(),
                 hostname=socket.gethostname())


@hooks.hook('secrets-storage-relation-changed')
def secrets_storage_changed():
    vault_ca = relation_get('vault_ca')
    if vault_ca:
        vault_ca = base64.decodebytes(json.loads(vault_ca).encode())
        write_file('/usr/local/share/ca-certificates/vault-ca.crt',
                   vault_ca, perms=0o644)
        subprocess.check_call(['update-ca-certificates', '--fresh'])
    prepare_disks_and_activate()


VERSION_PACKAGE = 'ceph-common'


def assess_status():
    """Assess status of current unit"""
    # check to see if the unit is paused.
    application_version_set(get_upstream_version(VERSION_PACKAGE))
    if is_unit_upgrading_set():
        status_set("blocked",
                   "Ready for do-release-upgrade and reboot. "
                   "Set complete when finished.")
        return
    if is_unit_paused_set():
        status_set('maintenance',
                   "Paused. Use 'resume' action to resume normal service.")
        return
    # Check for mon relation
    if len(relation_ids('mon')) < 1:
        status_set('blocked', 'Missing relation: monitor')
        return

    # Check for monitors with presented addresses
    # Check for bootstrap key presentation
    monitors = get_mon_hosts()
    if len(monitors) < 1 or not get_conf('osd_bootstrap_key'):
        status_set('waiting', 'Incomplete relation: monitor')
        return

    # Check for vault
    if use_vaultlocker():
        if not relation_ids('secrets-storage'):
            status_set('blocked', 'Missing relation: vault')
            return
        try:
            if not vaultlocker.vault_relation_complete():
                status_set('waiting', 'Incomplete relation: vault')
                return
        except Exception as e:
            status_set('blocked', "Warning: couldn't verify vault relation")
            log("Exception when verifying vault relation - maybe it was "
                "offline?:\n{}".format(str(e)))
            log("Traceback: {}".format(traceback.format_exc()))

    # Check for OSD device creation parity i.e. at least some devices
    # must have been presented and used for this charm to be operational
    (prev_status, prev_message) = status_get()
    running_osds = ceph.get_running_osds()
    if not prev_message.startswith('Non-pristine'):
        if not running_osds:
            status_set('blocked',
                       'No block devices detected using current configuration')
        else:
            status_set('active',
                       'Unit is ready ({} OSD)'.format(len(running_osds)))
    else:
        pristine = True
        osd_journals = get_journal_devices()
        for dev in list(set(ceph.unmounted_disks()) - set(osd_journals)):
            if (not ceph.is_active_bluestore_device(dev) and
                    not ceph.is_pristine_disk(dev) and
                    not ceph.is_mapped_luks_device(dev)):
                pristine = False
                break
        if pristine:
            status_set('active',
                       'Unit is ready ({} OSD)'.format(len(running_osds)))

    try:
        get_bdev_enable_discard()
    except ValueError as ex:
        status_set('blocked', str(ex))

    try:
        bluestore_compression = ch_context.CephBlueStoreCompressionContext()
        bluestore_compression.validate()
    except ValueError as e:
        status_set('blocked', 'Invalid configuration: {}'.format(str(e)))


@hooks.hook('update-status')
@harden()
def update_status():
    log('Updating status.')


@hooks.hook('pre-series-upgrade')
def pre_series_upgrade():
    log("Running prepare series upgrade hook", "INFO")
    # NOTE: The Ceph packages handle the series upgrade gracefully.
    # In order to indicate the step of the series upgrade process for
    # administrators and automated scripts, the charm sets the paused and
    # upgrading states.
    set_unit_paused()
    set_unit_upgrading()


@hooks.hook('post-series-upgrade')
def post_series_upgrade():
    log("Running complete series upgrade hook", "INFO")
    # In order to indicate the step of the series upgrade process for
    # administrators and automated scripts, the charm clears the paused and
    # upgrading states.
    clear_unit_paused()
    clear_unit_upgrading()


if __name__ == '__main__':
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        log('Unknown hook {} - skipping.'.format(e))
    assess_status()
