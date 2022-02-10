#!/usr/bin/python
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

import ast
import pcmk
import json
import os
import re
import subprocess
import socket
import fcntl
import struct
import time
import xml.etree.ElementTree as ET
import itertools

from base64 import b64decode

from charmhelpers.core.strutils import (
    bool_from_string,
)
from charmhelpers.core.hookenv import (
    local_unit,
    log,
    TRACE,
    DEBUG,
    ERROR,
    INFO,
    WARNING,
    leader_get,
    leader_set,
    relation_get,
    relation_set,
    related_units,
    relation_ids,
    config,
    unit_get,
    status_set,
)
from charmhelpers.core import unitdata
from charmhelpers.contrib.openstack.utils import (
    get_host_ip,
    set_unit_paused,
    clear_unit_paused,
    is_unit_paused_set,
    is_unit_upgrading_set,
)
from charmhelpers.contrib.openstack.ha.utils import (
    assert_charm_supports_dns_ha
)
from charmhelpers.core.host import (
    mkdir,
    rsync,
    service_start,
    service_stop,
    service_running,
    write_file,
    file_hash,
    lsb_release,
    init_is_systemd,
    CompareHostReleases,
)
from charmhelpers.fetch import (
    apt_install,
    add_source,
    apt_update,
)
from charmhelpers.contrib.hahelpers.cluster import (
    peer_ips,
)
from charmhelpers.contrib.network import ip as utils

import netifaces
from netaddr import IPNetwork
import jinja2


TEMPLATES_DIR = 'templates'
COROSYNC_CONF = '/etc/corosync/corosync.conf'
COROSYNC_DEFAULT = '/etc/default/corosync'
COROSYNC_AUTHKEY = '/etc/corosync/authkey'
COROSYNC_HACLUSTER_ACL_DIR = '/etc/corosync/uidgid.d'
COROSYNC_HACLUSTER_ACL = COROSYNC_HACLUSTER_ACL_DIR + '/hacluster'
COROSYNC_CONF_FILES = [
    COROSYNC_DEFAULT,
    COROSYNC_AUTHKEY,
    COROSYNC_CONF,
    COROSYNC_HACLUSTER_ACL,
]
SUPPORTED_TRANSPORTS = ['udp', 'udpu', 'multicast', 'unicast']

PCMKR_CONFIG_DIR = '/etc/pacemaker'
PCMKR_AUTHKEY = PCMKR_CONFIG_DIR + '/authkey'
PCMKR_MAX_RETRIES = 3
PCMKR_SLEEP_SECS = 5

SYSTEMD_OVERRIDES_DIR = '/etc/systemd/system/{}.service.d'
SYSTEMD_OVERRIDES_FILE = '{}/overrides.conf'


MAAS_DNS_CONF_DIR = '/etc/maas_dns'
STONITH_CONFIGURED = 'stonith-configured'


class MAASConfigIncomplete(Exception):
    pass


class RemoveCorosyncNodeFailed(Exception):
    def __init__(self, node_name, called_process_error):
        msg = 'Removing {} from the cluster failed. {} output={}'.format(
            node_name, called_process_error, called_process_error.output)
        super(RemoveCorosyncNodeFailed, self).__init__(msg)


class EnableStonithFailed(Exception):
    def __init__(self, called_process_error):
        msg = 'Enabling STONITH failed. {} output={}'.format(
            called_process_error, called_process_error.output)
        super(EnableStonithFailed, self).__init__(msg)


class DisableStonithFailed(Exception):
    def __init__(self, called_process_error):
        msg = 'Disabling STONITH failed. {} output={}'.format(
            called_process_error, called_process_error.output)
        super(DisableStonithFailed, self).__init__(msg)


def disable_upstart_services(*services):
    for service in services:
        with open("/etc/init/{}.override".format(service), "wt") as override:
            override.write("manual")


def enable_upstart_services(*services):
    for service in services:
        path = '/etc/init/{}.override'.format(service)
        if os.path.exists(path):
            os.remove(path)


def disable_lsb_services(*services):
    for service in services:
        subprocess.check_call(['update-rc.d', '-f', service, 'remove'])


def enable_lsb_services(*services):
    for service in services:
        subprocess.check_call(['update-rc.d', '-f', service, 'defaults'])


def get_iface_ipaddr(iface):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(fcntl.ioctl(
        s.fileno(),
        0x8919,  # SIOCGIFADDR
        struct.pack('256s', iface[:15])
    )[20:24])


def get_iface_netmask(iface):
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    return socket.inet_ntoa(fcntl.ioctl(
        s.fileno(),
        0x891b,  # SIOCGIFNETMASK
        struct.pack('256s', iface[:15])
    )[20:24])


def get_netmask_cidr(netmask):
    netmask = netmask.split('.')
    binary_str = ''
    for octet in netmask:
        binary_str += bin(int(octet))[2:].zfill(8)
    return str(len(binary_str.rstrip('0')))


def get_network_address(iface):
    if iface:
        iface = str(iface)
        network = "{}/{}".format(get_iface_ipaddr(iface),
                                 get_netmask_cidr(get_iface_netmask(iface)))
        ip = IPNetwork(network)
        return str(ip.network)
    else:
        return None


def get_ipv6_network_address(iface):
    # Behave in same way as ipv4 get_network_address() above if iface is None.
    if not iface:
        return None

    try:
        ipv6_addr = utils.get_ipv6_addr(iface=iface)[0]
        all_addrs = netifaces.ifaddresses(iface)

        for addr in all_addrs[netifaces.AF_INET6]:
            if ipv6_addr == addr['addr']:
                network = "{}/{}".format(addr['addr'], addr['netmask'])
                return str(IPNetwork(network).network)

    except ValueError:
        msg = "Invalid interface '%s'" % iface
        status_set('blocked', msg)
        raise Exception(msg)

    msg = "No valid network found for interface '%s'" % iface
    status_set('blocked', msg)
    raise Exception(msg)


def get_corosync_id(unit_name):
    # Corosync nodeid 0 is reserved so increase all the nodeids to avoid it
    off_set = 1000
    return off_set + int(unit_name.split('/')[1])


def nulls(data):
    """Returns keys of values that are null (but not bool)"""
    return [k for k in data.keys()
            if not isinstance(data[k], bool) and not data[k]]


def get_corosync_conf():
    if config('prefer-ipv6'):
        ip_version = 'ipv6'
        bindnetaddr = get_ipv6_network_address
    else:
        ip_version = 'ipv4'
        bindnetaddr = get_network_address

    transport = get_transport()

    # NOTE(jamespage) use local charm configuration over any provided by
    # principle charm
    conf = {
        'ip_version': ip_version,
        'ha_nodes': get_ha_nodes(),
        'transport': transport,
    }

    # NOTE(jamespage): only populate multicast configuration if udp is
    #                  configured
    if transport == 'udp':
        conf.update({
            'corosync_bindnetaddr': bindnetaddr(config('corosync_bindiface')),
            'corosync_mcastport': config('corosync_mcastport'),
            'corosync_mcastaddr': config('corosync_mcastaddr')
        })

    if config('prefer-ipv6'):
        conf['nodeid'] = get_corosync_id(local_unit())

    if config('netmtu'):
        conf['netmtu'] = config('netmtu')

    if config('debug'):
        conf['debug'] = config('debug')

    if not nulls(conf):
        log("Found sufficient values in local config to populate "
            "corosync.conf", level=DEBUG)
        return conf

    conf = {}
    for relid in relation_ids('ha'):
        for unit in related_units(relid):
            conf = {
                'ip_version': ip_version,
                'ha_nodes': get_ha_nodes(),
                'transport': transport,
            }

            # NOTE(jamespage): only populate multicast configuration if udpu is
            #                  configured
            if transport == 'udp':
                bindiface = relation_get('corosync_bindiface',
                                         unit, relid)
                conf.update({
                    'corosync_bindnetaddr': bindnetaddr(bindiface),
                    'corosync_mcastport': relation_get('corosync_mcastport',
                                                       unit, relid),
                    'corosync_mcastaddr': config('corosync_mcastaddr'),
                })

            if config('prefer-ipv6'):
                conf['nodeid'] = get_corosync_id(local_unit())

            if config('netmtu'):
                conf['netmtu'] = config('netmtu')

            if config('debug'):
                conf['debug'] = config('debug')

            # Values up to this point must be non-null
            if nulls(conf):
                continue

            return conf

    missing = [k for k, v in conf.items() if v is None]
    log('Missing required configuration: %s' % missing)
    return None


def emit_systemd_overrides_file():
    """Generate the systemd overrides file
    With Start and Stop timeout values
    Note: (David Ames) Bug#1654403 Work around
    May be removed if bug is resolved
    If timeout value is set to -1 pass infinity
    """
    if not init_is_systemd():
        return

    stop_timeout = int(config('service_stop_timeout'))
    if stop_timeout < 0:
        stop_timeout = 'infinity'
    start_timeout = int(config('service_start_timeout'))
    if start_timeout < 0:
        start_timeout = 'infinity'

    systemd_overrides_context = {'service_stop_timeout': stop_timeout,
                                 'service_start_timeout': start_timeout,
                                 }

    for service in ['corosync', 'pacemaker']:
        overrides_dir = SYSTEMD_OVERRIDES_DIR.format(service)
        overrides_file = SYSTEMD_OVERRIDES_FILE.format(overrides_dir)
        if not os.path.isdir(overrides_dir):
            os.mkdir(overrides_dir)

        write_file(path=overrides_file,
                   content=render_template('systemd-overrides.conf',
                                           systemd_overrides_context))

    # Update systemd with the new information
    subprocess.check_call(['systemctl', 'daemon-reload'])


def emit_corosync_conf():
    corosync_conf_context = get_corosync_conf()
    if corosync_conf_context:
        write_file(path=COROSYNC_CONF,
                   content=render_template('corosync.conf',
                                           corosync_conf_context))
        return True

    return False


def get_pcmkr_key():
    """Return the pacemaker auth key"""
    return config('pacemaker_key') or config('corosync_key')


def emit_base_conf():
    if not os.path.isdir(COROSYNC_HACLUSTER_ACL_DIR):
        os.mkdir(COROSYNC_HACLUSTER_ACL_DIR)
    if not os.path.isdir(PCMKR_CONFIG_DIR):
        os.mkdir(PCMKR_CONFIG_DIR)
    corosync_default_context = {'corosync_enabled': 'yes'}
    write_file(path=COROSYNC_DEFAULT,
               content=render_template('corosync',
                                       corosync_default_context))

    write_file(path=COROSYNC_HACLUSTER_ACL,
               content=render_template('hacluster.acl', {}))

    corosync_key = config('corosync_key')
    if corosync_key:
        write_file(path=COROSYNC_AUTHKEY,
                   content=b64decode(corosync_key),
                   perms=0o400)
        pcmkr_key = get_pcmkr_key()
        write_file(path=PCMKR_AUTHKEY,
                   owner='root',
                   group='haclient',
                   content=b64decode(pcmkr_key),
                   perms=0o440)
        return True

    return False


def render_template(template_name, context, template_dir=TEMPLATES_DIR):
    templates = jinja2.Environment(
        loader=jinja2.FileSystemLoader(template_dir)
    )
    template = templates.get_template(template_name)
    return template.render(context)


def assert_charm_supports_ipv6():
    """Check whether we are able to support charms ipv6."""
    _release = lsb_release()['DISTRIB_CODENAME'].lower()
    if CompareHostReleases(_release) < "trusty":
        msg = "IPv6 is not supported in the charms for Ubuntu " \
              "versions less than Trusty 14.04"
        status_set('blocked', msg)
        raise Exception(msg)


def get_transport():
    transport = config('corosync_transport')
    _deprecated_transport_values = {"multicast": "udp", "unicast": "udpu"}
    val = _deprecated_transport_values.get(transport, transport)
    if val not in ['udp', 'udpu']:
        msg = ("Unsupported corosync_transport type '%s' - supported "
               "types are: %s" % (transport, ', '.join(SUPPORTED_TRANSPORTS)))
        status_set('blocked', msg)
        raise ValueError(msg)

    return val


def get_ipv6_addr():
    """Exclude any ip addresses configured or managed by corosync."""
    excludes = []
    for rid in relation_ids('ha'):
        for unit in related_units(rid):
            resources = parse_data(rid, unit, 'resources')
            for res in resources.values():
                if 'ocf:heartbeat:IPv6addr' in res:
                    res_params = parse_data(rid, unit, 'resource_params')
                    res_p = res_params.get(res)
                    if res_p:
                        for k, v in res_p.values():
                            if utils.is_ipv6(v):
                                log("Excluding '%s' from address list" % v,
                                    level=DEBUG)
                                excludes.append(v)

    return utils.get_ipv6_addr(exc_list=excludes)[0]


def get_ha_nodes():
    ha_units = peer_ips(peer_relation='hanode')
    ha_nodes = {}
    for unit in ha_units:
        corosync_id = get_corosync_id(unit)
        addr = ha_units[unit]
        if config('prefer-ipv6'):
            if not utils.is_ipv6(addr):
                # Not an error since cluster may still be forming/updating
                log("Expected an ipv6 address but got %s" % (addr),
                    level=WARNING)

            ha_nodes[corosync_id] = addr
        else:
            ha_nodes[corosync_id] = get_host_ip(addr)

    corosync_id = get_corosync_id(local_unit())
    if config('prefer-ipv6'):
        addr = get_ipv6_addr()
    else:
        addr = get_host_ip(unit_get('private-address'))

    ha_nodes[corosync_id] = addr

    return ha_nodes


def get_node_flags(flag):
    """Nodes which have advertised the given flag.

    :param flag: Flag to check peers relation data for.
    :type flag: str
    :returns: List of IPs of nodes that are ready to join the cluster
    :rtype: List
    """
    hosts = []
    if config('prefer-ipv6'):
        hosts.append(get_ipv6_addr())
    else:
        hosts.append(unit_get('private-address'))

    for relid in relation_ids('hanode'):
        for unit in related_units(relid):
            if relation_get(flag, rid=relid, unit=unit):
                hosts.append(relation_get('private-address',
                                          rid=relid,
                                          unit=unit))

    hosts.sort()
    return hosts


def get_cluster_nodes():
    """Nodes which have advertised that they are ready to join the cluster.

    :returns: List of IPs of nodes that are ready to join the cluster
    :rtype: List
    """
    return get_node_flags('ready')


def get_member_ready_nodes():
    """List of nodes which have advertised that they have joined the cluster.

    :returns: List of IPs of nodes that have joined thcluster.
    :rtype: List
    """
    return get_node_flags('member_ready')


def parse_data(relid, unit, key):
    """Helper to detect and parse json or ast based relation data"""
    _key = 'json_{}'.format(key)
    data = relation_get(_key, unit, relid) or relation_get(key, unit, relid)
    if data:
        try:
            return json.loads(data)
        except (TypeError, ValueError):
            return ast.literal_eval(data)

    return {}


def configure_stonith():
    if configure_pacemaker_remote_stonith_resource():
        configure_peer_stonith_resource()
        enable_stonith()
        set_stonith_configured(True)
    else:
        # NOTE(lourot): We enter here when no MAAS STONITH resource could be
        # created. Disabling STONITH for now. We're not calling
        # set_stonith_configured(), so that enabling STONITH will be retried
        # later. (STONITH is now always enabled in this charm.)
        # Without MAAS, we keep entering here, which isn't really an issue,
        # except that this fails in rare cases, thus failure_is_fatal=False.
        disable_stonith(failure_is_fatal=False)


def configure_monitor_host():
    """Configure extra monitor host for better network failure detection"""
    log('Checking monitor host configuration', level=DEBUG)
    monitor_host = config('monitor_host')
    if monitor_host:
        if not pcmk.crm_opt_exists('ping'):
            log('Implementing monitor host configuration (host: %s)' %
                monitor_host, level=DEBUG)
            monitor_interval = config('monitor_interval')
            cmd = ('crm -w -F configure primitive ping '
                   'ocf:pacemaker:ping params host_list="%s" '
                   'multiplier="100" op monitor interval="%s" ' %
                   (monitor_host, monitor_interval))
            pcmk.commit(cmd)
            cmd = ('crm -w -F configure clone cl_ping ping '
                   'meta interleave="true"')
            pcmk.commit(cmd)
        else:
            log('Reconfiguring monitor host configuration (host: %s)' %
                monitor_host, level=DEBUG)
            cmd = ('crm -w -F resource param ping set host_list="%s"' %
                   monitor_host)
    else:
        if pcmk.crm_opt_exists('ping'):
            log('Disabling monitor host configuration', level=DEBUG)
            pcmk.commit('crm -w -F resource stop ping')
            pcmk.commit('crm -w -F configure delete ping')


def configure_cluster_global(failure_timeout, cluster_recheck_interval=60):
    """Configure global cluster options

    :param failure_timeout: Duration in seconds (measured from the most recent
                             failure) to wait before resetting failcount to 0.
    :type failure_timeout: int
    :param cluster_recheck_interval: Duration in seconds for the polling
                                     interval at which the cluster checks for
                                     changes in the resource parameters,
                                     constraints or other cluster options.
    :type cluster_recheck_interval: int
    """
    log('Applying global cluster configuration', level=DEBUG)
    # NOTE(lathiat) quorum in a two-node scenario is handled by
    # corosync two_node=1.  In this case quorum is required for
    # initial cluster startup but not if a node was previously in
    # contact with the full cluster.
    log('Configuring no-quorum-policy to stop', level=DEBUG)
    cmd = "crm configure property no-quorum-policy=stop"
    pcmk.commit(cmd)

    cmd = ('crm configure rsc_defaults $id="rsc-options" '
           'resource-stickiness="100" '
           'failure-timeout={}'.format(failure_timeout))
    pcmk.commit(cmd)

    log('Configuring cluster-recheck-interval to {} seconds'.format(
        cluster_recheck_interval), level=DEBUG)
    cmd = "crm configure property cluster-recheck-interval={}".format(
        cluster_recheck_interval)
    pcmk.commit(cmd)


def remove_legacy_maas_stonith_resources():
    """Remove maas stoniths resources using the old name."""
    stonith_resources = pcmk.crm_maas_stonith_resource_list()
    for resource_name in stonith_resources:
        pcmk.commit(
            'crm -w -F resource stop {}'.format(resource_name))
        pcmk.commit(
            'crm -w -F configure delete {}'.format(resource_name))


def _configure_stonith_resource(ctxt):
    hostnames = []
    for host in ctxt['stonith_hostnames']:
        hostnames.append(host)
        if '.' in host:
            hostnames.append(host.split('.')[0])
    ctxt['hostnames'] = ' '.join(sorted(list(set(hostnames))))
    if all(ctxt.values()):
        ctxt['resource_params'] = ctxt['resource_params'].format(**ctxt)
        if pcmk.is_resource_present(ctxt['stonith_resource_name']):
            pcmk.crm_update_resource(
                ctxt['stonith_resource_name'],
                ctxt['stonith_plugin'],
                ctxt['resource_params'])
        else:
            cmd = (
                "crm configure primitive {stonith_resource_name} "
                "{stonith_plugin} {resource_params}").format(**ctxt)
            pcmk.commit(cmd, failure_is_fatal=True)
    else:
        raise ValueError("Missing configuration: {}".format(ctxt))


def configure_null_stonith_resource(stonith_hostnames):
    """Create null stonith resource for the given hostname.

    :param stonith_hostnames: The hostnames that the stonith management system
                             refers to the remote node as.
    :type stonith_hostname: List
    """
    ctxt = {
        'stonith_plugin': 'stonith:null',
        'stonith_hostnames': stonith_hostnames,
        'stonith_resource_name': 'st-null',
        'resource_params': (
            "params hostlist='{hostnames}' "
            "op monitor interval=25 start-delay=25 "
            "timeout=25")}
    _configure_stonith_resource(ctxt)
    # NOTE (gnuoy): Not enabling the global stonith-enabled setting as it
    # does not make sense to have stonith-enabled when the only resources
    # are null resources, so defer enabling stonith-enabled to the 'real'
    # stonith resources.
    return {ctxt['stonith_resource_name']: ctxt['stonith_plugin']}


def configure_maas_stonith_resource(stonith_hostnames):
    """Create maas stonith resource for the given hostname.

    :param stonith_hostnames: The hostnames that the stonith management system
                             refers to the remote node as.
    :type stonith_hostname: List
    """
    ctxt = {
        'stonith_plugin': 'stonith:external/maas',
        'stonith_hostnames': stonith_hostnames,
        'stonith_resource_name': 'st-maas',
        'url': config('maas_url'),
        'apikey': config('maas_credentials'),
        'resource_params': (
            "params url='{url}' apikey='{apikey}' hostnames='{hostnames}' "
            "op monitor interval=25 start-delay=25 "
            "timeout=25")}
    _configure_stonith_resource(ctxt)
    return {ctxt['stonith_resource_name']: ctxt['stonith_plugin']}


def enable_stonith():
    """Enable stonith via the global property stonith-enabled.

    :raises: EnableStonithFailed
    """
    log('Enabling STONITH', level=INFO)
    try:
        pcmk.commit(
            "crm configure property stonith-enabled=true",
            failure_is_fatal=True)
    except subprocess.CalledProcessError as e:
        raise EnableStonithFailed(e)


def disable_stonith(failure_is_fatal=True):
    """Disable stonith via the global property stonith-enabled.

    :param failure_is_fatal: Whether to raise exception if command fails.
    :type failure_is_fatal: bool
    :raises: DisableStonithFailed
    """
    log('Disabling STONITH', level=INFO)
    try:
        pcmk.commit(
            "crm configure property stonith-enabled=false",
            failure_is_fatal=failure_is_fatal)
    except subprocess.CalledProcessError as e:
        raise DisableStonithFailed(e)


def get_ip_addr_from_resource_params(params):
    """Returns the IP address in the resource params provided

    :return: the IP address in the params or None if not found
    """
    reg_ex = r'.* ip_address="([a-fA-F\d\:\.]+)".*'
    res = re.search(reg_ex, params)
    return res.group(1) if res else None


def need_resources_on_remotes():
    """Whether to run resources on remote nodes.

    Check the 'enable-resources' setting across the remote units. If it is
    absent or inconsistent then raise a ValueError.

    :returns: Whether to run resources on remote nodes
    :rtype: bool
    :raises: ValueError
    """
    responses = []
    for relid in relation_ids('pacemaker-remote'):
        for unit in related_units(relid):
            data = parse_data(relid, unit, 'enable-resources')
            # parse_data returns {} if key is absent.
            if type(data) is bool:
                responses.append(data)

    if len(set(responses)) == 1:
        run_resources_on_remotes = responses[0]
    else:
        msg = "Inconsistent or absent enable-resources setting {}".format(
            responses)
        log(msg, level=WARNING)
        raise ValueError(msg)
    return run_resources_on_remotes


def set_cluster_symmetry():
    """Set the cluster symmetry.

    By default the cluster is an Opt-out cluster (equivalent to
    symmetric-cluster=true) this means that any resource can run anywhere
    unless a node explicitly Opts-out. When using pacemaker-remotes there may
    be hundreds of nodes and if they are not prepared to run resources the
    cluster should be switched to an Opt-in cluster.
    """
    try:
        symmetric = need_resources_on_remotes()
    except ValueError:
        msg = 'Unable to calculated desired symmetric-cluster setting'
        log(msg, level=WARNING)
        return
    log('Configuring symmetric-cluster: {}'.format(symmetric), level=DEBUG)
    cmd = "crm configure property symmetric-cluster={}".format(
        str(symmetric).lower())
    pcmk.commit(cmd, failure_is_fatal=True)


def add_score_location_rule(res_name, node, location_score):
    """Add or update a location rule that uses a score.

    :param res_name: Resource that this location rule controls.
    :type res_name: str
    :param node: Node that this location rule relates to.
    :type node: str
    :param location_score: The score to give this location.
    :type location_score: int
    """
    loc_constraint_name = 'loc-{}-{}'.format(res_name, node)
    pcmk.crm_update_location(
        loc_constraint_name,
        res_name,
        location_score,
        node)


def add_location_rules_for_local_nodes(res_name):
    """Add location rules for running resource on local nodes.

    Add location rules allowing the given resource to run on local nodes (eg
    not remote nodes).

    :param res_name: Resource name to create location rules for.
    :type res_name: str
    """
    for node in pcmk.list_nodes():
        loc_constraint_name = 'loc-{}-{}'.format(res_name, node)
        if not pcmk.crm_opt_exists(loc_constraint_name):
            cmd = 'crm -w -F configure location {} {} 0: {}'.format(
                loc_constraint_name,
                res_name,
                node)
            pcmk.commit(cmd, failure_is_fatal=True)
            log('%s' % cmd, level=DEBUG)


def add_location_rules_for_pacemaker_remotes(res_names):
    """Add location rules for pacemaker remote resources on local nodes.

    Add location rules allowing the pacemaker remote resource to run on a local
    node. Use location score rules to spread resources out.

    :param res_names: Pacemaker remote resource names.
    :type res_names: List[str]
    """
    res_names = sorted(res_names)
    nodes = sorted(pcmk.list_nodes())
    prefered_nodes = list(zip(res_names, itertools.cycle(nodes)))
    for res_name in res_names:
        for node in nodes:
            location_score = 0
            if (res_name, node) in prefered_nodes:
                location_score = 200
            add_score_location_rule(
                res_name,
                node,
                location_score)


def configure_pacemaker_remote(remote_hostname, remote_ip):
    """Create a resource corresponding to the pacemaker remote node.

    :param remote_hostname: Remote hostname used for registering remote node.
    :type remote_hostname: str
    :param remote_ip: Remote IP used for registering remote node.
    :type remote_ip: str
    :returns: Name of resource for pacemaker remote node.
    :rtype: str
    """
    resource_name = remote_hostname
    if not pcmk.is_resource_present(resource_name):
        cmd = (
            "crm configure primitive {} ocf:pacemaker:remote "
            "params server={} reconnect_interval=60 "
            "op monitor interval=30s").format(resource_name,
                                              remote_ip)
        pcmk.commit(cmd, failure_is_fatal=True)
    return resource_name


def cleanup_remote_nodes(remote_nodes):
    """Cleanup pacemaker remote resources

    Remove all status records of the resource and
    probe the node afterwards.
    :param remote_nodes: List of resource names associated with remote nodes
    :type remote_nodes: list
    """
    for res_name in remote_nodes:
        cmd = 'crm resource cleanup {}'.format(res_name)
        # Resource cleanups seem to fail occasionally even on healthy nodes
        # Bug #1822962. Given this cleanup task is just housekeeping log
        # the message if a failure occurs and move on.
        if pcmk.commit(cmd, failure_is_fatal=False) == 0:
            log(
                'Cleanup of resource {} succeeded'.format(res_name),
                level=DEBUG)
        else:
            log(
                'Cleanup of resource {} failed'.format(res_name),
                level=WARNING)


def configure_pacemaker_remote_stonith_resource():
    """Create a maas stonith resource for the pacemaker-remotes.

    :returns: Stonith resource dict {res_name: res_type}
    :rtype: dict
    """
    hostnames = []
    stonith_resource = {}
    for relid in relation_ids('pacemaker-remote'):
        for unit in related_units(relid):
            stonith_hostname = parse_data(relid, unit, 'stonith-hostname')
            if stonith_hostname:
                hostnames.append(stonith_hostname)
    if hostnames:
        stonith_resource = configure_maas_stonith_resource(hostnames)
    return stonith_resource


def configure_peer_stonith_resource():
    """Create a null stonith resource for lxd containers.

    :returns: Stonith resource dict {res_name: res_type}
    :rtype: dict
    """
    hostnames = [get_hostname()]
    stonith_resource = {}
    for relid in relation_ids('hanode'):
        for unit in related_units(relid):
            stonith_hostname = relation_get('hostname', unit, relid)
            if stonith_hostname:
                hostnames.append(stonith_hostname)
    stonith_resource = configure_null_stonith_resource(hostnames)
    return stonith_resource


def configure_pacemaker_remote_resources():
    """Create resources corresponding to the pacemaker remote nodes.

    Create resources, location constraints and stonith resources for pacemaker
    remote node.

    :returns: resource dict {res_name: res_type, ...}
    :rtype: dict
    """
    log('Checking for pacemaker-remote nodes', level=DEBUG)
    resources = []
    for relid in relation_ids('pacemaker-remote'):
        for unit in related_units(relid):
            remote_hostname = parse_data(relid, unit, 'remote-hostname')
            remote_ip = parse_data(relid, unit, 'remote-ip')
            if remote_hostname:
                resource_name = configure_pacemaker_remote(
                    remote_hostname,
                    remote_ip)
                resources.append(resource_name)
    cleanup_remote_nodes(resources)
    return {name: 'ocf:pacemaker:remote' for name in resources}


def configure_resources_on_remotes(resources=None, clones=None, groups=None):
    """Add location rules as needed for resources, clones and groups

    If remote nodes should not run resources then add location rules then add
    location rules to enable them on local nodes.

    :param resources: Resource definitions
    :type resources: dict
    :param clones: Clone definitions
    :type clones: dict
    :param groups: Group definitions
    :type groups: dict
    """
    clones = clones or {}
    groups = groups or {}
    try:
        resources_on_remote = need_resources_on_remotes()
    except ValueError:
        msg = 'Unable to calculate whether resources should run on remotes'
        log(msg, level=WARNING)
        return
    if resources_on_remote:
        msg = ('Resources are permitted to run on remotes, no need to create '
               'location constraints')
        log(msg, level=WARNING)
        return
    pacemaker_remotes = []
    for res_name, res_type in resources.items():
        if res_name not in list(clones.values()) + list(groups.values()):
            if res_type == 'ocf:pacemaker:remote':
                pacemaker_remotes.append(res_name)
            else:
                add_location_rules_for_local_nodes(res_name)
    add_location_rules_for_pacemaker_remotes(pacemaker_remotes)
    for cl_name in clones:
        add_location_rules_for_local_nodes(cl_name)
        # Limit clone resources to only running on X number of nodes where X
        # is the number of local nodes. Otherwise they will show as offline
        # on the remote nodes.
        node_count = len(pcmk.list_nodes())
        cmd = ('crm_resource --resource {} --set-parameter clone-max '
               '--meta --parameter-value {}').format(cl_name, node_count)
        pcmk.commit(cmd, failure_is_fatal=True)
        log('%s' % cmd, level=DEBUG)
    for grp_name in groups:
        add_location_rules_for_local_nodes(grp_name)


def restart_corosync_on_change():
    """Simple decorator to restart corosync if any of its config changes"""
    def wrap(f):
        def wrapped_f(*args, **kwargs):
            checksums = {}
            if not is_unit_paused_set():
                for path in COROSYNC_CONF_FILES:
                    checksums[path] = file_hash(path)
            return_data = f(*args, **kwargs)
            # NOTE: this assumes that this call is always done around
            # configure_corosync, which returns true if configuration
            # files where actually generated
            if return_data and not is_unit_paused_set():
                for path in COROSYNC_CONF_FILES:
                    if checksums[path] != file_hash(path):
                        validated_restart_corosync()
                        break

            return return_data
        return wrapped_f
    return wrap


def try_pcmk_wait():
    """Try pcmk.wait_for_pcmk()
    Log results and set status message
    """
    try:
        pcmk.wait_for_pcmk()
        log("Pacemaker is ready", level=TRACE)
    except pcmk.ServicesNotUp as e:
        status_msg = "Pacemaker is down. Please manually start it."
        status_set('blocked', status_msg)
        full_msg = "{} {}".format(status_msg, e)
        log(full_msg, ERROR)
        raise pcmk.ServicesNotUp(full_msg)


@restart_corosync_on_change()
def configure_corosync():
    log('Configuring and (maybe) restarting corosync', level=DEBUG)
    # David Ames Bug#1654403 Work around
    # May be removed if bug is resolved
    emit_systemd_overrides_file()
    return emit_base_conf() and emit_corosync_conf()


def services_running():
    """Determine if both Corosync and Pacemaker are running
    Both from the operating system perspective and with a functional test
    @returns boolean
    """
    pacemaker_status = service_running("pacemaker")
    corosync_status = service_running("corosync")
    log("Pacemaker status: {}, Corosync status: {}"
        "".format(pacemaker_status, corosync_status),
        level=DEBUG)
    if not (pacemaker_status and corosync_status):
        # OS perspective
        return False
    # Functional test of pacemaker. This will raise if pacemaker doesn't get
    # fully ready in time:
    pcmk.wait_for_pcmk()
    return True


def validated_restart_corosync(retries=10):
    """Restart and validate Corosync and Pacemaker are in fact up and running.

    @param retries: number of attempts to restart the services before giving up
    @raises pcmk.ServicesNotUp if after retries services are still not up
    """
    for restart in range(retries):
        try:
            if restart_corosync():
                log("Corosync and Pacemaker are validated as up and running.",
                    INFO)
                return
            else:
                log("Corosync or Pacemaker not validated as up yet, retrying",
                    WARNING)
        except pcmk.ServicesNotUp:
            log("Pacemaker failed to start, retrying", WARNING)
            continue

    msg = ("Corosync and/or Pacemaker failed to restart after {} retries"
           "".format(retries))
    log(msg, ERROR)
    status_set('blocked', msg)
    raise pcmk.ServicesNotUp(msg)


def restart_corosync():
    if service_running("pacemaker"):
        log("Stopping pacemaker", DEBUG)
        service_stop("pacemaker")

    if not is_unit_paused_set():
        log("Stopping corosync", DEBUG)
        service_stop("corosync")
        log("Starting corosync", DEBUG)
        service_start("corosync")
        log("Starting pacemaker", DEBUG)
        service_start("pacemaker")

    return services_running()


def validate_dns_ha():
    """Validate the DNS HA

    Assert the charm will support DNS HA
    Check MAAS related configuration options are properly set

    :raises MAASConfigIncomplete: if maas_url and maas_credentials are not set
    """

    # Will raise an exception if unable to continue
    assert_charm_supports_dns_ha()

    if config('maas_url') and config('maas_credentials'):
        return True
    else:
        msg = ("DNS HA is requested but the maas_url or maas_credentials "
               "settings are not set")
        raise MAASConfigIncomplete(msg)


def setup_maas_api():
    """Install MAAS PPA and packages for accessing the MAAS API.
    """
    add_source(config('maas_source'), config('maas_source_key'))
    apt_update(fatal=True)
    apt_install('python3-maas-client', fatal=True)


def setup_ocf_files():
    """Setup OCF resrouce agent files
    """

    # TODO (thedac) Eventually we want to package the OCF files.
    # Bundle with the charm until then.
    mkdir('/usr/lib/ocf/resource.d/ceph')
    mkdir('/usr/lib/ocf/resource.d/maas')
    # Xenial corosync is not creating this directory
    mkdir('/etc/corosync/uidgid.d')

    rsync('files/ocf/ceph/rbd', '/usr/lib/ocf/resource.d/ceph/rbd')
    rsync('files/ocf/maas/dns', '/usr/lib/ocf/resource.d/maas/dns')
    rsync('files/ocf/maas/maas_dns.py', '/usr/lib/heartbeat/maas_dns.py')
    rsync('files/ocf/maas/maasclient/', '/usr/lib/heartbeat/maasclient/')
    rsync(
        'files/ocf/maas/maas_stonith_plugin.py',
        '/usr/lib/stonith/plugins/external/maas')


def write_maas_dns_address(resource_name, resource_addr):
    """Writes the specified IP address to the resource file for MAAS dns.

    :param resource_name: the name of the resource the address belongs to.
        This is the name of the file that will be written in /etc/maas_dns.
    :param resource_addr: the IP address for the resource. This will be
        written to the resource_name file.
    """
    mkdir(MAAS_DNS_CONF_DIR)
    write_file(os.path.join(MAAS_DNS_CONF_DIR, resource_name),
               content=resource_addr)


def needs_maas_dns_migration():
    """Determines if the MAAS DNS ocf resources need migration.

    :return: True if migration is necessary, False otherwise.
    """
    try:
        subprocess.check_call(['grep', 'OCF_RESOURCE_INSTANCE',
                               '/usr/lib/ocf/resource.d/maas/dns'])
        return True
    except subprocess.CalledProcessError:
        # check_call will raise an exception if grep doesn't find the string
        return False


def is_in_standby_mode(node_name):
    """Check if node is in standby mode in pacemaker

    @param node_name: The name of the node to check
    @returns boolean - True if node_name is in standby mode
    """
    out = (subprocess
           .check_output(['crm', 'node', 'status', node_name])
           .decode('utf-8'))
    root = ET.fromstring(out)

    standby_mode = False
    for nvpair in root.iter('nvpair'):
        if (nvpair.attrib.get('name') == 'standby' and
                nvpair.attrib.get('value') == 'on'):
            standby_mode = True
    return standby_mode


def get_hostname():
    """Return the hostname of this unit

    @returns hostname
    """
    return socket.gethostname()


def enter_standby_mode(node_name, duration='forever'):
    """Put this node into standby mode in pacemaker

    @returns None
    """
    subprocess.check_call(['crm', 'node', 'standby', node_name, duration])


def leave_standby_mode(node_name):
    """Take this node out of standby mode in pacemaker

    @returns None
    """
    subprocess.check_call(['crm', 'node', 'online', node_name])


def node_has_resources(node_name):
    """Check if this node is running resources

    @param node_name: The name of the node to check
    @returns boolean - True if node_name has resources
    """
    out = subprocess.check_output(['crm_mon', '-X']).decode('utf-8')
    root = ET.fromstring(out)
    has_resources = False
    for resource in root.iter('resource'):
        for child in resource:
            if child.tag == 'node' and child.attrib.get('name') == node_name:
                has_resources = True
    return has_resources


def node_is_dc(node_name):
    """Check if this node is the designated controller.

    @param node_name: The name of the node to check
    @returns boolean - True if node_name is the DC
    """
    out = subprocess.check_output(['crm_mon', '-X']).decode('utf-8')
    root = ET.fromstring(out)
    for current_dc in root.iter("current_dc"):
        if current_dc.attrib.get('name') == node_name:
            return True
    return False


def set_unit_status():
    """Set the workload status for this unit

    @returns None
    """
    status_set(*assess_status_helper())


def resume_unit():
    """Resume services on this unit and update the units status

    @returns None
    """
    node_name = get_hostname()
    messages = []
    leave_standby_mode(node_name)
    if is_in_standby_mode(node_name):
        messages.append("Node still in standby mode")
    if messages:
        raise Exception("Couldn't resume: {}".format("; ".join(messages)))
    else:
        clear_unit_paused()
        set_unit_status()


def pause_unit():
    """Pause services on this unit and update the units status

    @returns None
    """
    node_name = get_hostname()
    messages = []
    enter_standby_mode(node_name)
    if not is_in_standby_mode(node_name):
        messages.append("Node not in standby mode")

    # some resources may take some time to be migrated out from the node. So 3
    # retries are made with a 5 seconds wait between each one.
    i = 0
    ready = False
    has_resources = False
    while i < PCMKR_MAX_RETRIES and not ready:
        if node_has_resources(node_name):
            has_resources = True
            i += 1
            time.sleep(PCMKR_SLEEP_SECS)
        else:
            ready = True
            has_resources = False

    if has_resources:
        messages.append("Resources still running on unit")
    status, message = assess_status_helper()
    # New status message will indicate the resource is not running
    if status != 'active' and 'not running' not in message:
        messages.append(message)
    if messages and not is_unit_upgrading_set():
        raise Exception("Couldn't pause: {}".format("; ".join(messages)))
    else:
        set_unit_paused()
        status_set("maintenance",
                   "Paused. Use 'resume' action to resume normal service.")


def assess_status_helper():
    """Assess status of unit

    @returns status, message - status is workload status and message is any
                               corresponding messages
    """
    if config('stonith_enabled') in ['true', 'True', True]:
        return(
            'blocked',
            'stonith_enabled config option is no longer supported')

    if config('no_quorum_policy'):
        if config('no_quorum_policy').lower() not in ['ignore', 'freeze',
                                                      'stop', 'suicide']:
            return(
                'blocked',
                'Invalid no_quorum_policy specified')

    if is_unit_upgrading_set():
        return ("blocked",
                "Ready for do-release-upgrade. Set complete when finished")
    if is_waiting_unit_series_upgrade_set():
        return ("blocked",
                "HA services shutdown, peers are ready for series upgrade")
    if is_unit_paused_set():
        return ("maintenance",
                "Paused. Use 'resume' action to resume normal service.")

    node_count = int(config('cluster_count'))
    status = 'active'
    message = 'Unit is ready and clustered'
    try:
        try_pcmk_wait()
    except pcmk.ServicesNotUp:
        message = 'Pacemaker is down'
        status = 'blocked'
    for relid in relation_ids('hanode'):
        if len(related_units(relid)) + 1 < node_count:
            status = 'blocked'
            message = ("Insufficient peer units for ha cluster "
                       "(require {})".format(node_count))

    # if the status was not changed earlier, we verify the maintenance status
    try:
        if status == 'active':
            prop = pcmk.get_property('maintenance-mode').strip()
    except pcmk.PropertyNotFound:
        # the property is not the output of 'crm configure show xml', so we use
        # the default value for this property. For crmsh>=2.2.0 the default
        # value is automatically provided by show-property or get-property.
        prop = 'false'

    if (status == 'active' and prop == 'true'):
        # maintenance mode enabled in pacemaker
        status = 'maintenance'
        message = 'Pacemaker in maintenance mode'

    for resource in get_resources().keys():
        if not pcmk.is_resource_present(resource):
            return ("waiting",
                    "Resource: {} not yet configured".format(resource))
        if not pcmk.crm_res_running_on_node(resource, get_hostname()):
            return ("blocked",
                    "Resource: {} not running".format(resource))

    return status, message


def ocf_file_exists(res_name, resources,
                    RES_ROOT='/usr/lib/ocf/resource.d'):
    """To determine whether the ocf file exists, allow multiple ocf
       files with the same name in different directories

    @param res_name: The name of the ocf resource to check
    @param resources: ocf resources
    @return: boolean - True if the ocf resource exists
    """
    res_type = None
    for key, val in resources.items():
        if res_name == key:
            if len(val.split(':')) > 2:
                res_type = val.split(':')[1]
                ocf_name = res_name.replace('res_', '').replace('_', '-')
                ocf_file = os.path.join(RES_ROOT, res_type, ocf_name)
                if os.path.isfile(ocf_file):
                    return True
    return False


def kill_legacy_ocf_daemon_process(res_name):
    """Kill legacy ocf daemon process

    @param res_name: The name of the ocf process to kill
    """
    ocf_name = res_name.replace('res_', '').replace('_', '-')
    reg_expr = r'([0-9]+)\s+[^0-9]+{}'.format(ocf_name)
    cmd = ['ps', '-eo', 'pid,cmd']
    ps = subprocess.check_output(cmd).decode('utf-8')
    res = re.search(reg_expr, ps, re.MULTILINE)
    if res:
        pid = res.group(1)
        subprocess.call(['sudo', 'kill', '-9', pid])


def maintenance_mode(enable):
    """Enable/disable pacemaker's maintenance mode"""

    log('Setting maintenance-mode to %s' % enable, level=INFO)

    try:
        current_state = pcmk.get_property('maintenance-mode').strip().lower()
    except pcmk.PropertyNotFound:
        current_state = 'false'

    current_state = True if current_state == 'true' else False
    log('Is maintenance-mode currently enabled? %s' % current_state,
        level=DEBUG)
    if current_state != enable:
        pcmk.set_property('maintenance-mode', str(enable).lower())
    else:
        log('Desired value for maintenance-mode is already set', level=DEBUG)


def get_resources():
    """Get resources from the HA relation

    :returns: dict of resources
    """
    resources = {}
    for rid in relation_ids("ha"):
        for unit in related_units(rid):
            resources = parse_data(rid, unit, 'resources')
    return resources


def set_waiting_unit_series_upgrade():
    """Set the unit to a waiting upgrade state in the local kv() store.
    """
    log("Setting waiting-unit-series-upgrade=true in local kv", DEBUG)
    with unitdata.HookData()() as t:
        kv = t[0]
        kv.set('waiting-unit-series-upgrade', True)


def clear_waiting_unit_series_upgrade():
    """Clear the unit from a waiting upgrade state in the local kv() store.
    """
    log("Setting waiting-unit-series-upgrade=false in local kv", DEBUG)
    with unitdata.HookData()() as t:
        kv = t[0]
        kv.set('waiting-unit-series-upgrade', False)


def is_waiting_unit_series_upgrade_set():
    """Return the state of the kv().get('waiting-unit-series-upgrade').

    To help with units that don't have HookData() (testing)
    if it excepts, return False
    """
    with unitdata.HookData()() as t:
        kv = t[0]
        if not kv.get('waiting-unit-series-upgrade'):
            return False
        return kv.get('waiting-unit-series-upgrade')


def get_series_upgrade_notifications(relid):
    """Check peers for notifications that they are upgrading their series.

    Returns a dict of the form {unit_name: target_series, ...}

    :param relid: Relation id to check for notifications.
    :type relid: str
    :returns: dict
    """
    notifications = {}
    for unit in related_units(relid):
        relation_data = relation_get(rid=relid, unit=unit)
        for key, value in relation_data.items():
            if key.startswith('series_upgrade_of_'):
                notifications[unit] = value
    log("Found series upgrade notifications: {}".format(notifications), DEBUG)
    return notifications


def disable_ha_services():
    """Shutdown and disable HA services."""
    log("Disabling HA services", INFO)
    for svc in ['corosync', 'pacemaker']:
        disable_lsb_services(svc)
        if service_running(svc):
            service_stop(svc)


def enable_ha_services():
    """Startup and enable HA services."""
    log("Enabling HA services", INFO)
    for svc in ['pacemaker', 'corosync']:
        enable_lsb_services(svc)
        if not service_running(svc):
            service_start(svc)


def get_series_upgrade_key():
    series_upgrade_key = 'series_upgrade_of_{}'.format(
        local_unit().replace('/', '_'))
    return series_upgrade_key.replace('-', '_')


def notify_peers_of_series_upgrade():
    """Notify peers which release this unit is upgrading from."""
    ubuntu_rel = lsb_release()['DISTRIB_CODENAME'].lower()
    series_upgrade_key = get_series_upgrade_key()
    relation_data = {
        series_upgrade_key: ubuntu_rel}
    for rel_id in relation_ids('hanode'):
        relation_set(
            relation_id=rel_id,
            relation_settings=relation_data)


def clear_series_upgrade_notification():
    """Remove from series upgrade notification from peers."""
    log("Removing upgrade notification from peers")
    series_upgrade_key = get_series_upgrade_key()
    relation_data = {
        series_upgrade_key: None}
    for rel_id in relation_ids('hanode'):
        relation_set(
            relation_id=rel_id,
            relation_settings=relation_data)


def set_stonith_configured(is_configured):
    """Set the STONITH_CONFIGURED state.

    :param is_configured: Flag to check peers relation data for.
    :type is_configured: bool
    :returns: List of IPs of nodes that are ready to join the cluster
    :rtype: List
    """
    leader_set({STONITH_CONFIGURED: is_configured})


def is_stonith_configured():
    """Get the STONITH_CONFIGURED state.

    :returns: State of STONITH_CONFIGURED state.
    :rtype: bool
    """
    configured = leader_get(STONITH_CONFIGURED) or 'False'
    return bool_from_string(configured)


def get_hanode_hostnames():
    """Hostnames of nodes in the hanode relation.

    :returns: List of hostnames of nodes in the hanode relation.
    :rtype: List
    """
    hanode_hostnames = [get_hostname()]
    for relid in relation_ids('hanode'):
        for unit in related_units(relid):
            hostname = relation_get('hostname', rid=relid, unit=unit)
            if hostname:
                hanode_hostnames.append(hostname)

    hanode_hostnames.sort()
    return hanode_hostnames


def update_node_list():
    """Determine and delete unexpected nodes from the corosync ring.

    :returns: Set of pcmk nodes not part of Juju hanode relation
    :rtype: Set[str]
    :raises: RemoveCorosyncNodeFailed
    """
    pcmk_nodes = set(pcmk.list_nodes())
    juju_nodes = set(get_hanode_hostnames())

    diff_nodes = pcmk_nodes.difference(juju_nodes)
    log("pcmk_nodes[{}], juju_nodes[{}], diff[{}]"
        "".format(pcmk_nodes, juju_nodes, diff_nodes),
        DEBUG)

    for old_node in diff_nodes:
        try:
            pcmk.set_node_status_to_maintenance(old_node)
            pcmk.delete_node(old_node)
        except subprocess.CalledProcessError as e:
            raise RemoveCorosyncNodeFailed(old_node, e)

    return diff_nodes


def is_update_ring_requested(corosync_update_uuid):
    log("Setting corosync-update-uuid=<uuid> in local kv", DEBUG)
    with unitdata.HookData()() as t:
        kv = t[0]
        stored_value = kv.get('corosync-update-uuid')
        if not stored_value or stored_value != corosync_update_uuid:
            kv.set('corosync-update-uuid', corosync_update_uuid)
            return True
    return False


def trigger_corosync_update_from_leader(unit, rid):
    corosync_update_uuid = relation_get(
        attribute='trigger-corosync-update',
        unit=unit, rid=rid,
    )
    if (corosync_update_uuid and
        is_update_ring_requested(corosync_update_uuid) and
            emit_corosync_conf()):
        cmd = 'corosync-cfgtool -R'
        pcmk.commit(cmd)
        return True

    return False
