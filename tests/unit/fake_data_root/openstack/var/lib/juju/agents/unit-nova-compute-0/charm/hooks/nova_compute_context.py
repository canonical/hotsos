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

import json
import os
import platform
import shutil
import uuid

from charmhelpers.core.unitdata import kv
from charmhelpers.contrib.openstack import context

from charmhelpers.core.host import (
    lsb_release,
    CompareHostReleases,
)
from charmhelpers.core.strutils import (
    bool_from_string,
)
from charmhelpers.fetch import apt_install, filter_installed_packages
from charmhelpers.core.hookenv import (
    config,
    log,
    relation_get,
    relation_ids,
    related_units,
    service_name,
    ERROR,
    INFO,
)
from charmhelpers.contrib.openstack.utils import (
    get_os_version_package,
    get_os_version_codename,
    os_release,
    CompareOpenStackReleases,
)
from charmhelpers.contrib.openstack.ip import (
    INTERNAL,
    resolve_address,
)
from charmhelpers.contrib.network.ip import (
    get_relation_ip,
)

# This is just a label and it must be consistent across
# nova-compute nodes to support live migration.
CEPH_SECRET_UUID = '514c9fca-8cbe-11e2-9c52-3bc8c7819472'

OVS_BRIDGE = 'br-int'

CEPH_CONF = '/etc/ceph/ceph.conf'
CHARM_CEPH_CONF = '/var/lib/charm/{}/ceph.conf'

NOVA_API_AA_PROFILE = 'usr.bin.nova-api'
NOVA_COMPUTE_AA_PROFILE = 'usr.bin.nova-compute'
NOVA_NETWORK_AA_PROFILE = 'usr.bin.nova-network'


def ceph_config_file():
    return CHARM_CEPH_CONF.format(service_name())


def _save_flag_file(path, data):
    '''
    Saves local state about plugin or manager to specified file.
    '''
    # Wonder if we can move away from this now?
    if data is None:
        return
    with open(path, 'wt') as out:
        out.write(data)
    os.chmod(path, 0o640)
    shutil.chown(path, 'root', 'nova')


# compatibility functions to help with quantum -> neutron transition
def _network_manager():
    from nova_compute_utils import network_manager as manager
    return manager()


def _get_availability_zone():
    from nova_compute_utils import get_availability_zone as get_az
    return get_az()


def _neutron_security_groups():
    '''
    Inspects current cloud-compute relation and determine if nova-c-c has
    instructed us to use neutron security groups.
    '''
    for rid in relation_ids('cloud-compute'):
        for unit in related_units(rid):
            groups = [
                relation_get('neutron_security_groups',
                             rid=rid, unit=unit),
                relation_get('quantum_security_groups',
                             rid=rid, unit=unit)
            ]
            if ('yes' in groups or 'Yes' in groups):
                return True
    return False


def _neutron_plugin():
    from nova_compute_utils import neutron_plugin
    return neutron_plugin()


def _neutron_url(rid, unit):
    # supports legacy relation settings.
    return (relation_get('neutron_url', rid=rid, unit=unit) or
            relation_get('quantum_url', rid=rid, unit=unit))


def nova_metadata_requirement():
    enable = False
    secret = None
    for rid in relation_ids('neutron-plugin'):
        for unit in related_units(rid):
            rdata = relation_get(rid=rid, unit=unit)
            if 'metadata-shared-secret' in rdata:
                secret = rdata['metadata-shared-secret']
                enable = True
            if bool_from_string(rdata.get('enable-metadata', 'False')):
                enable = True
    return enable, secret


class LxdContext(context.OSContextGenerator):
    def __call__(self):
        lxd_context = {
            'storage_pool': None
        }
        for rid in relation_ids('lxd'):
            for unit in related_units(rid):
                rel = {'rid': rid, 'unit': unit}

                lxd_context = {
                    'storage_pool': relation_get(
                        'pool', **rel)
                }
        return lxd_context


class NovaComputeLibvirtContext(context.OSContextGenerator):

    '''
    Determines various libvirt and nova options depending on live migration
    configuration.
    '''
    interfaces = []

    def __call__(self):
        # distro defaults
        ctxt = {
            # /etc/libvirt/libvirtd.conf (
            'listen_tls': 0
        }
        cmp_distro_codename = CompareHostReleases(
            lsb_release()['DISTRIB_CODENAME'].lower())
        cmp_os_release = CompareOpenStackReleases(os_release('nova-common'))

        # NOTE(jamespage): deal with switch to systemd
        if cmp_distro_codename < "wily":
            ctxt['libvirtd_opts'] = '-d'
        else:
            ctxt['libvirtd_opts'] = ''

        # NOTE(jamespage): deal with alignment with Debian in
        #                  Ubuntu yakkety and beyond.
        if cmp_distro_codename >= 'yakkety' or cmp_os_release >= 'ocata':
            ctxt['libvirt_user'] = 'libvirt'
        else:
            ctxt['libvirt_user'] = 'libvirtd'

        # get the processor architecture to use in the nova.conf template
        ctxt['arch'] = platform.machine()

        # enable tcp listening if configured for live migration.
        if config('enable-live-migration'):
            ctxt['libvirtd_opts'] += ' -l'

        if config('enable-live-migration') and \
                config('migration-auth-type') in ['none', 'None', 'ssh']:
            ctxt['listen_tls'] = 0

        if config('enable-live-migration') and \
                config('migration-auth-type') == 'ssh':
            migration_address = get_relation_ip(
                'migration', cidr_network=config('libvirt-migration-network'))

            if cmp_os_release >= 'ocata':
                ctxt['live_migration_scheme'] = config('migration-auth-type')
                ctxt['live_migration_inbound_addr'] = migration_address
            else:
                ctxt['live_migration_uri'] = 'qemu+ssh://%s/system'

        if config('enable-live-migration'):
            ctxt['live_migration_completion_timeout'] = \
                config('live-migration-completion-timeout')
            ctxt['live_migration_downtime'] = \
                config('live-migration-downtime')
            ctxt['live_migration_downtime_steps'] = \
                config('live-migration-downtime-steps')
            ctxt['live_migration_downtime_delay'] = \
                config('live-migration-downtime-delay')
            ctxt['live_migration_permit_post_copy'] = \
                config('live-migration-permit-post-copy')
            ctxt['live_migration_permit_auto_converge'] = \
                config('live-migration-permit-auto-converge')

        if config('instances-path') is not None:
            ctxt['instances_path'] = config('instances-path')

        if config('disk-cachemodes'):
            ctxt['disk_cachemodes'] = config('disk-cachemodes')

        if config('use-multipath'):
            ctxt['use_multipath'] = config('use-multipath')

        if config('default-ephemeral-format'):
            ctxt['default_ephemeral_format'] = \
                config('default-ephemeral-format')

        if config('cpu-mode'):
            ctxt['cpu_mode'] = config('cpu-mode')
        elif ctxt['arch'] in ('ppc64el', 'ppc64le', 'aarch64'):
            ctxt['cpu_mode'] = 'host-passthrough'
        elif ctxt['arch'] == 's390x':
            ctxt['cpu_mode'] = 'none'

        if config('cpu-model'):
            ctxt['cpu_model'] = config('cpu-model')

        if config('cpu-model-extra-flags'):
            ctxt['cpu_model_extra_flags'] = ', '.join(
                config('cpu-model-extra-flags').split(' '))

        if config('hugepages'):
            ctxt['hugepages'] = True
            ctxt['kvm_hugepages'] = 1
        else:
            ctxt['kvm_hugepages'] = 0

        if config('ksm') in ("1", "0",):
            ctxt['ksm'] = config('ksm')
        else:
            if cmp_os_release < 'kilo':
                log("KSM set to 1 by default on openstack releases < kilo",
                    level=INFO)
                ctxt['ksm'] = "1"
            else:
                ctxt['ksm'] = "AUTO"

        if config('reserved-huge-pages'):
            # To bypass juju limitation with list of strings, we
            # consider separate the option's values per semicolons.
            ctxt['reserved_huge_pages'] = (
                [o.strip() for o in config('reserved-huge-pages').split(";")])

        if config('pci-passthrough-whitelist'):
            ctxt['pci_passthrough_whitelist'] = \
                config('pci-passthrough-whitelist')

        if config('pci-alias'):
            aliases = json.loads(config('pci-alias'))
            # Behavior previous to queens is maintained as it was
            if isinstance(aliases, list) and cmp_os_release >= 'queens':
                ctxt['pci_aliases'] = [json.dumps(x, sort_keys=True)
                                       for x in aliases]
            else:
                ctxt['pci_alias'] = json.dumps(aliases, sort_keys=True)

        if config('cpu-dedicated-set'):
            ctxt['cpu_dedicated_set'] = config('cpu-dedicated-set')
        elif config('vcpu-pin-set'):
            ctxt['vcpu_pin_set'] = config('vcpu-pin-set')

        if config('cpu-shared-set'):
            ctxt['cpu_shared_set'] = config('cpu-shared-set')

        if config('virtio-net-tx-queue-size'):
            ctxt['virtio_net_tx_queue_size'] = (
                config('virtio-net-tx-queue-size'))
        if config('virtio-net-rx-queue-size'):
            ctxt['virtio_net_rx_queue_size'] = (
                config('virtio-net-rx-queue-size'))

        if config('num-pcie-ports'):
            ctxt['num_pcie_ports'] = config('num-pcie-ports')

        ctxt['reserved_host_memory'] = config('reserved-host-memory')
        ctxt['reserved_host_disk'] = config('reserved-host-disk')

        db = kv()
        if db.get('host_uuid'):
            ctxt['host_uuid'] = db.get('host_uuid')
        else:
            host_uuid = str(uuid.uuid4())
            db.set('host_uuid', host_uuid)
            db.flush()
            ctxt['host_uuid'] = host_uuid

        if config('libvirt-image-backend'):
            ctxt['libvirt_images_type'] = config('libvirt-image-backend')

        ctxt['force_raw_images'] = config('force-raw-images')
        ctxt['inject_password'] = config('inject-password')
        # if allow the injection of an admin password it depends
        # on value greater or equal to -1 for inject_partition
        # -2 means disable the injection of data
        ctxt['inject_partition'] = -1 if config('inject-password') else -2

        return ctxt


class NovaComputeLibvirtOverrideContext(context.OSContextGenerator):
    """Provides overrides to the libvirt-bin service"""
    interfaces = []

    def __call__(self):
        ctxt = {}
        ctxt['overrides'] = "limit nofile 65535 65535"
        return ctxt


class NovaComputeVirtContext(context.OSContextGenerator):
    interfaces = []

    def __call__(self):
        ctxt = {}
        _release = lsb_release()['DISTRIB_CODENAME'].lower()
        if CompareHostReleases(_release) >= "yakkety":
            ctxt['virt_type'] = config('virt-type')
            ctxt['enable_live_migration'] = config('enable-live-migration')
        ctxt['resume_guests_state_on_host_boot'] =\
            config('resume-guests-state-on-host-boot')
        return ctxt


class IronicAPIContext(context.OSContextGenerator):
    interfaces = ["ironic-api"]

    def __call__(self):
        ctxt = {}
        for rid in relation_ids('ironic-api'):
            for unit in related_units(rid):
                is_ready = relation_get(
                    'ironic-api-ready', rid=rid, unit=unit)
                if is_ready:
                    ctxt["ironic_api_ready"] = is_ready
                    return ctxt
        return ctxt


def assert_libvirt_rbd_imagebackend_allowed():
    os_rel = "Juno"
    os_ver = get_os_version_package('nova-common')
    if float(os_ver) < float(get_os_version_codename(os_rel.lower())):
        msg = ("Libvirt RBD imagebackend only supported for openstack >= %s" %
               os_rel)
        raise Exception(msg)

    return True


class NovaComputeCephContext(context.CephContext):

    def __call__(self):
        ctxt = super(NovaComputeCephContext, self).__call__()
        if not ctxt:
            return {}
        svc = service_name()
        # secret.xml
        ctxt['ceph_secret_uuid'] = CEPH_SECRET_UUID
        # nova.conf
        ctxt['service_name'] = svc
        ctxt['rbd_user'] = svc
        ctxt['rbd_secret_uuid'] = CEPH_SECRET_UUID

        if config('pool-type') == 'erasure-coded':
            ctxt['rbd_pool'] = (
                config('ec-rbd-metadata-pool') or
                "{}-metadata".format(config('rbd-pool'))
            )
        else:
            ctxt['rbd_pool'] = config('rbd-pool')

        if (config('libvirt-image-backend') == 'rbd' and
                assert_libvirt_rbd_imagebackend_allowed()):
            ctxt['libvirt_rbd_images_ceph_conf'] = ceph_config_file()

        rbd_cache = config('rbd-client-cache') or ""
        if rbd_cache.lower() == "enabled":
            # We use write-though only to be safe for migration
            ctxt['rbd_client_cache_settings'] = \
                {'rbd cache': 'true',
                 'rbd cache size': '67108864',
                 'rbd cache max dirty': '0',
                 'rbd cache writethrough until flush': 'true',
                 'admin socket': '/var/run/ceph/rbd-client-$pid.asok'}

            asok_path = '/var/run/ceph/'
            if not os.path.isdir(asok_path):
                os.mkdir(asok_path)
                shutil.chown(asok_path, group='kvm')

        elif rbd_cache.lower() == "disabled":
            ctxt['rbd_client_cache_settings'] = {'rbd cache': 'false'}

        return ctxt


class SerialConsoleContext(context.OSContextGenerator):

    @property
    def enable_serial_console(self):
        for rid in relation_ids('cloud-compute'):
            for unit in related_units(rid):
                _enable_sc = relation_get('enable_serial_console', rid=rid,
                                          unit=unit)
                if _enable_sc and bool_from_string(_enable_sc):
                    return 'true'
        return 'false'

    @property
    def serial_console_base_url(self):
        for rid in relation_ids('cloud-compute'):
            for unit in related_units(rid):
                base_url = relation_get('serial_console_base_url',
                                        rid=rid, unit=unit)
                if base_url is not None:
                    return base_url
        return 'ws://127.0.0.1:6083/'

    def __call__(self):
        return {
            'enable_serial_console': self.enable_serial_console,
            'serial_console_base_url': self.serial_console_base_url,
        }


class CloudComputeVendorJSONContext(context.OSContextGenerator):
    """Receives vendor_data.json from nova cloud controller node."""

    interfaces = ['cloud-compute']

    @property
    def vendor_json(self):
        """
        Returns the json string to be written in vendor_data.json file,
        received from nova-cloud-controller charm through relation attribute
        vendor_json.
        """
        for rid in relation_ids('cloud-compute'):
            for unit in related_units(rid):
                vendor_data_string = relation_get(
                    'vendor_json', rid=rid, unit=unit)
                if vendor_data_string:
                    return vendor_data_string

    def __call__(self):
        """
        Returns a dict in which the value of vendor_data_json is the json
        string to be written in vendor_data.json file.
        """
        ctxt = {'vendor_data_json': '{}'}
        vendor_data = self.vendor_json
        if vendor_data:
            ctxt['vendor_data_json'] = vendor_data
        return ctxt


class CloudComputeContext(context.OSContextGenerator):
    '''
    Generates main context for writing nova.conf and quantum.conf templates
    from a cloud-compute relation changed hook.  Mainly used for determinig
    correct network and volume service configuration on the compute node,
    as advertised by the cloud-controller.

    Note: individual quantum plugin contexts are handled elsewhere.
    '''
    interfaces = ['cloud-compute']

    def _ensure_packages(self, packages):
        '''Install but do not upgrade required packages'''
        required = filter_installed_packages(packages)
        if required:
            apt_install(required, fatal=True)

    @property
    def network_manager(self):
        return _network_manager()

    @property
    def volume_service(self):
        volume_service = None
        for rid in relation_ids('cloud-compute'):
            for unit in related_units(rid):
                volume_service = relation_get('volume_service',
                                              rid=rid, unit=unit)
        return volume_service

    @property
    def cross_az_attach(self):
        # Default to True as that is the nova default
        cross_az_attach = True
        for rid in relation_ids('cloud-compute'):
            for unit in related_units(rid):
                setting = relation_get('cross_az_attach', rid=rid, unit=unit)
                if setting is not None:
                    cross_az_attach = setting
        return cross_az_attach

    @property
    def region(self):
        region = None
        for rid in relation_ids('cloud-compute'):
            for unit in related_units(rid):
                region = relation_get('region', rid=rid, unit=unit)
        return region

    @property
    def vendor_data(self):
        """
        Returns vendor metadata related parameters to be written in
        nova.conf, received from nova-cloud-controller charm through relation
        attribute vendor_data.
        """
        vendor_data_json = {}
        for rid in relation_ids('cloud-compute'):
            for unit in related_units(rid):
                vendor_data_string = relation_get(
                    'vendor_data', rid=rid, unit=unit)
                if vendor_data_string:
                    vendor_data_json = json.loads(vendor_data_string)
        return vendor_data_json

    def vendor_data_context(self):
        vdata_ctxt = {}
        vendor_data_json = self.vendor_data
        if vendor_data_json:
            # NOTE(ganso): avoid returning any extra keys to context
            if vendor_data_json.get('vendor_data'):
                vdata_ctxt['vendor_data'] = vendor_data_json['vendor_data']
            if vendor_data_json.get('vendor_data_url'):
                vdata_ctxt['vendor_data_url'] = vendor_data_json[
                    'vendor_data_url']
            if vendor_data_json.get('vendordata_providers'):
                vdata_ctxt['vendordata_providers'] = vendor_data_json[
                    'vendordata_providers']

        return vdata_ctxt

    def flat_dhcp_context(self):
        ec2_host = None
        for rid in relation_ids('cloud-compute'):
            for unit in related_units(rid):
                ec2_host = relation_get('ec2_host', rid=rid, unit=unit)

        if not ec2_host:
            return {}

        if config('multi-host').lower() == 'yes':
            cmp_os_release = CompareOpenStackReleases(
                os_release('nova-common'))
            if cmp_os_release <= 'train':
                # nova-network only available until ussuri
                self._ensure_packages(['nova-api', 'nova-network'])
            else:
                self._ensure_packages(['nova-api'])

        return {
            'flat_interface': config('flat-interface'),
            'ec2_dmz_host': ec2_host,
        }

    def neutron_context(self):
        # generate config context for neutron or quantum. these get converted
        # directly into flags in nova.conf
        # NOTE: Its up to release templates to set correct driver
        neutron_ctxt = {'neutron_url': None}
        for rid in relation_ids('cloud-compute'):
            for unit in related_units(rid):
                rel = {'rid': rid, 'unit': unit}

                url = _neutron_url(**rel)
                if not url:
                    # only bother with units that have a neutron url set.
                    continue

                neutron_ctxt = {
                    'auth_protocol': relation_get(
                        'auth_protocol', **rel) or 'http',
                    'service_protocol': relation_get(
                        'service_protocol', **rel) or 'http',
                    'service_port': relation_get(
                        'service_port', **rel) or '5000',
                    'neutron_auth_strategy': 'keystone',
                    'keystone_host': relation_get(
                        'auth_host', **rel),
                    'auth_port': relation_get(
                        'auth_port', **rel),
                    'neutron_admin_tenant_name': relation_get(
                        'service_tenant_name', **rel),
                    'neutron_admin_username': relation_get(
                        'service_username', **rel),
                    'neutron_admin_password': relation_get(
                        'service_password', **rel),
                    'api_version': relation_get(
                        'api_version', **rel) or '2.0',
                    'neutron_plugin': _neutron_plugin(),
                    'neutron_url': url,
                }
                # DNS domain is optional
                dns_domain = relation_get('dns_domain', **rel)
                if dns_domain:
                    neutron_ctxt['dns_domain'] = dns_domain
                admin_domain = relation_get('admin_domain_name', **rel)
                if admin_domain:
                    neutron_ctxt['neutron_admin_domain_name'] = admin_domain

        missing = [k for k, v in neutron_ctxt.items() if v in ['', None]]
        if missing:
            log('Missing required relation settings for Quantum: ' +
                ' '.join(missing))
            return {}

        neutron_ctxt['neutron_security_groups'] = _neutron_security_groups()

        ks_url = '%s://%s:%s/v%s' % (neutron_ctxt['auth_protocol'],
                                     neutron_ctxt['keystone_host'],
                                     neutron_ctxt['auth_port'],
                                     neutron_ctxt['api_version'])
        neutron_ctxt['neutron_admin_auth_url'] = ks_url

        if config('neutron-physnets'):
            physnets = config('neutron-physnets').split(';')
            neutron_ctxt['neutron_physnets'] =\
                dict(item.split(":") for item in physnets)
        if config('neutron-tunnel'):
            neutron_ctxt['neutron_tunnel'] = config('neutron-tunnel')

        return neutron_ctxt

    def neutron_context_no_auth_data(self):
        """If the charm has a cloud-credentials relation then a subset
        of data is needed to complete this context."""
        neutron_ctxt = {'neutron_url': None}
        for rid in relation_ids('cloud-compute'):
            for unit in related_units(rid):
                rel = {'rid': rid, 'unit': unit}

                url = _neutron_url(**rel)
                if not url:
                    # only bother with units that have a neutron url set.
                    continue

                neutron_ctxt = {
                    'neutron_auth_strategy': 'keystone',
                    'neutron_plugin': _neutron_plugin(),
                    'neutron_url': url,
                }

        return neutron_ctxt

    def volume_context(self):
        # provide basic validation that the volume manager is supported on the
        # given openstack release (nova-volume is only supported for E and F)
        # it is up to release templates to set the correct volume driver.

        if not self.volume_service:
            return {}

        # ensure volume service is supported on specific openstack release.
        if self.volume_service == 'cinder':
            return 'cinder'
        else:
            e = ('Invalid volume service received via cloud-compute: %s' %
                 self.volume_service)
            log(e, level=ERROR)
            raise context.OSContextError(e)

    def network_manager_context(self):
        ctxt = {}
        if self.network_manager == 'flatdhcpmanager':
            ctxt = self.flat_dhcp_context()
        elif self.network_manager == 'neutron':
            ctxt = self.neutron_context()

            # If charm has a cloud-credentials relation then auth data is not
            # needed.
            if relation_ids('cloud-credentials') and not ctxt:
                ctxt = self.neutron_context_no_auth_data()
        _save_flag_file(path='/etc/nova/nm.conf', data=self.network_manager)

        log('Generated config context for %s network manager.' %
            self.network_manager)
        return ctxt

    def restart_trigger(self):
        rt = None
        for rid in relation_ids('cloud-compute'):
            for unit in related_units(rid):
                rt = relation_get('restart_trigger', rid=rid, unit=unit)
                if rt:
                    return rt

    def __call__(self):
        rids = relation_ids('cloud-compute')
        if not rids:
            return {}

        ctxt = {}

        net_manager = self.network_manager_context()

        if net_manager:
            if net_manager.get('neutron_admin_password'):
                ctxt['network_manager'] = self.network_manager
                ctxt['network_manager_config'] = net_manager
                # This is duplicating information in the context to enable
                # common keystone fragment to be used in template
                ctxt['service_protocol'] = net_manager.get('service_protocol')
                ctxt['service_host'] = net_manager.get('keystone_host')
                ctxt['service_port'] = net_manager.get('service_port')
                ctxt['admin_tenant_name'] = net_manager.get(
                    'neutron_admin_tenant_name')
                ctxt['admin_user'] = net_manager.get('neutron_admin_username')
                ctxt['admin_password'] = net_manager.get(
                    'neutron_admin_password')
                ctxt['auth_protocol'] = net_manager.get('auth_protocol')
                ctxt['auth_host'] = net_manager.get('keystone_host')
                ctxt['auth_port'] = net_manager.get('auth_port')
                ctxt['api_version'] = net_manager.get('api_version')
                if net_manager.get('dns_domain'):
                    ctxt['dns_domain'] = net_manager.get('dns_domain')
                if net_manager.get('neutron_admin_domain_name'):
                    ctxt['admin_domain_name'] = net_manager.get(
                        'neutron_admin_domain_name')
            else:
                ctxt['network_manager'] = self.network_manager
                ctxt['network_manager_config'] = net_manager

        net_dev_mtu = config('network-device-mtu')
        if net_dev_mtu:
            ctxt['network_device_mtu'] = net_dev_mtu

        vol_service = self.volume_context()
        if vol_service:
            ctxt['volume_service'] = vol_service
            ctxt['cross_az_attach'] = self.cross_az_attach

        if self.restart_trigger():
            ctxt['restart_trigger'] = self.restart_trigger()

        region = self.region
        if region:
            ctxt['region'] = region

        ctxt.update(self.vendor_data_context())

        if self.context_complete(ctxt):
            return ctxt

        return {}


class InstanceConsoleContext(context.OSContextGenerator):
    interfaces = []

    def get_console_info(self, proto, **kwargs):
        console_settings = {
            proto + '_proxy_address':
            relation_get('console_proxy_%s_address' % (proto), **kwargs),
            proto + '_proxy_host':
            relation_get('console_proxy_%s_host' % (proto), **kwargs),
            proto + '_proxy_port':
            relation_get('console_proxy_%s_port' % (proto), **kwargs),
        }
        return console_settings

    def __call__(self):
        ctxt = {}

        for rid in relation_ids('cloud-compute'):
            for unit in related_units(rid):
                rel = {'rid': rid, 'unit': unit}
                proto = relation_get('console_access_protocol', **rel)
                if not proto:
                    # only bother with units that have a proto set.
                    continue
                ctxt['console_keymap'] = relation_get('console_keymap', **rel)
                ctxt['console_access_protocol'] = proto
                ctxt['spice_agent_enabled'] = relation_get(
                    'spice_agent_enabled', **rel)
                ctxt['console_vnc_type'] = True if 'vnc' in proto else False
                if proto == 'vnc':
                    ctxt = dict(ctxt, **self.get_console_info('xvpvnc', **rel))
                    ctxt = dict(ctxt, **self.get_console_info('novnc', **rel))
                else:
                    ctxt = dict(ctxt, **self.get_console_info(proto, **rel))
                break
        ctxt['console_listen_addr'] = resolve_address(endpoint_type=INTERNAL)
        return ctxt


class MetadataServiceContext(context.OSContextGenerator):

    def __call__(self):
        ctxt = {}
        _, secret = nova_metadata_requirement()
        if secret:
            ctxt['metadata_shared_secret'] = secret
        return ctxt


class NeutronComputeContext(context.OSContextGenerator):
    interfaces = []

    @property
    def plugin(self):
        return _neutron_plugin()

    @property
    def network_manager(self):
        return _network_manager()

    @property
    def neutron_security_groups(self):
        return _neutron_security_groups()

    def __call__(self):
        if self.plugin:
            return {
                'network_manager': self.network_manager,
                'neutron_plugin': self.plugin,
                'neutron_security_groups': self.neutron_security_groups
            }
        return {}


class HostIPContext(context.OSContextGenerator):
    def __call__(self):
        ctxt = {}
        # Use the address used in the cloud-compute relation in templates for
        # this host
        host_ip = get_relation_ip('cloud-compute',
                                  cidr_network=config('os-internal-network'))

        if host_ip:
            # NOTE: do not format this even for ipv6 (see bug 1499656)
            ctxt['host_ip'] = host_ip

        return ctxt


class NovaAPIAppArmorContext(context.AppArmorContext):

    def __init__(self):
        super(NovaAPIAppArmorContext, self).__init__()
        self.aa_profile = NOVA_API_AA_PROFILE

    def __call__(self):
        super(NovaAPIAppArmorContext, self).__call__()
        if not self.ctxt:
            return self.ctxt
        self._ctxt.update({'aa_profile': self.aa_profile})
        return self.ctxt


class NovaComputeAppArmorContext(context.AppArmorContext):

    def __init__(self):
        super(NovaComputeAppArmorContext, self).__init__()
        self.aa_profile = NOVA_COMPUTE_AA_PROFILE

    def __call__(self):
        super(NovaComputeAppArmorContext, self).__call__()
        if not self.ctxt:
            return self.ctxt
        self._ctxt.update({'virt_type': config('virt-type')})
        self._ctxt.update({'aa_profile': self.aa_profile})
        return self.ctxt


class NovaNetworkAppArmorContext(context.AppArmorContext):

    def __init__(self):
        super(NovaNetworkAppArmorContext, self).__init__()
        self.aa_profile = NOVA_NETWORK_AA_PROFILE

    def __call__(self):
        super(NovaNetworkAppArmorContext, self).__call__()
        if not self.ctxt:
            return self.ctxt
        self._ctxt.update({'aa_profile': self.aa_profile})
        return self.ctxt


class NovaComputeAvailabilityZoneContext(context.OSContextGenerator):

    def __call__(self):
        ctxt = {}
        ctxt['default_availability_zone'] = _get_availability_zone()
        return ctxt


class NeutronPluginSubordinateConfigContext(context.SubordinateConfigContext):

    def context_complete(self, ctxt):
        """Allow sections to be empty

        It is ok for this context to be empty as the neutron-plugin may not
        require the nova-compute charm to add anything to its config. So
        override the SubordinateConfigContext behaviour of marking the context
        incomplete if no config data has been sent.

        :param ctxt: The current context members
        :type ctxt: Dict[str, ANY]
        :returns: True if the context is complete
        :rtype: bool
        """
        return 'sections' in ctxt.keys()


class NovaComputePlacementContext(context.OSContextGenerator):

    def __call__(self):
        ctxt = {}
        cmp_os_release = CompareOpenStackReleases(os_release('nova-common'))

        ctxt['initial_cpu_allocation_ratio'] =\
            config('initial-cpu-allocation-ratio')
        ctxt['initial_ram_allocation_ratio'] =\
            config('initial-ram-allocation-ratio')
        ctxt['initial_disk_allocation_ratio'] =\
            config('initial-disk-allocation-ratio')

        ctxt['cpu_allocation_ratio'] = config('cpu-allocation-ratio')
        ctxt['ram_allocation_ratio'] = config('ram-allocation-ratio')
        ctxt['disk_allocation_ratio'] = config('disk-allocation-ratio')

        if cmp_os_release >= 'stein':
            for ratio_config in ['initial_cpu_allocation_ratio',
                                 'initial_ram_allocation_ratio',
                                 'initial_disk_allocation_ratio']:
                if ctxt[ratio_config] is None:
                    for rid in relation_ids('cloud-compute'):
                        for unit in related_units(rid):
                            rel = {'rid': rid, 'unit': unit}
                            ctxt[ratio_config] = relation_get(ratio_config,
                                                              **rel)
        else:
            for ratio_config in ['cpu_allocation_ratio',
                                 'ram_allocation_ratio',
                                 'disk_allocation_ratio']:
                if ctxt[ratio_config] is None:
                    for rid in relation_ids('cloud-compute'):
                        for unit in related_units(rid):
                            rel = {'rid': rid, 'unit': unit}
                            ctxt[ratio_config] = relation_get(ratio_config,
                                                              **rel)
        return ctxt
