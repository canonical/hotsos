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

import os
import re
import pwd
import subprocess
import platform
import uuid

from itertools import chain
from base64 import b64decode
from copy import deepcopy
from subprocess import (
    check_call,
    check_output,
    CalledProcessError
)

from charmhelpers.fetch import (
    apt_update,
    apt_upgrade,
    apt_install,
    apt_purge,
    apt_autoremove,
    apt_mark,
    filter_missing_packages,
    filter_installed_packages,
)

from charmhelpers.core.fstab import Fstab
from charmhelpers.core.host import (
    mkdir,
    service_restart,
    lsb_release,
    rsync,
    CompareHostReleases,
    mount,
    fstab_add,
)

from charmhelpers.core.hookenv import (
    charm_dir,
    config,
    log,
    related_units,
    relation_ids,
    relation_get,
    status_set,
    DEBUG,
    INFO,
    WARNING,
    storage_list,
    storage_get,
    hook_name,
)

from charmhelpers.core.decorators import retry_on_exception
from charmhelpers.contrib.openstack import templating, context
from charmhelpers.contrib.openstack.alternatives import install_alternative

from charmhelpers.contrib.openstack.utils import (
    configure_installation_source,
    get_os_codename_install_source,
    get_subordinate_release_packages,
    get_subordinate_services,
    os_release,
    reset_os_release,
    is_unit_paused_set,
    make_assess_status_func,
    pause_unit,
    resume_unit,
    os_application_version_set,
    CompareOpenStackReleases,
)

from charmhelpers.core.hugepage import hugepage_support

from nova_compute_context import (
    nova_metadata_requirement,
    CloudComputeContext,
    CloudComputeVendorJSONContext,
    LxdContext,
    MetadataServiceContext,
    NovaComputeLibvirtContext,
    NovaComputeLibvirtOverrideContext,
    NovaComputeCephContext,
    NeutronComputeContext,
    InstanceConsoleContext,
    IronicAPIContext,
    CEPH_CONF,
    ceph_config_file,
    HostIPContext,
    NovaComputeVirtContext,
    NOVA_API_AA_PROFILE,
    NOVA_COMPUTE_AA_PROFILE,
    NOVA_NETWORK_AA_PROFILE,
    NovaAPIAppArmorContext,
    NovaComputeAppArmorContext,
    NovaNetworkAppArmorContext,
    SerialConsoleContext,
    NovaComputeAvailabilityZoneContext,
    NeutronPluginSubordinateConfigContext,
    NovaComputePlacementContext,
)

import charmhelpers.contrib.openstack.vaultlocker as vaultlocker

from charmhelpers.core.unitdata import kv

from charmhelpers.contrib.storage.linux.utils import (
    is_block_device,
    is_device_mounted,
    mkfs_xfs,
)

from charmhelpers.core.templating import render

CA_CERT_PATH = '/usr/local/share/ca-certificates/keystone_juju_ca_cert.crt'

TEMPLATES = 'templates/'

BASE_PACKAGES = [
    'nova-compute',
    'genisoimage',  # was missing as a package dependency until raring.
    'librbd1',  # bug 1440953
    'python-six',
    'python-psutil',
    'xfsprogs',
    'nfs-common',
    'open-iscsi',
    'numactl',
    'python3-novaclient',  # lib required by juju actions
    'python3-neutronclient',  # lib required by juju actions
    'python3-keystoneauth1',  # lib required by juju actions
    'ovmf',  # required for uefi based instances
]

PY3_PACKAGES = [
    'python3-nova',
    'python3-memcache',
    'python3-rados',
    'python3-rbd',
]

PURGE_PACKAGES = [
    'python-ceilometer',
    'python-neutron',
    'python-neutron-fwaas',
    'python-nova',
    'python-nova-lxd',
]

MULTIPATH_PACKAGES = [
    'multipath-tools',
    'sysfsutils',
]

HELD_PACKAGES = [
    'python-memcache',
    'python-six',
    'python-psutil',
]

VERSION_PACKAGE = 'nova-common'

DEFAULT_INSTANCE_PATH = '/var/lib/nova/instances'
NOVA_CONF_DIR = "/etc/nova"
QEMU_CONF = '/etc/libvirt/qemu.conf'
LIBVIRTD_CONF = '/etc/libvirt/libvirtd.conf'
LIBVIRT_BIN = '/etc/default/libvirt-bin'
LIBVIRT_BIN_OVERRIDES = '/etc/init/libvirt-bin.override'
NOVA_CONF = '%s/nova.conf' % NOVA_CONF_DIR
NOVA_COMPUTE_CONF = '%s/nova-compute.conf' % NOVA_CONF_DIR
VENDORDATA_FILE = '%s/vendor_data.json' % NOVA_CONF_DIR
QEMU_KVM = '/etc/default/qemu-kvm'
NOVA_API_AA_PROFILE_PATH = ('/etc/apparmor.d/{}'.format(NOVA_API_AA_PROFILE))
NOVA_COMPUTE_AA_PROFILE_PATH = ('/etc/apparmor.d/{}'
                                ''.format(NOVA_COMPUTE_AA_PROFILE))
NOVA_NETWORK_AA_PROFILE_PATH = ('/etc/apparmor.d/{}'
                                ''.format(NOVA_NETWORK_AA_PROFILE))

NOVA_COMPUTE_OVERRIDE_DIR = '/etc/systemd/system/nova-compute.service.d'
MOUNT_DEPENDENCY_OVERRIDE = '99-mount.conf'

LIBVIRT_TYPES = ['kvm', 'qemu', 'lxc']

USE_FQDN_KEY = 'nova-compute-charm-use-fqdn'


def use_fqdn_hint():
    """Hint for whether FQDN should be used for agent registration

    :returns: True or False
    :rtype: bool
    """
    db = kv()
    return db.get(USE_FQDN_KEY, False)


BASE_RESOURCE_MAP = {
    NOVA_CONF: {
        'services': ['nova-compute'],
        'contexts': [context.AMQPContext(ssl_dir=NOVA_CONF_DIR),
                     context.SharedDBContext(
                         relation_prefix='nova', ssl_dir=NOVA_CONF_DIR),
                     context.ImageServiceContext(),
                     context.OSConfigFlagContext(),
                     CloudComputeContext(),
                     LxdContext(),
                     IronicAPIContext(),
                     NovaComputeLibvirtContext(),
                     NovaComputeCephContext(),
                     context.SyslogContext(),
                     NeutronPluginSubordinateConfigContext(
                         interface=['neutron-plugin'],
                         service=['nova-compute', 'nova'],
                         config_file=NOVA_CONF),
                     context.SubordinateConfigContext(
                         interface=['nova-ceilometer',
                                    'ephemeral-backend'],
                         service=['nova-compute', 'nova'],
                         config_file=NOVA_CONF),
                     InstanceConsoleContext(),
                     context.ZeroMQContext(),
                     context.NotificationDriverContext(),
                     MetadataServiceContext(),
                     HostIPContext(),
                     NovaComputeVirtContext(),
                     context.LogLevelContext(),
                     context.InternalEndpointContext(),
                     context.VolumeAPIContext('nova-common'),
                     SerialConsoleContext(),
                     NovaComputeAvailabilityZoneContext(),
                     NovaComputePlacementContext(),
                     context.WorkerConfigContext(),
                     vaultlocker.VaultKVContext(
                         vaultlocker.VAULTLOCKER_BACKEND),
                     context.IdentityCredentialsContext(
                         rel_name='cloud-credentials'),
                     context.HostInfoContext(use_fqdn_hint_cb=use_fqdn_hint),
                     ],
    },
    VENDORDATA_FILE: {
        'services': [],
        'contexts': [CloudComputeVendorJSONContext()],
    },
    NOVA_API_AA_PROFILE_PATH: {
        'services': ['nova-api'],
        'contexts': [NovaAPIAppArmorContext()],
    },
    NOVA_COMPUTE_AA_PROFILE_PATH: {
        'services': ['nova-compute'],
        'contexts': [NovaComputeAppArmorContext()],
    },
    NOVA_NETWORK_AA_PROFILE_PATH: {
        'services': ['nova-network'],
        'contexts': [NovaNetworkAppArmorContext()],
    },
}

LIBVIRTD_DAEMON = 'libvirtd'
LIBVIRT_BIN_DAEMON = 'libvirt-bin'

LIBVIRT_RESOURCE_MAP = {
    QEMU_CONF: {
        'services': [LIBVIRT_BIN_DAEMON],
        'contexts': [NovaComputeLibvirtContext()],
    },
    QEMU_KVM: {
        'services': ['qemu-kvm'],
        'contexts': [NovaComputeLibvirtContext()],
    },
    LIBVIRTD_CONF: {
        'services': [LIBVIRT_BIN_DAEMON],
        'contexts': [NovaComputeLibvirtContext()],
    },
    LIBVIRT_BIN: {
        'services': [LIBVIRT_BIN_DAEMON],
        'contexts': [NovaComputeLibvirtContext()],
    },
    LIBVIRT_BIN_OVERRIDES: {
        'services': [LIBVIRT_BIN_DAEMON],
        'contexts': [NovaComputeLibvirtOverrideContext()],
    },
}
LIBVIRT_RESOURCE_MAP.update(BASE_RESOURCE_MAP)

CEPH_SECRET = '/etc/ceph/secret.xml'
CEPH_BACKEND_SECRET = '/etc/ceph/secret-{}.xml'

CEPH_RESOURCES = {
    CEPH_SECRET: {
        'contexts': [NovaComputeCephContext()],
        'services': [],
    }
}

# Maps virt-type config to a compute package(s).
VIRT_TYPES = {
    'kvm': ['nova-compute-kvm'],
    'qemu': ['nova-compute-qemu'],
    'uml': ['nova-compute-uml'],
    'lxc': ['nova-compute-lxc'],
    'lxd': ['nova-compute-lxd'],
    'ironic': ['nova-compute-ironic'],
}


# Maps virt-type config to a libvirt URI.
LIBVIRT_URIS = {
    'kvm': 'qemu:///system',
    'qemu': 'qemu:///system',
    'uml': 'uml:///system',
    'lxc': 'lxc:///',
}

# The interface is said to be satisfied if anyone of the interfaces in the
# list has a complete context.
REQUIRED_INTERFACES = {
    'messaging': ['amqp'],
    'image': ['image-service'],
    'compute': ['cloud-compute'],
}


def libvirt_daemon():
    '''Resolve the correct name of the libvirt daemon service'''
    distro_codename = lsb_release()['DISTRIB_CODENAME'].lower()
    if (CompareHostReleases(distro_codename) >= 'yakkety' or
            CompareOpenStackReleases(os_release('nova-common')) >= 'ocata'):
        return LIBVIRTD_DAEMON
    else:
        return LIBVIRT_BIN_DAEMON


def vaultlocker_installed():
    return len(filter_installed_packages(['vaultlocker'])) == 0


def resource_map():
    '''
    Dynamically generate a map of resources that will be managed for a single
    hook execution.
    '''
    # TODO: Cache this on first call?
    virt_type = config('virt-type').lower()
    if virt_type in ('lxd', 'ironic'):
        resource_map = deepcopy(BASE_RESOURCE_MAP)
    else:
        resource_map = deepcopy(LIBVIRT_RESOURCE_MAP)

    # if vault deps are not installed it is not yet possible to check the vault
    # context status since it requires the hvac dependency.
    if not vaultlocker_installed():
        to_delete = []
        for item in resource_map[NOVA_CONF]['contexts']:
            if isinstance(item, type(vaultlocker.VaultKVContext())):
                to_delete.append(item)

        for item in to_delete:
            resource_map[NOVA_CONF]['contexts'].remove(item)

    net_manager = network_manager()

    # Network manager gets set late by the cloud-compute interface.
    # FlatDHCPManager only requires some extra packages.
    cmp_os_release = CompareOpenStackReleases(os_release('nova-common'))
    if (net_manager in ['flatmanager', 'flatdhcpmanager'] and
            config('multi-host').lower() == 'yes' and
            cmp_os_release < 'ocata'):
        resource_map[NOVA_CONF]['services'].extend(
            ['nova-api', 'nova-network']
        )
    else:
        resource_map.pop(NOVA_API_AA_PROFILE_PATH)
        resource_map.pop(NOVA_NETWORK_AA_PROFILE_PATH)

    if virt_type == 'ironic':
        # NOTE(gsamfira): OpenStack versions prior to Victoria do not have a
        # dedicated nova-compute-ironic package which provides a suitable
        # nova-compute.conf file. We use a template to compensate for that.
        if cmp_os_release < 'victoria':
            resource_map[NOVA_COMPUTE_CONF] = {
                "services": ["nova-compute"],
                "contexts": [],
            }

    cmp_distro_codename = CompareHostReleases(
        lsb_release()['DISTRIB_CODENAME'].lower())
    if (cmp_distro_codename >= 'yakkety' or cmp_os_release >= 'ocata'):
        for data in resource_map.values():
            if LIBVIRT_BIN_DAEMON in data['services']:
                data['services'].remove(LIBVIRT_BIN_DAEMON)
                data['services'].append(LIBVIRTD_DAEMON)

    # Neutron/quantum requires additional contexts, as well as new resources
    # depending on the plugin used.
    # NOTE(james-page): only required for ovs plugin right now
    if net_manager in ['neutron', 'quantum']:
        resource_map[NOVA_CONF]['contexts'].append(NeutronComputeContext())

    if relation_ids('ceph'):
        CEPH_RESOURCES[ceph_config_file()] = {
            'contexts': [NovaComputeCephContext()],
            'services': ['nova-compute']
        }
        resource_map.update(CEPH_RESOURCES)

    enable_nova_metadata, _ = nova_metadata_requirement()
    if enable_nova_metadata:
        resource_map[NOVA_CONF]['services'].append('nova-api-metadata')

    # NOTE(james-page): If not on an upstart based system, don't write
    #                   and override file for libvirt-bin.
    if not os.path.exists('/etc/init'):
        if LIBVIRT_BIN_OVERRIDES in resource_map:
            del resource_map[LIBVIRT_BIN_OVERRIDES]

    return resource_map


def restart_map():
    '''
    Constructs a restart map based on charm config settings and relation
    state.
    '''
    return {k: v['services'] for k, v in resource_map().items()}


def services():
    '''
    Returns a list of services associated with this charm and its subordinates.
    '''
    # NOTE(lourot): the order is important when resuming the services. For
    # example the ceilometer-agent-compute service, coming from the
    # ceilometer-agent subordinate charm, has a dependency to the nova-compute
    # service. Attempting to start the ceilometer-agent-compute service first
    # will then fail. Thus we return the services here in a resume-friendly
    # order, i.e. the principal services first, then the subordinate ones.
    return (list(set(chain(*restart_map().values()))) +
            list(get_subordinate_services()))


def register_configs():
    '''
    Returns an OSTemplateRenderer object with all required configs registered.
    '''
    release = os_release('nova-common')
    configs = templating.OSConfigRenderer(templates_dir=TEMPLATES,
                                          openstack_release=release)

    if relation_ids('ceph'):
        # Add charm ceph configuration to resources and
        # ensure directory actually exists
        mkdir(os.path.dirname(ceph_config_file()))
        mkdir(os.path.dirname(CEPH_CONF))
        # Install ceph config as an alternative for co-location with
        # ceph and ceph-osd charms - nova-compute ceph.conf will be
        # lower priority than both of these but that's OK
        if not os.path.exists(ceph_config_file()):
            # touch file for pre-templated generation
            open(ceph_config_file(), 'w').close()
        install_alternative(os.path.basename(CEPH_CONF),
                            CEPH_CONF, ceph_config_file())

    for cfg, d in resource_map().items():
        configs.register(cfg, d['contexts'])
    return configs


def determine_packages_arch():
    '''Generate list of architecture-specific packages'''
    packages = []
    distro_codename = lsb_release()['DISTRIB_CODENAME'].lower()
    if (platform.machine() == 'aarch64' and
            CompareHostReleases(distro_codename) >= 'wily'):
        packages.extend(['qemu-efi']),  # AArch64 cloud images require UEFI fw

    return packages


def determine_packages():
    release = os_release('nova-common')
    cmp_release = CompareOpenStackReleases(release)

    packages = [] + BASE_PACKAGES

    net_manager = network_manager()
    if (net_manager in ['flatmanager', 'flatdhcpmanager'] and
            config('multi-host').lower() == 'yes' and
            CompareOpenStackReleases(os_release('nova-common')) < 'ocata'):
        packages.extend(['nova-api', 'nova-network'])

    if relation_ids('ceph'):
        packages.append('ceph-common')

    virt_type = config('virt-type')
    if virt_type == 'ironic' and release < 'victoria':
        # ironic compute driver is part of nova and
        # gets installed along with python3-nova
        # The nova-compute-ironic metapackage that satisfies
        # nova-compute-hypervisor does not exist for versions of
        # OpenStack prior to Victoria. Use nova-compute-vmware,
        # as that package has the least amount of dependencies.
        # We also add python3-ironicclient here. This is a dependency
        # which gets installed by nova-compute-ironic in Victoria and later.
        VIRT_TYPES[virt_type] = [
            'nova-compute-vmware',
            'python3-ironicclient']
    try:
        packages.extend(VIRT_TYPES[virt_type])
    except KeyError:
        log('Unsupported virt-type configured: %s' % virt_type)
        raise
    enable_nova_metadata, _ = nova_metadata_requirement()
    if enable_nova_metadata:
        packages.append('nova-api-metadata')

    packages.extend(determine_packages_arch())

    # LP#1806830 - ensure that multipath packages are installed when
    # use-multipath option is enabled.
    if config('use-multipath'):
        packages.extend(MULTIPATH_PACKAGES)

    if cmp_release >= 'rocky':
        packages = [p for p in packages if not p.startswith('python-')]
        packages.extend(PY3_PACKAGES)
        if filter_missing_packages(['python-ceilometer']):
            packages.append('python3-ceilometer')
        if filter_missing_packages(['python-neutron']):
            packages.append('python3-neutron')
        if filter_missing_packages(['python-neutron-fwaas']):
            packages.append('python3-neutron-fwaas')
        if virt_type == 'lxd':
            packages.append('python3-nova-lxd')

    packages = sorted(set(packages).union(get_subordinate_release_packages(
        release).install))

    return packages


def determine_purge_packages():
    '''Return a list of packages to purge for the current OS release'''
    release = os_release('nova-common')
    cmp_release = CompareOpenStackReleases(release)
    packages = []
    if cmp_release >= 'rocky':
        packages.extend(PURGE_PACKAGES)
    packages = sorted(set(packages).union(get_subordinate_release_packages(
        release).purge))
    return packages


def remove_old_packages():
    '''Purge any packages that need to be removed.

    :returns: bool Whether packages were removed.
    '''
    installed_packages = filter_missing_packages(
        determine_purge_packages()
    )
    if installed_packages:
        apt_mark(filter_missing_packages(determine_held_packages()),
                 'auto')
        apt_purge(installed_packages, fatal=True)
        apt_autoremove(purge=True, fatal=True)
    return bool(installed_packages)


def determine_held_packages():
    '''Return a list of packages to mark as candidates for removal
    for the current OS release'''
    cmp_os_source = CompareOpenStackReleases(os_release('nova-common'))
    if cmp_os_source >= 'rocky':
        return HELD_PACKAGES
    return []


def migration_enabled():
    # XXX: confirm juju-core bool behavior is the same.
    return config('enable-live-migration')


def _network_config():
    '''
    Obtain all relevant network configuration settings from nova-c-c via
    cloud-compute interface.
    '''
    settings = ['network_manager', 'neutron_plugin', 'quantum_plugin']
    net_config = {}
    for rid in relation_ids('cloud-compute'):
        for unit in related_units(rid):
            for setting in settings:
                value = relation_get(setting, rid=rid, unit=unit)
                if value:
                    net_config[setting] = value
    return net_config


def neutron_plugin():
    return (_network_config().get('neutron_plugin') or
            _network_config().get('quantum_plugin'))


def network_manager():
    '''
    Obtain the network manager advertised by nova-c-c, renaming to Quantum
    if required
    '''
    manager = _network_config().get('network_manager')
    if manager:
        manager = manager.lower()
        if manager != 'neutron':
            return manager
        else:
            return 'neutron'
    return manager


def public_ssh_key(user='root'):
    home = pwd.getpwnam(user).pw_dir
    try:
        with open(os.path.join(home, '.ssh', 'id_rsa.pub')) as key:
            return key.read().strip()
    except OSError:
        return None


def initialize_ssh_keys(user='root'):
    home_dir = pwd.getpwnam(user).pw_dir
    ssh_dir = os.path.join(home_dir, '.ssh')
    if not os.path.isdir(ssh_dir):
        os.mkdir(ssh_dir)

    priv_key = os.path.join(ssh_dir, 'id_rsa')
    if not os.path.isfile(priv_key):
        log('Generating new ssh key for user %s.' % user)
        cmd = ['ssh-keygen', '-q', '-N', '', '-t', 'rsa', '-b', '2048',
               '-f', priv_key]
        check_output(cmd)

    pub_key = '%s.pub' % priv_key
    if not os.path.isfile(pub_key):
        log('Generating missing ssh public key @ %s.' % pub_key)
        cmd = ['ssh-keygen', '-y', '-f', priv_key]
        p = check_output(cmd).decode('UTF-8').strip()
        with open(pub_key, 'wt') as out:
            out.write(p)
    check_output(['chown', '-R', user, ssh_dir])


def set_ppc64_cpu_smt_state(smt_state):
    """Set ppc64_cpu smt state."""

    current_smt_state = check_output(['ppc64_cpu', '--smt']).decode('UTF-8')
    # Possible smt state values are integer or 'off'
    #   Ex. common ppc64_cpu query command output values:
    #      SMT=8
    #   -or-
    #      SMT is off

    if 'SMT={}'.format(smt_state) in current_smt_state:
        log('Not changing ppc64_cpu smt state ({})'.format(smt_state))
    elif smt_state == 'off' and 'SMT is off' in current_smt_state:
        log('Not changing ppc64_cpu smt state (already off)')
    else:
        log('Setting ppc64_cpu smt state: {}'.format(smt_state))
        cmd = ['ppc64_cpu', '--smt={}'.format(smt_state)]
        try:
            check_output(cmd)
        except CalledProcessError as e:
            # Known to fail in a container (host must pre-configure smt)
            msg = 'Failed to set ppc64_cpu smt state: {}'.format(smt_state)
            log(msg, level=WARNING)
            status_set('blocked', msg)
            raise e


def import_authorized_keys(user='root', prefix=None):
    """Import SSH authorized_keys + known_hosts from a cloud-compute relation.
    Store known_hosts in user's $HOME/.ssh and authorized_keys in a path
    specified using authorized-keys-path config option.

    The relation_get data is a series of key values of the form:

    [prefix_]known_hosts_max_index: <int>
    [prefix_]authorized_keys_max_index: <int>

    [prefix_]known_hosts_[n]: <str>
    [prefix_]authorized_keys_[n]: <str>

    :param user: the user to write the known hosts and keys for (default 'root)
    :type user: str
    :param prefix: A prefix to add to the relation data keys (default None)
    :type prefix: Option[str, None]
    """
    _prefix = "{}_".format(prefix) if prefix else ""

    # get all the data at once with one relation_get call
    rdata = relation_get() or {}

    known_hosts_index = int(
        rdata.get('{}known_hosts_max_index'.format(_prefix), '0'))
    authorized_keys_index = int(
        rdata.get('{}authorized_keys_max_index'.format(_prefix), '0'))

    if known_hosts_index == 0 or authorized_keys_index == 0:
        return

    homedir = pwd.getpwnam(user).pw_dir
    dest_auth_keys = config('authorized-keys-path').format(
        homedir=homedir, username=user)
    dest_known_hosts = os.path.join(homedir, '.ssh/known_hosts')
    log('Saving new known_hosts file to %s and authorized_keys file to: %s.' %
        (dest_known_hosts, dest_auth_keys))

    # write known hosts using data from relation_get
    with open(dest_known_hosts, 'wt') as f:
        for index in range(known_hosts_index):
            f.write("{}\n".format(
                rdata.get("{}known_hosts_{}".format(_prefix, index))))

    # write authorized keys using data from relation_get
    with open(dest_auth_keys, 'wt') as f:
        for index in range(authorized_keys_index):
            f.write("{}\n".format(
                rdata.get('{}authorized_keys_{}'.format(_prefix, index))))


def do_openstack_upgrade(configs):
    # NOTE(jamespage) horrible hack to make utils forget a cached value
    import charmhelpers.contrib.openstack.utils as utils
    utils.os_rel = None
    new_src = config('openstack-origin')
    new_os_rel = get_os_codename_install_source(new_src)
    log('Performing OpenStack upgrade to %s.' % (new_os_rel))

    configure_installation_source(new_src)
    apt_update(fatal=True)

    dpkg_opts = [
        '--option', 'Dpkg::Options::=--force-confnew',
        '--option', 'Dpkg::Options::=--force-confdef',
    ]

    apt_upgrade(options=dpkg_opts, fatal=True, dist=True)
    reset_os_release()
    apt_install(determine_packages(), fatal=True)

    remove_old_packages()

    configs.set_release(openstack_release=new_os_rel)
    configs.write_all()
    if not is_unit_paused_set():
        for s in services():
            service_restart(s)


def import_keystone_ca_cert():
    """If provided, import the Keystone CA cert that gets forwarded
    to compute nodes via the cloud-compute interface
    """
    ca_cert = relation_get('ca_cert')
    if not ca_cert:
        return
    log('Writing Keystone CA certificate to %s' % CA_CERT_PATH)
    with open(CA_CERT_PATH, 'wb') as out:
        out.write(b64decode(ca_cert))
    check_call(['update-ca-certificates'])


def create_libvirt_secret(secret_file, secret_uuid, key):
    uri = LIBVIRT_URIS[config('virt-type')]
    cmd = ['virsh', '-c', uri, 'secret-list']
    if secret_uuid in check_output(cmd).decode('UTF-8'):
        old_key = check_output(['virsh', '-c', uri, 'secret-get-value',
                                secret_uuid]).decode('UTF-8')
        old_key = old_key.strip()
        if old_key == key:
            log('Libvirt secret already exists for uuid %s.' % secret_uuid,
                level=DEBUG)
            return
        else:
            log('Libvirt secret changed for uuid %s.' % secret_uuid,
                level=INFO)
    log('Defining new libvirt secret for uuid %s.' % secret_uuid)
    cmd = ['virsh', '-c', uri, 'secret-define', '--file', secret_file]
    check_call(cmd)
    cmd = ['virsh', '-c', uri, 'secret-set-value', '--secret', secret_uuid,
           '--base64', key]
    check_call(cmd)


def _libvirt_network_exec(netname, action):
    """Run action on libvirt network"""
    try:
        cmd = ['virsh', 'net-list', '--all']
        out = check_output(cmd).decode('UTF-8').splitlines()
        if len(out) < 3:
            return

        for line in out[2:]:
            res = re.search(r"^\s+{} ".format(netname), line)
            if res:
                check_call(['virsh', 'net-{}'.format(action), netname])
                return

    except CalledProcessError:
        log("Failed to {} libvirt network '{}'".format(action, netname),
            level=WARNING)
    except OSError as e:
        if e.errno == 2:
            log("virsh is unavailable. Virt Type is '{}'. Not attempting to "
                "{} libvirt network '{}'"
                "".format(config('virt-type'), action, netname), level=DEBUG)
        else:
            raise e


def remove_libvirt_network(netname):
    _libvirt_network_exec(netname, 'destroy')
    _libvirt_network_exec(netname, 'undefine')


def configure_lxd(user='nova'):
    ''' Configure lxd use for nova user '''
    _release = lsb_release()['DISTRIB_CODENAME'].lower()
    if CompareHostReleases(_release) < "vivid":
        raise Exception("LXD is not supported for Ubuntu "
                        "versions less than 15.04 (vivid)")

    configure_subuid(user)
    lxc_list(user)


@retry_on_exception(5, base_delay=2, exc_type=CalledProcessError)
def lxc_list(user):
    cmd = ['sudo', '-u', user, 'lxc', 'list']
    check_call(cmd)


def configure_subuid(user):
    cmd = ['usermod', '-v', '100000-200000', '-w', '100000-200000', user]
    check_call(cmd)


def enable_shell(user):
    cmd = ['usermod', '-s', '/bin/bash', user]
    check_call(cmd)


def disable_shell(user):
    cmd = ['usermod', '-s', '/bin/false', user]
    check_call(cmd)


def fix_path_ownership(path, user='nova'):
    cmd = ['chown', user, path]
    check_call(cmd)


def assert_charm_supports_ipv6():
    """Check whether we are able to support charms ipv6."""
    _release = lsb_release()['DISTRIB_CODENAME'].lower()
    if CompareHostReleases(_release) < "trusty":
        raise Exception("IPv6 is not supported in the charms for Ubuntu "
                        "versions less than Trusty 14.04")


def get_hugepage_number():
    # TODO: defaults to 2M - this should probably be configurable
    #       and support multiple pool sizes - e.g. 2M and 1G.
    # NOTE(jamespage): 2M in bytes
    hugepage_size = 2048 * 1024
    hugepage_config = config('hugepages')
    hugepages = None
    if hugepage_config:
        if hugepage_config.endswith('%'):
            # NOTE(jamespage): return units of virtual_memory is
            #                  bytes
            import psutil
            mem = psutil.virtual_memory()
            hugepage_config_pct = hugepage_config.strip('%')
            hugepage_multiplier = float(hugepage_config_pct) / 100
            hugepages = int((mem.total * hugepage_multiplier) / hugepage_size)
        else:
            hugepages = int(hugepage_config)
    return hugepages


def install_hugepages():
    """ Configure hugepages """
    hugepage_config = config('hugepages')
    if hugepage_config:
        mnt_point = '/run/hugepages/kvm'
        hugepage_support(
            'nova',
            mnt_point=mnt_point,
            group='root',
            nr_hugepages=get_hugepage_number(),
            mount=False,
            set_shmmax=True,
        )
        # Remove hugepages entry if present due to Bug #1518771
        Fstab.remove_by_mountpoint(mnt_point)
        if subprocess.call(['mountpoint', mnt_point]):
            service_restart('qemu-kvm')
        rsync(
            charm_dir() + '/files/qemu-hugefsdir',
            '/etc/init.d/qemu-hugefsdir'
        )
        subprocess.check_call('/etc/init.d/qemu-hugefsdir')
        subprocess.check_call(['update-rc.d', 'qemu-hugefsdir', 'defaults'])


def get_optional_relations():
    """Return a dictionary of optional relations.

    @returns {relation: relation_name}
    """
    optional_interfaces = {}
    if relation_ids('ceph'):
        optional_interfaces['storage-backend'] = ['ceph']
    if relation_ids('neutron-plugin'):
        optional_interfaces['neutron-plugin'] = ['neutron-plugin']
    if config('encrypt'):
        optional_interfaces['vault'] = ['secrets-storage']
    if config('virt-type').lower() == 'ironic':
        optional_interfaces['baremetal'] = ['ironic-api']

    return optional_interfaces


def assess_status(configs):
    """Assess status of current unit
    Decides what the state of the unit should be based on the current
    configuration.
    SIDE EFFECT: calls set_os_workload_status(...) which sets the workload
    status of the unit.
    Also calls status_set(...) directly if paused state isn't complete.
    @param configs: a templating.OSConfigRenderer() object
    @returns None - this function is executed for its side-effect
    """
    if is_unit_paused_set():
        services_to_check = services_to_pause_or_resume()
    else:
        services_to_check = services()

    assess_status_func(configs, services_to_check)()
    os_application_version_set(VERSION_PACKAGE)


def check_optional_config_and_relations(configs):
    """Validate optional configuration and relations when present.

    This function is called from assess_status/set_os_workload_status as the
    charm_func and needs to return either None, None if there is no problem or
    the status, message if there is a problem.

    :param configs: an OSConfigRender() instance.
    :return 2-tuple: (string, string) = (status, message)
    """
    if relation_ids('ceph'):
        # Check that provided Ceph BlueStoe configuration is valid.
        try:
            bluestore_compression = context.CephBlueStoreCompressionContext()
            bluestore_compression.validate()
        except AttributeError:
            # The charm does late installation of the `ceph-common` package and
            # the class initializer above will throw an exception until it is.
            pass
        except ValueError as e:
            return ('blocked', 'Invalid configuration: {}'.format(str(e)))

    # return 'unknown' as the lowest priority to not clobber an existing
    # status.
    return "unknown", ""


def assess_status_func(configs, services_=None):
    """Helper function to create the function that will assess_status() for
    the unit.
    Uses charmhelpers.contrib.openstack.utils.make_assess_status_func() to
    create the appropriate status function and then returns it.
    Used directly by assess_status() and also for pausing and resuming
    the unit.

    NOTE(ajkavanagh) ports are not checked due to race hazards with services
    that don't behave synchronously w.r.t their service scripts.  e.g.
    apache2.
    @param configs: a templating.OSConfigRenderer() object
    @return f() -> None : a function that assesses the unit's workload status
    """
    required_interfaces = REQUIRED_INTERFACES.copy()

    optional_relations = get_optional_relations()
    if 'vault' in optional_relations:
        # skip check if hvac dependency not installed yet
        if not vaultlocker_installed():
            log("Vault dependencies not yet met so removing from status check")
            del optional_relations['vault']
        else:
            log("Vault dependencies met so including in status check")

    required_interfaces.update(optional_relations)
    return make_assess_status_func(
        configs, required_interfaces,
        charm_func=check_optional_config_and_relations,
        services=services_ or services(), ports=None)


def pause_unit_helper(configs):
    """Helper function to pause a unit, and then call assess_status(...) in
    effect, so that the status is correctly updated.
    Uses charmhelpers.contrib.openstack.utils.pause_unit() to do the work.
    @param configs: a templating.OSConfigRenderer() object
    @returns None - this function is executed for its side-effect
    """
    _pause_resume_helper(pause_unit, configs)


def resume_unit_helper(configs):
    """Helper function to resume a unit, and then call assess_status(...) in
    effect, so that the status is correctly updated.
    Uses charmhelpers.contrib.openstack.utils.resume_unit() to do the work.
    @param configs: a templating.OSConfigRenderer() object
    @returns None - this function is executed for its side-effect
    """
    _pause_resume_helper(resume_unit, configs)


def services_to_pause_or_resume():
    if "post-series-upgrade" in hook_name():
        return services()
    else:
        # WARNING(lourot): the list ordering is important. See services() for
        # more details.
        return [service for service in services()
                if service != libvirt_daemon()]


def _pause_resume_helper(f, configs):
    """Helper function that uses the make_assess_status_func(...) from
    charmhelpers.contrib.openstack.utils to create an assess_status(...)
    function that can be used with the pause/resume of the unit
    @param f: the function to be used with the assess_status(...) function
    @returns None - this function is executed for its side-effect
    """
    # TODO(ajkavanagh) - ports= has been left off because of the race hazard
    # that exists due to service_start()

    f(assess_status_func(configs, services_to_pause_or_resume()),
      services=services_to_pause_or_resume(),
      ports=None)


def determine_block_device():
    """Determine the block device to use for ephemeral storage

    :returns: Block device to use for storage
    :rtype: str or None if not configured"""
    config_dev = config('ephemeral-device')

    if config_dev and os.path.exists(config_dev):
        return config_dev

    storage_ids = storage_list('ephemeral-device')
    storage_devs = [storage_get('location', s) for s in storage_ids]

    if storage_devs:
        return storage_devs[0]

    return None


def configure_local_ephemeral_storage():
    """Configure local block device for use as ephemeral instance storage"""
    # Preflight check vault relation if encryption is enabled

    encrypt = config('encrypt')
    if encrypt:
        if not vaultlocker_installed():
            log("Encryption requested but vaultlocker not yet installed",
                level=DEBUG)
            return

        vault_kv = vaultlocker.VaultKVContext(
            secret_backend=vaultlocker.VAULTLOCKER_BACKEND
        )
        context = vault_kv()
        if vault_kv.complete:
            # NOTE: only write vaultlocker configuration once relation is
            #       complete otherwise we run the chance of an empty
            #       configuration file being installed on a machine with other
            #       vaultlocker based services
            vaultlocker.write_vaultlocker_conf(context, priority=80)
        else:
            log("Encryption requested but vault relation not complete",
                level=DEBUG)
            return

    mountpoint = config('instances-path') or '/var/lib/nova/instances'

    db = kv()
    storage_configured = db.get('storage-configured', False)
    if storage_configured:
        log("Ephemeral storage already configured, skipping",
            level=DEBUG)
        # NOTE(jamespage):
        # Install mountpoint override to ensure that upgrades
        # to the charm version which supports this change
        # also start exhibiting the correct behaviour
        install_mount_override(mountpoint)
        return

    dev = determine_block_device()

    if not dev:
        log('No block device configuration found, skipping',
            level=DEBUG)
        return

    if not is_block_device(dev):
        log("Device '{}' is not a block device, "
            "unable to configure storage".format(dev),
            level=DEBUG)
        return

    # NOTE: this deals with a dm-crypt'ed block device already in
    #       use
    if is_device_mounted(dev):
        log("Device '{}' is already mounted, "
            "unable to configure storage".format(dev),
            level=DEBUG)
        return

    options = None
    if encrypt:
        dev_uuid = str(uuid.uuid4())
        check_call(['vaultlocker', 'encrypt',
                    '--uuid', dev_uuid,
                    dev])
        dev = '/dev/mapper/crypt-{}'.format(dev_uuid)
        options = ','.join([
            "defaults",
            "nofail",
            ("x-systemd.requires="
             "vaultlocker-decrypt@{uuid}.service".format(uuid=dev_uuid)),
            "comment=vaultlocker",
        ])

    # If not cleaned and in use, mkfs should fail.
    mkfs_xfs(dev, force=True)

    filesystem = "xfs"
    mount(dev, mountpoint, filesystem=filesystem)
    fstab_add(dev, mountpoint, filesystem, options=options)
    install_mount_override(mountpoint)

    check_call(['chown', '-R', 'nova:nova', mountpoint])
    check_call(['chmod', '-R', '0755', mountpoint])

    # NOTE: record preparation of device - this ensures that ephemeral
    #       storage is never reconfigured by mistake, losing instance disks
    db.set('storage-configured', True)
    db.flush()


def install_mount_override(mountpoint):
    """Install override for nova-compute for configured mountpoint"""
    render(
        MOUNT_DEPENDENCY_OVERRIDE,
        os.path.join(NOVA_COMPUTE_OVERRIDE_DIR, MOUNT_DEPENDENCY_OVERRIDE),
        {'mount_point': mountpoint.replace('/', '-')[1:]},
        perms=0o644,
    )


def get_availability_zone():
    use_juju_az = config('customize-failure-domain')
    juju_az = os.environ.get('JUJU_AVAILABILITY_ZONE')
    return (juju_az if use_juju_az and juju_az
            else config('default-availability-zone'))
