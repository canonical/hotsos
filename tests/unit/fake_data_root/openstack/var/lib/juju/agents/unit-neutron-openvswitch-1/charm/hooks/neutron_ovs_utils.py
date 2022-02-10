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

import json
import os
from itertools import chain
import shutil
import subprocess

from charmhelpers.contrib.openstack.neutron import neutron_plugin_attribute
from copy import deepcopy

from charmhelpers.contrib.openstack import context, templating
from charmhelpers.contrib.openstack.utils import (
    pause_unit,
    resume_unit,
    make_assess_status_func,
    is_unit_paused_set,
    os_application_version_set,
    CompareOpenStackReleases,
    os_release,
    sequence_status_check_functions,
)
from charmhelpers.contrib.openstack.deferred_events import (
    deferrable_svc_restart,
    check_restart_timestamps,
)
from charmhelpers.core.unitdata import kv
from collections import OrderedDict
import neutron_ovs_context
from charmhelpers.contrib.network.ovs import (
    add_bridge,
    add_bridge_bond,
    add_bridge_port,
    is_linuxbridge_interface,
    add_ovsbridge_linuxbridge,
    full_restart,
    enable_ipfix,
    disable_ipfix,
    generate_external_ids,
)
from charmhelpers.core.hookenv import (
    config,
    DEBUG,
    log,
    status_set,
    ERROR,
    WARNING,
)
from charmhelpers.contrib.openstack.neutron import (
    parse_bridge_mappings,
    determine_dkms_package,
    headers_package,
)
from charmhelpers.contrib.openstack.context import (
    DataPortContext,
    DHCPAgentContext,
    DPDKDeviceContext,
    ExternalPortContext,
    OVSDPDKDeviceContext,
    WorkerConfigContext,
    BondConfig,
    BridgePortInterfaceMap,
    parse_data_port_mappings,
    validate_ovs_use_veth,
)
from charmhelpers.core.host import (
    lsb_release,
    service_restart,
    service_running,
    CompareHostReleases,
    init_is_systemd,
    group_exists,
    user_exists,
    is_container,
)
from charmhelpers.core.kernel import (
    modprobe,
)

from charmhelpers.fetch import (
    apt_install,
    apt_purge,
    apt_update,
    filter_installed_packages,
    filter_missing_packages,
    apt_autoremove,
    get_upstream_version,
    add_source,
)


# The interface is said to be satisfied if anyone of the interfaces in the
# list has a complete context.
# LY: Note the neutron-plugin is always present since that is the relation
#     with the principle and no data currently flows down from the principle
#     so there is no point in having it in REQUIRED_INTERFACES
REQUIRED_INTERFACES = {
    'messaging': ['amqp', 'zeromq-configuration'],
}

VERSION_PACKAGE = 'neutron-common'
NOVA_CONF_DIR = "/etc/nova"
NEUTRON_DHCP_AGENT_CONF = "/etc/neutron/dhcp_agent.ini"
NEUTRON_DNSMASQ_CONF = "/etc/neutron/dnsmasq.conf"
NEUTRON_CONF_DIR = "/etc/neutron"
NEUTRON_CONF = '%s/neutron.conf' % NEUTRON_CONF_DIR
NEUTRON_DEFAULT = '/etc/default/neutron-server'
NEUTRON_L3_AGENT_CONF = "/etc/neutron/l3_agent.ini"
NEUTRON_FWAAS_CONF = "/etc/neutron/fwaas_driver.ini"
ML2_CONF = '%s/plugins/ml2/ml2_conf.ini' % NEUTRON_CONF_DIR
OVS_CONF = '%s/plugins/ml2/openvswitch_agent.ini' % NEUTRON_CONF_DIR
EXT_PORT_CONF = '/etc/init/ext-port.conf'
NEUTRON_METADATA_AGENT_CONF = "/etc/neutron/metadata_agent.ini"
DVR_PACKAGES = [
    'neutron-l3-agent',
    'libnetfilter-log1',
]
DHCP_PACKAGES = ['neutron-dhcp-agent']
# haproxy is required for isolated provider networks
# ns-metadata-proxy LP#1831935
METADATA_PACKAGES = ['neutron-metadata-agent', 'haproxy']
# conntrack is a dependency of neutron-l3-agent and hence is not added
L3HA_PACKAGES = ['keepalived']

PY3_PACKAGES = [
    'python3-neutron',
    'python3-zmq',  # fwaas_v2_log
]

PURGE_PACKAGES = [
    'python-neutron',
    'python-neutron-fwaas',
]

PHY_NIC_MTU_CONF = '/etc/init/os-charm-phy-nic-mtu.conf'
TEMPLATES = 'templates/'
OVS_DEFAULT = '/etc/default/openvswitch-switch'
NEUTRON_DHCP_DEFAULT = '/etc/default/neutron-dhcp-agent'
DPDK_INTERFACES = '/etc/dpdk/interfaces'
NEUTRON_SRIOV_AGENT_CONF = os.path.join(NEUTRON_CONF_DIR,
                                        'plugins/ml2/sriov_agent.ini')
USE_FQDN_KEY = 'neutron-ovs-charm-use-fqdn'
SRIOV_NETPLAN_SHIM_CONF = '/etc/sriov-netplan-shim/interfaces.yaml'


def use_fqdn_hint():
    """Hint for whether FQDN should be used for agent registration

    :returns: True or False
    :rtype: bool
    """
    db = kv()
    return db.get(USE_FQDN_KEY, False)


BASE_RESOURCE_MAP = OrderedDict([
    (NEUTRON_CONF, {
        'services': ['neutron-plugin-openvswitch-agent'],
        'contexts': [neutron_ovs_context.OVSPluginContext(),
                     neutron_ovs_context.RemoteRestartContext(
                         ['neutron-plugin', 'neutron-control']),
                     context.AMQPContext(ssl_dir=NEUTRON_CONF_DIR),
                     context.ZeroMQContext(),
                     context.NotificationDriverContext(),
                     context.HostInfoContext(use_fqdn_hint_cb=use_fqdn_hint),
                     neutron_ovs_context.ZoneContext(),
                     ],
    }),
    (ML2_CONF, {
        'services': ['neutron-plugin-openvswitch-agent'],
        'contexts': [neutron_ovs_context.OVSPluginContext()],
    }),
    (OVS_CONF, {
        'services': ['neutron-openvswitch-agent'],
        'contexts': [neutron_ovs_context.OVSPluginContext()],
    }),
    (OVS_DEFAULT, {
        'services': ['openvswitch-switch'],
        'contexts': [neutron_ovs_context.OVSPluginContext()],
    }),
    (PHY_NIC_MTU_CONF, {
        'services': ['os-charm-phy-nic-mtu'],
        'contexts': [context.PhyNICMTUContext()],
    }),
])
METADATA_RESOURCE_MAP = OrderedDict([
    (NEUTRON_METADATA_AGENT_CONF, {
        'services': ['neutron-metadata-agent'],
        'contexts': [neutron_ovs_context.SharedSecretContext(),
                     neutron_ovs_context.APIIdentityServiceContext(),
                     WorkerConfigContext()],
    }),
])
DHCP_RESOURCE_MAP = OrderedDict([
    (NEUTRON_DHCP_AGENT_CONF, {
        'services': ['neutron-dhcp-agent'],
        'contexts': [DHCPAgentContext()],
    }),
    (NEUTRON_DNSMASQ_CONF, {
        'services': ['neutron-dhcp-agent'],
        'contexts': [DHCPAgentContext()],
    }),
    (NEUTRON_DHCP_DEFAULT, {
        'services': ['neutron-dhcp-agent'],
        'contexts': [DHCPAgentContext()],
    }),
])
DVR_RESOURCE_MAP = OrderedDict([
    (NEUTRON_L3_AGENT_CONF, {
        'services': ['neutron-l3-agent'],
        'contexts': [neutron_ovs_context.L3AgentContext()],
    }),
    (NEUTRON_FWAAS_CONF, {
        'services': ['neutron-l3-agent'],
        'contexts': [neutron_ovs_context.L3AgentContext()],
    }),
    (EXT_PORT_CONF, {
        'services': ['neutron-l3-agent'],
        'contexts': [context.ExternalPortContext()],
    }),
])
DPDK_RESOURCE_MAP = OrderedDict([
    (OVS_DEFAULT, {
        'services': ['openvswitch-switch'],
        'contexts': [DPDKDeviceContext(),
                     neutron_ovs_context.RemoteRestartContext(
                         ['neutron-plugin', 'neutron-control'])],
    }),
    (DPDK_INTERFACES, {
        'services': ['dpdk', 'openvswitch-switch'],
        'contexts': [DPDKDeviceContext()],
    }),
])
SRIOV_RESOURCE_MAP = OrderedDict([
    (NEUTRON_SRIOV_AGENT_CONF, {
        'services': ['neutron-sriov-agent'],
        'contexts': [neutron_ovs_context.OVSPluginContext(),
                     context.NeutronAPIContext()],
    }),
])

TEMPLATES = 'templates/'
INT_BRIDGE = "br-int"
EXT_BRIDGE = "br-ex"
DATA_BRIDGE = 'br-data'


def install_packages():
    # NOTE(jamespage): install neutron-common package so we always
    #                  get a clear signal on which OS release is
    #                  being deployed
    apt_install(filter_installed_packages(['neutron-common']),
                fatal=True)
    # NOTE(jamespage):
    # networking-tools-source provides general tooling for configuration
    # of SR-IOV VF's and Mellanox ConnectX switchdev capable adapters
    # The default PPA published packages back to Xenial, which covers
    # all target series for this charm.
    if config('networking-tools-source') and \
       (use_dpdk() or enable_sriov() or use_hw_offload()):
        add_source(config('networking-tools-source'))
    apt_update()
    # NOTE(jamespage): ensure early install of dkms related
    #                  dependencies for kernels which need
    #                  openvswitch via dkms (12.04).
    dkms_packages = determine_dkms_package()
    if dkms_packages:
        apt_install([headers_package()] + dkms_packages, fatal=True)
    missing_packages = filter_installed_packages(determine_packages())
    if missing_packages:
        status_set('maintenance', 'Installing packages')
        apt_install(missing_packages,
                    fatal=True)
    if use_dpdk():
        enable_ovs_dpdk()

    if use_hw_offload():
        enable_hw_offload()

    # NOTE(tpsilva): if we're using openvswitch driver, we need to explicitly
    #                load the nf_conntrack_ipv4/6 module, since it won't be
    #                loaded automatically in some cases. LP#1834213
    if not is_container() and config('firewall-driver') == 'openvswitch':
        try:
            modprobe('nf_conntrack_ipv4', True)
            modprobe('nf_conntrack_ipv6', True)
        except subprocess.CalledProcessError:
            # Newer kernel versions (4.19+) don't have two modules for that, so
            # only load nf_conntrack
            log("This kernel does not have nf_conntrack_ipv4/6. "
                "Loading nf_conntrack only.")
            modprobe('nf_conntrack', True)


def install_l3ha_packages():
    apt_update()
    apt_install(L3HA_PACKAGES, fatal=True)


def purge_packages(pkg_list):
    purge_pkgs = []
    required_packages = determine_packages()
    for pkg in pkg_list:
        if pkg not in required_packages:
            purge_pkgs.append(pkg)
    purge_pkgs = filter_missing_packages(purge_pkgs)
    if purge_pkgs:
        status_set('maintenance', 'Purging unused packages')
        apt_purge(purge_pkgs, fatal=True)
        apt_autoremove(purge=True, fatal=True)


def determine_packages():
    pkgs = []
    py3_pkgs = []
    plugin_pkgs = neutron_plugin_attribute('ovs', 'packages', 'neutron')
    for plugin_pkg in plugin_pkgs:
        pkgs.extend(plugin_pkg)
    if use_dvr():
        pkgs.extend(DVR_PACKAGES)
        _os_release = os_release('neutron-common', base='icehouse')
        # per 17.08 release notes L3HA + DVR is a Newton+ feature
        if (use_l3ha() and
                CompareOpenStackReleases(_os_release) >= 'newton'):
            pkgs.extend(L3HA_PACKAGES)
        # python3-neutron-fwaas is already dependency package on
        # neutron-l3-agent. However this need to be added to py3_pkgs
        # to support switch from py2 to py3 in Rocky release.
        if CompareOpenStackReleases(_os_release) == 'rocky':
            py3_pkgs.append('python3-neutron-fwaas')
    if enable_local_dhcp():
        pkgs.extend(DHCP_PACKAGES)
        pkgs.extend(METADATA_PACKAGES)

    cmp_release = CompareOpenStackReleases(
        os_release('neutron-common', base='icehouse',
                   reset_cache=True))
    if cmp_release >= 'mitaka' and 'neutron-plugin-openvswitch-agent' in pkgs:
        pkgs.remove('neutron-plugin-openvswitch-agent')
        pkgs.append('neutron-openvswitch-agent')

    if use_dpdk():
        pkgs.append('openvswitch-switch-dpdk')

    if enable_sriov():
        if cmp_release >= 'mitaka':
            pkgs.append('neutron-sriov-agent')
        else:
            pkgs.append('neutron-plugin-sriov-agent')

    if use_hw_offload():
        pkgs.append('mlnx-switchdev-mode')

    if cmp_release >= 'rocky':
        pkgs = [p for p in pkgs if not p.startswith('python-')]
        pkgs.extend(PY3_PACKAGES)
        pkgs.extend(py3_pkgs)

    return pkgs


def determine_purge_packages():
    cmp_release = CompareOpenStackReleases(
        os_release('neutron-common', base='icehouse',
                   reset_cache=True))
    if cmp_release >= 'rocky':
        return PURGE_PACKAGES
    return []


def register_configs(release=None):
    release = release or os_release('neutron-common', base='icehouse')
    configs = templating.OSConfigRenderer(templates_dir=TEMPLATES,
                                          openstack_release=release)
    for cfg, rscs in resource_map().items():
        configs.register(cfg, rscs['contexts'])
    return configs


def resource_map():
    """Get map of resources that will be managed for a single hook execution.

    :returns: map of resources
    :rtype: OrderedDict[str,Dict[str,List[str]]]
    """
    drop_config = []
    resource_map = deepcopy(BASE_RESOURCE_MAP)
    # Remap any service names as required
    _os_release = os_release('neutron-common', base='icehouse')
    if use_dvr():
        resource_map.update(DVR_RESOURCE_MAP)
        resource_map.update(METADATA_RESOURCE_MAP)
        dvr_services = ['neutron-metadata-agent', 'neutron-l3-agent']
        resource_map[NEUTRON_CONF]['services'] += dvr_services
    if enable_local_dhcp():
        resource_map.update(METADATA_RESOURCE_MAP)
        resource_map.update(DHCP_RESOURCE_MAP)
        metadata_services = ['neutron-metadata-agent', 'neutron-dhcp-agent']
        resource_map[NEUTRON_CONF]['services'] += metadata_services
        if use_dpdk() and CompareOpenStackReleases(_os_release) >= 'queens':
            resource_map[OVS_CONF]['services'] += ['neutron-dhcp-agent']
    if CompareOpenStackReleases(_os_release) >= 'mitaka':
        # ml2_conf.ini -> openvswitch_agent.ini
        drop_config.append(ML2_CONF)
        # drop of -plugin from service name
        resource_map[NEUTRON_CONF]['services'].remove(
            'neutron-plugin-openvswitch-agent'
        )
        resource_map[NEUTRON_CONF]['services'].append(
            'neutron-openvswitch-agent'
        )
        if use_dpdk():
            resource_map.update(DPDK_RESOURCE_MAP)
            if ovs_has_late_dpdk_init():
                drop_config.append(OVS_DEFAULT)
    else:
        drop_config.append(OVS_CONF)

    if enable_sriov():
        sriov_agent_name = 'neutron-sriov-agent'
        sriov_resource_map = deepcopy(SRIOV_RESOURCE_MAP)

        if CompareOpenStackReleases(_os_release) < 'mitaka':
            sriov_agent_name = 'neutron-plugin-sriov-agent'
            # Patch resource_map for Kilo and Liberty
            sriov_resource_map[NEUTRON_SRIOV_AGENT_CONF]['services'] = \
                [sriov_agent_name]

        resource_map.update(sriov_resource_map)
        resource_map[NEUTRON_CONF]['services'].append(
            sriov_agent_name)
    if enable_sriov() or use_hw_offload():
        # We do late initialization of this as a call to
        # ``context.SRIOVContext`` requires the ``sriov-netplan-shim`` package
        # to already be installed on the system.
        #
        # Note that we also do not want the charm to manage the service, but
        # only update the configuration for boot-time initialization.
        # LP: #1908351
        try:
            resource_map.update(OrderedDict([
                (SRIOV_NETPLAN_SHIM_CONF, {
                    # We deliberately omit service here as we only want changes
                    # to be applied at boot time.
                    'services': [],
                    'contexts': [SRIOVContext_adapter()],
                }),
            ]))
        except NameError:
            # The resource_map is built at module import time and as such this
            # function is called multiple times prior to the charm actually
            # being installed. As the SRIOVContext depends on a Python module
            # provided by the ``sriov-netplan-shim`` package gracefully ignore
            # this to allow the package to be installed.
            pass

    # Use MAAS1.9 for MTU and external port config on xenial and above
    if CompareHostReleases(lsb_release()['DISTRIB_CODENAME']) >= 'xenial':
        drop_config.extend([EXT_PORT_CONF, PHY_NIC_MTU_CONF])

    for _conf in drop_config:
        try:
            del resource_map[_conf]
        except KeyError:
            pass

    return resource_map


def restart_map():
    '''
    Constructs a restart map based on charm config settings and relation
    state.
    '''
    return {k: v['services'] for k, v in resource_map().items()}


def services(exclude_services=None):
    """Returns a list of (unique) services associate with this charm
    Note that we drop the os-charm-phy-nic-mtu service as it's not an actual
    running service that we can check for.

    @returns [strings] - list of service names suitable for (re)start_service()
    """
    if exclude_services is None:
        exclude_services = []
    s_set = set(chain(*restart_map().values()))
    s_set.discard('os-charm-phy-nic-mtu')
    s_set = {s for s in s_set if s not in exclude_services}
    return list(s_set)


def deferrable_services():
    """Services which should be stopped from restarting.

    All services from services() are deferable. But the charm may
    install a package which install a service that the charm does not add
    to its restart_map. In that case it will be missing from
    self.services. However one of the jobs of deferred events is to ensure
    that packages updates outside of charms also do not restart services.
    To ensure there is a complete list take the services from services()
    and also add in a known list of networking services.

    NOTE: It does not matter if one of the services in the list is not
    installed on the system.

    """

    _svcs = services()
    _svcs.extend(['ovs-vswitchd', 'ovsdb-server', 'ovs-vswitchd-dpdk',
                  'openvswitch-switch'])
    return list(set(_svcs))


def determine_ports():
    """Assemble a list of API ports for services the charm is managing

    @returns [ports] - list of ports that the charm manages.
    """
    ports = []
    if use_dvr():
        ports.append(DVR_RESOURCE_MAP[EXT_PORT_CONF]["ext_port"])
    return ports


UPDATE_ALTERNATIVES = ['update-alternatives', '--set', 'ovs-vswitchd']
OVS_DPDK_BIN = '/usr/lib/openvswitch-switch-dpdk/ovs-vswitchd-dpdk'
OVS_DEFAULT_BIN = '/usr/lib/openvswitch-switch/ovs-vswitchd'


# TODO(jamespage): rework back to charmhelpers
def set_Open_vSwitch_column_value(column, value):
    """
    Calls ovs-vsctl and sets the 'column=value' in the Open_vSwitch table.

    :param column: colume name to set value for
    :param value: value to set
            See http://www.openvswitch.org//ovs-vswitchd.conf.db.5.pdf for
            details of the relevant values.
    :type str
    :returns bool: indicating if a column value was changed
    :raises CalledProcessException: possibly ovsdb-server is not running
    """
    current_value = None
    try:
        current_value = json.loads(subprocess.check_output(
            ['ovs-vsctl', 'get', 'Open_vSwitch', '.', column]
        ))
    except subprocess.CalledProcessError:
        pass

    if current_value != value:
        log('Setting {}:{} in the Open_vSwitch table'.format(column, value))
        subprocess.check_call(['ovs-vsctl', 'set', 'Open_vSwitch',
                               '.', '{}={}'.format(column,
                                                   value)])
        return True
    return False


def enable_ovs_dpdk():
    '''Enables the DPDK variant of ovs-vswitchd and restarts it'''
    subprocess.check_call(UPDATE_ALTERNATIVES + [OVS_DPDK_BIN])
    values_changed = []
    if ovs_has_late_dpdk_init():
        dpdk_context = OVSDPDKDeviceContext()
        other_config = OrderedDict([
            ('dpdk-lcore-mask', dpdk_context.cpu_mask()),
            ('dpdk-socket-mem', dpdk_context.socket_memory()),
            ('dpdk-init', 'true'),
        ])
        if not ovs_vhostuser_client():
            other_config['dpdk-extra'] = (
                '--vhost-owner libvirt-qemu:kvm --vhost-perm 0660 ' +
                dpdk_context.pci_whitelist()
            )
        else:
            other_config['dpdk-extra'] = (
                dpdk_context.pci_whitelist()
            )
        other_config['dpdk-init'] = 'true'
        for column, value in other_config.items():
            values_changed.append(
                set_Open_vSwitch_column_value(
                    'other_config:{}'.format(column),
                    value
                )
            )
    if ((values_changed and any(values_changed)) and
            not is_unit_paused_set()):
        deferrable_svc_restart(
            'openvswitch-switch',
            reason='DPDK Config changed')


def enable_hw_offload():
    '''Enable hardware offload support in Open vSwitch'''
    values_changed = [
        set_Open_vSwitch_column_value('other_config:hw-offload',
                                      'true'),
        set_Open_vSwitch_column_value('other_config:max-idle',
                                      '30000')
    ]
    if ((values_changed and any(values_changed)) and
            not is_unit_paused_set()):
        deferrable_svc_restart(
            'openvswitch-switch',
            reason='Hardware offload config changed')


def install_tmpfilesd():
    '''Install systemd-tmpfiles configuration for ovs vhost-user sockets'''
    # NOTE(jamespage): Only do this if libvirt is actually installed
    if (init_is_systemd() and
            user_exists('libvirt-qemu') and
            group_exists('kvm')):
        shutil.copy('files/nova-ovs-vhost-user.conf',
                    '/etc/tmpfiles.d')
        subprocess.check_call(['systemd-tmpfiles', '--create'])


def purge_sriov_systemd_files():
    '''Purge obsolete SR-IOV configuration scripts'''
    old_paths = [
        '/usr/local/bin/neutron_openvswitch_networking_sriov.py',
        '/usr/local/bin/neutron-openvswitch-networking-sriov.sh',
        '/lib/systemd/system/neutron-openvswitch-networking-sriov.service'
    ]
    for path in old_paths:
        if os.path.exists(path):
            os.remove(path)


def configure_ovs():
    """Configure the OVS plugin.

    This function uses the config.yaml parameters ext-port, data-port and
    bridge-mappings to configure the bridges and ports on the ovs on the
    unit.

    Note that the ext-port is deprecated and data-port/bridge-mappings are
    preferred.

    Thus, if data-port is set, then ext-port is ignored (and if set, then
    it is removed from the set of bridges unless it is defined in
    bridge-mappings/data-port).  A warning is issued, if both data-port and
    ext-port are set.
    """
    status_set('maintenance', 'Configuring ovs')
    if not service_running('openvswitch-switch'):
        full_restart()

    # all bridges use the same datapath_type
    brdata = {
        'datapath-type': determine_datapath_type(),
    }
    brdata.update(generate_external_ids())

    add_bridge(INT_BRIDGE, brdata=brdata)
    add_bridge(EXT_BRIDGE, brdata=brdata)

    # If data-port is defined in the config, we can ignore ext-port value
    # and log an error to the unit's log
    if config('data-port') and config('ext-port'):
        log("Both ext-port and data-port are set. ext-port is deprecated"
            " and is not used when data-port is set.", level=ERROR)

    ext_port_ctx = None
    if use_dvr():
        ext_port_ctx = ExternalPortContext()()
    # Set ext-port only if data-port isn't defined.
    if not config('data-port') and ext_port_ctx and ext_port_ctx['ext_port']:
        add_bridge_port(
            EXT_BRIDGE, ext_port_ctx['ext_port'],
            ifdata=generate_external_ids(EXT_BRIDGE),
            portdata=generate_external_ids(EXT_BRIDGE))

    modern_ovs = ovs_has_late_dpdk_init()

    bridgemaps = None
    portmaps = None
    if not use_dpdk():
        # NOTE(jamespage):
        # Its possible to support both hardware offloaded 'direct' ports
        # and default 'openvswitch' ports on the same hypervisor, so
        # configure bridge mappings in addition to any hardware offload
        # enablement.
        portmaps = DataPortContext()()
        bridgemaps = parse_bridge_mappings(config('bridge-mappings'))
        for br in bridgemaps.values():
            add_bridge(br, brdata=brdata)
            if not portmaps:
                continue

            for port, _br in portmaps.items():
                if _br == br:
                    if not is_linuxbridge_interface(port):
                        add_bridge_port(
                            br, port, promisc=True,
                            ifdata=generate_external_ids(br),
                            portdata=generate_external_ids(br))
                    else:
                        log('{} is a Linux bridge: using Linux bridges in the '
                            'data-port config is deprecated for removal after '
                            '21.10 release of OpenStack charms.'.format(port),
                            level=WARNING)
                        add_ovsbridge_linuxbridge(
                            br, port, ifdata=generate_external_ids(br),
                            portdata=generate_external_ids(br))

    # NOTE(jamespage):
    # hw-offload and dpdk are mutually exclusive so log and error
    # and skip any subsequent DPDK configuration
    if use_dpdk() and use_hw_offload():
        log('DPDK and Hardware offload are mutually exclusive, '
            'please disable enable-dpdk or enable-hardware-offload',
            level=ERROR)
    elif use_dpdk():
        log('Configuring bridges with DPDK', level=DEBUG)

        # TODO(sahid): We should also take into account the
        # "physical-network-mtus" in case different MTUs are
        # configured based on physical networks.
        global_mtu = (neutron_ovs_context.NeutronAPIContext()
                      ()['global_physnet_mtu'])

        dpdk_context = OVSDPDKDeviceContext()
        devices = dpdk_context.devices()

        portmaps = parse_data_port_mappings(config('data-port'))
        bridgemaps = parse_bridge_mappings(config('bridge-mappings'))

        bridge_port_interface_map = BridgePortInterfaceMap()
        bond_config = BondConfig()

        for br, port_iface_map in bridge_port_interface_map.items():
            log('Adding DPDK bridge: {}:{}'.format(br, brdata),
                level=DEBUG)
            add_bridge(br, brdata=brdata)
            if modern_ovs:
                for port in port_iface_map.keys():
                    ifdatamap = bridge_port_interface_map.get_ifdatamap(
                        br, port)
                    # set external-ids for all interfaces
                    for iface in ifdatamap:
                        ifdatamap[iface].update(generate_external_ids(br))
                    # NOTE: DPDK bonds are referenced by name and can be found
                    #       in the data-port config, regular DPDK ports are
                    #       referenced by MAC addresses and their names should
                    #       never be found in data-port
                    if port in portmaps.keys():
                        portdata = bond_config.get_ovs_portdata(port)
                        portdata.update(generate_external_ids(br))
                        log('Adding DPDK bond: {}({}) to bridge: {}'.format(
                            port, list(ifdatamap.keys()), br), level=DEBUG)
                        add_bridge_bond(
                            br, port, list(ifdatamap.keys()),
                            portdata=portdata, ifdatamap=ifdatamap)
                    else:
                        log('Adding DPDK port: {} to bridge: {}'.format(
                            port, br), level=DEBUG)
                        ifdata = ifdatamap[port]
                        add_bridge_port(br, port, ifdata=ifdata,
                                        portdata=generate_external_ids(br),
                                        linkup=False, promisc=None)
        if not modern_ovs:
            # port enumeration in legacy OVS-DPDK must follow alphabetic order
            # of the PCI addresses
            dev_idx = 0
            for pci, mac in sorted(devices.items()):
                # if mac.entity is a bridge, then the port can be added
                # directly, otherwise it is a bond (supported only in
                # modern_ovs) or misconfiguration
                if mac.entity in bridgemaps.values():
                    ifdata = {
                        'type': 'dpdk',
                        'mtu-request': global_mtu
                    }
                    ifdata.update(generate_external_ids(mac.entity))
                    ifname = 'dpdk{}'.format(dev_idx)
                    log('Adding DPDK port {}:{} to bridge {}'.format(
                        ifname, ifdata, mac.entity), level=DEBUG)
                    add_bridge_port(
                        mac.entity, ifname, ifdata=ifdata,
                        portdata=generate_external_ids(mac.entity),
                        linkup=False, promisc=None)
                else:
                    log('DPDK device {} skipped, {} is not a bridge'.format(
                        pci, mac.entity), level=WARNING)
                dev_idx += 1

    target = config('ipfix-target')
    bridges = [INT_BRIDGE, EXT_BRIDGE]
    if bridgemaps:
        bridges.extend(bridgemaps.values())
    elif portmaps:
        bridges.extend(
            [bridge_mac.entity for bridge_mac in portmaps.values()])

    if target:
        for bridge in bridges:
            disable_ipfix(bridge)
            enable_ipfix(bridge, target)
    else:
        # NOTE: removing ipfix setting from a bridge is idempotent and
        #       will pass regardless of the existence of the setting
        for bridge in bridges:
            disable_ipfix(bridge)

    # Ensure this runs so that mtu is applied to data-port interfaces if
    # provided.
    # NOTE(ajkavanagh) for pause/resume we don't gate this as it's not a
    # running service, but rather running a few commands.
    if not init_is_systemd():
        service_restart('os-charm-phy-nic-mtu')


def _get_interfaces_from_mappings(sriov_mappings):
    """Returns list of interfaces based on sriov-device-mappings"""
    interfaces = []
    if sriov_mappings:
        # <net>:<interface>[ <net>:<interface>] configuration
        for token in sriov_mappings.split():
            _, interface = token.split(':')
            interfaces.append(interface)
    return interfaces


def get_shared_secret():
    ctxt = neutron_ovs_context.SharedSecretContext()()
    if 'shared_secret' in ctxt:
        return ctxt['shared_secret']


def use_dvr():
    return not is_container() and context.NeutronAPIContext()().get(
        'enable_dvr', False)


def use_l3ha():
    return not is_container() and context.NeutronAPIContext()().get(
        'enable_l3ha', False)


def determine_datapath_type():
    '''
    Determine the ovs datapath type to use

    @returns string containing the datapath type
    '''
    if use_dpdk():
        return 'netdev'
    return 'system'


def use_dpdk():
    '''Determine whether DPDK should be used'''
    cmp_release = CompareOpenStackReleases(
        os_release('neutron-common', base='icehouse', reset_cache=True))
    return (cmp_release >= 'mitaka' and config('enable-dpdk'))


def use_hw_offload():
    '''
    Determine whether OVS hardware offload should be used

    :returns: boolean indicating whether hardware offload should be enabled
    :rtype: bool
    '''
    cmp_release = CompareOpenStackReleases(
        os_release('neutron-common')
    )
    return (cmp_release >= 'stein' and config('enable-hardware-offload'))


def ovs_has_late_dpdk_init():
    ''' OVS 2.6.0 introduces late initialization '''
    import apt_pkg
    ovs_version = get_upstream_version("openvswitch-switch")
    return apt_pkg.version_compare(ovs_version, '2.6.0') >= 0


def ovs_vhostuser_client():
    '''
    Determine whether OVS will act as a client on the vhostuser socket

    @returns boolean indicating whether OVS will act as a client
    '''
    import apt_pkg
    ovs_version = get_upstream_version("openvswitch-switch")
    return apt_pkg.version_compare(ovs_version, '2.9.0') >= 0


def enable_sriov():
    '''Determine whether SR-IOV is enabled and supported'''
    cmp_release = CompareHostReleases(lsb_release()['DISTRIB_CODENAME'])
    return (cmp_release >= 'xenial' and config('enable-sriov'))


class SRIOVContext_adapter(object):
    """Adapt the SRIOVContext for use in a classic charm.

    :returns: Dictionary with entry point to context map.
    :rtype: Dict[str,SRIOVContext]
    """
    interfaces = []

    def __init__(self):
        self._sriov_device = context.SRIOVContext()

    def __call__(self):
        return {'sriov_device': self._sriov_device}


def enable_nova_metadata():
    return not is_container() and (use_dvr() or enable_local_dhcp())


def enable_local_dhcp():
    return not is_container() and config('enable-local-dhcp-and-metadata')


def check_ext_port_data_port_config(configs):
    """Checks that if data-port is set (other than None) then if ext-port is
    also set, add a warning to the status line.

    :param configs: an OSConfigRender() instance.
    :type configs: OSConfigRender
    :returns: (status, message)
    :rtype: (str, str)
    """
    if config('data-port') and config('ext-port'):
        return ("blocked", "ext-port set when data-port set: see config.yaml")
    # return 'unknown' as the lowest priority to not clobber an existing
    # status.
    return None, None


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
    check_restart_timestamps()
    exclude_services = []
    if is_unit_paused_set():
        exclude_services = ['openvswitch-switch']
    assess_status_func(configs, exclude_services)()
    os_application_version_set(VERSION_PACKAGE)


def assess_status_func(configs, exclude_services=None):
    """Helper function to create the function that will assess_status() for
    the unit.
    Uses charmhelpers.contrib.openstack.utils.make_assess_status_func() to
    create the appropriate status function and then returns it.
    Used directly by assess_status() and also for pausing and resuming
    the unit.

    Note that required_interfaces is augmented with neutron-plugin-api if the
    nova_metadata is enabled.

    NOTE(ajkavanagh) ports are not checked due to race hazards with services
    that don't behave sychronously w.r.t their service scripts.  e.g.
    apache2.
    @param configs: a templating.OSConfigRenderer() object
    @return f() -> None : a function that assesses the unit's workload status
    """
    if exclude_services is None:
        exclude_services = []
    required_interfaces = REQUIRED_INTERFACES.copy()
    if enable_nova_metadata():
        required_interfaces['neutron-plugin-api'] = ['neutron-plugin-api']
    return make_assess_status_func(
        configs, required_interfaces,
        charm_func=sequence_status_check_functions(
            validate_ovs_use_veth, check_ext_port_data_port_config),
        services=services(exclude_services),
        ports=None)


def pause_unit_helper(configs, exclude_services=None):
    """Helper function to pause a unit, and then call assess_status(...) in
    effect, so that the status is correctly updated.
    Uses charmhelpers.contrib.openstack.utils.pause_unit() to do the work.
    @param configs: a templating.OSConfigRenderer() object
    @returns None - this function is executed for its side-effect
    """
    if exclude_services is None:
        exclude_services = []
    _pause_resume_helper(pause_unit, configs, exclude_services)


def resume_unit_helper(configs, exclude_services=None):
    """Helper function to resume a unit, and then call assess_status(...) in
    effect, so that the status is correctly updated.
    Uses charmhelpers.contrib.openstack.utils.resume_unit() to do the work.
    @param configs: a templating.OSConfigRenderer() object
    @returns None - this function is executed for its side-effect
    """
    if exclude_services is None:
        exclude_services = []
    _pause_resume_helper(resume_unit, configs, exclude_services)


def _pause_resume_helper(f, configs, exclude_services=None):
    """Helper function that uses the make_assess_status_func(...) from
    charmhelpers.contrib.openstack.utils to create an assess_status(...)
    function that can be used with the pause/resume of the unit
    @param f: the function to be used with the assess_status(...) function
    @returns None - this function is executed for its side-effect
    """
    # TODO(ajkavanagh) - ports= has been left off because of the race hazard
    # that exists due to service_start()
    if exclude_services is None:
        exclude_services = []
    f(assess_status_func(configs, exclude_services),
      services=services(exclude_services), ports=None)
