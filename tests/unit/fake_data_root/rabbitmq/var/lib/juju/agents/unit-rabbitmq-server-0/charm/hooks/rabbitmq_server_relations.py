#!/usr/bin/python3
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

import glob
import os
import shutil
import sys
import subprocess


_path = os.path.dirname(os.path.realpath(__file__))
_root = os.path.abspath(os.path.join(_path, '..'))


def _add_path(path):
    if path not in sys.path:
        sys.path.insert(1, path)


_add_path(_root)


import rabbit_net_utils
import rabbit_utils as rabbit
import ssl_utils

from lib.utils import (
    chown, chmod,
    is_newer,
)

from charmhelpers.contrib.charmsupport import nrpe
from charmhelpers.contrib.hahelpers.cluster import (
    is_clustered,
    is_elected_leader,
)
from charmhelpers.contrib.openstack.deferred_events import (
    configure_deferred_restarts,
    get_deferred_restarts,
    is_restart_permitted,
)
from charmhelpers.contrib.openstack.utils import (
    is_hook_allowed,
    is_unit_paused_set,
    set_unit_upgrading,
    clear_unit_paused,
    clear_unit_upgrading,
)

from charmhelpers.contrib.openstack.utils import save_script_rc
from charmhelpers.contrib.hardening.harden import harden

from charmhelpers.fetch import (
    add_source,
)
from charmhelpers.fetch import (
    apt_install,
    apt_update,
    filter_installed_packages,
)

from charmhelpers.core.hookenv import (
    open_port,
    close_port,
    log,
    DEBUG,
    ERROR,
    INFO,
    WARNING,
    leader_set,
    leader_get,
    relation_get,
    relation_clear,
    relation_set,
    relation_id as get_relation_id,
    relation_ids,
    related_units,
    service_name,
    local_unit,
    config,
    is_relation_made,
    Hooks,
    UnregisteredHookError,
    is_leader,
    status_set,
    unit_private_ip,
)
from charmhelpers.core.host import (
    cmp_pkgrevno,
    service_stop,
    service_restart,
)

from charmhelpers.contrib.peerstorage import (
    peer_echo,
    peer_retrieve,
    peer_store,
    peer_store_and_set,
    peer_retrieve_by_prefix,
)

from charmhelpers.core.unitdata import kv

import charmhelpers.contrib.openstack.cert_utils as ch_cert_utils

import charmhelpers.contrib.network.ip as ch_ip

hooks = Hooks()

SERVICE_NAME = os.getenv('JUJU_UNIT_NAME').split('/')[0]
POOL_NAME = SERVICE_NAME
RABBIT_DIR = '/var/lib/rabbitmq'
RABBIT_USER = 'rabbitmq'
RABBIT_GROUP = 'rabbitmq'
INITIAL_CLIENT_UPDATE_KEY = 'initial_client_update_done'


@hooks.hook('install.real')
@harden()
def install():
    pre_install_hooks()
    add_source(config('source'), config('key'))
    if is_leader() and not leader_get(rabbit.CLUSTER_MODE_KEY):
        log("Setting {} to {} for installation phase.".format(
            rabbit.CLUSTER_MODE_KEY,
            rabbit.CLUSTER_MODE_FOR_INSTALL))
        leader_set({rabbit.CLUSTER_MODE_KEY: rabbit.CLUSTER_MODE_FOR_INSTALL})
    rabbit.install_or_upgrade_packages()


def validate_amqp_config_tracker(f):
    """Decorator to mark all existing tracked amqp configs as stale so that
    they are refreshed the next time the current unit leader.
    """
    def _validate_amqp_config_tracker(*args, **kwargs):
        if not is_leader():
            kvstore = kv()
            tracker = kvstore.get('amqp_config_tracker')
            if tracker:
                for rid in tracker:
                    tracker[rid]['stale'] = True

                kvstore.set(key='amqp_config_tracker', value=tracker)
                kvstore.flush()

        return f(*args, **kwargs)
    return _validate_amqp_config_tracker


def configure_amqp(username, vhost, relation_id, admin=False,
                   ttlname=None, ttlreg=None, ttl=None):
    """Configure rabbitmq server.

    This function creates user/password, vhost and sets user permissions. It
    also enabales mirroring queues if requested.

    Calls to rabbitmqctl are costly and as such we aim to limit them by only
    doing them if we detect that a settings needs creating or updating. To
    achieve this we track what we set by storing key/value pairs associated
    with a particular relation id in a local database.

    Since this function is only supposed to be called by the cluster leader,
    the database is expected to be invalidated if it exists and we are no
    longer leader so as to ensure that a leader switch results in a
    rabbitmq configuraion consistent with the current leader's view.

    :param username: client username.
    :param vhost: vhost name.
    :param relation_id: optional relation id used to identify the context of
                        this operation. This should always be provided
                        so that we can track what has been set.
    :param admin: boolean value defining whether the new user is admin.
    :param ttlname: the name of ttl
    :param ttlreg: the regular expression of ttl
    :param ttl: the vaule of ttl
    :returns: user password
    """
    log("Configuring rabbitmq for user '{}' vhost '{}' (rid={})".
        format(username, vhost, relation_id), DEBUG)

    if not relation_id:
        raise Exception("Invalid relation id '{}' provided to "
                        "{}()".format(relation_id, configure_amqp.__name__))

    # get and update service password
    password = rabbit.get_rabbit_password(username)

    expected = {'username': username, 'vhost': vhost, 'ttl': ttl,
                'mirroring-queues': config('mirroring-queues')}
    kvstore = kv()
    tracker = kvstore.get('amqp_config_tracker') or {}
    val = tracker.get(relation_id)
    if val == expected and not val.get('stale'):
        log("Rabbit already configured for relation "
            "'{}'".format(relation_id), DEBUG)
        return password
    else:
        tracker[relation_id] = expected

    # update vhost
    rabbit.create_vhost(vhost)
    # NOTE(jamespage): Workaround until we have a good way
    #                  of generally disabling notifications
    #                  based on which services are deployed.
    if vhost == 'openstack':
        rabbit.configure_notification_ttl(vhost,
                                          config('notification-ttl'))
        rabbit.configure_ttl(vhost, ttlname, ttlreg, ttl)

    if admin:
        rabbit.create_user(username, password, ['administrator'])
    else:
        rabbit.create_user(username, password)
    rabbit.grant_permissions(username, vhost)

    # NOTE(freyes): after rabbitmq-server 3.0 the method to define HA in the
    # queues is different
    # http://www.rabbitmq.com/blog/2012/11/19/breaking-things-with-rabbitmq-3-0
    if config('mirroring-queues'):
        rabbit.set_ha_mode(vhost, 'all')

    kvstore.set(key='amqp_config_tracker', value=tracker)
    kvstore.flush()

    return password


def update_clients(check_deferred_restarts=True):
    """Update amqp client relation hooks

    IFF leader node is ready. Client nodes are considered ready once the leader
    has already run amqp_changed.

    :param check_deferred_events: Whether to check if restarts are
                                  permitted before running hook.
    :type check_deferred_events: bool
    """
    if check_deferred_restarts and get_deferred_restarts():
        log("Not sendinfg client update as a restart is pending.", INFO)
        return
    if rabbit.leader_node_is_ready() or rabbit.client_node_is_ready():
        for rid in relation_ids('amqp'):
            for unit in related_units(rid):
                amqp_changed(
                    relation_id=rid,
                    remote_unit=unit,
                    check_deferred_restarts=check_deferred_restarts)


@hooks.hook('dashboards-relation-joined')
def dashboards_relation_joined(relation_id=None, remote_unit=None):
    """
    dashboards relation joined
    send the dashboard json data via relation
    """
    with open(os.path.join("files", "grafana-dashboard.json")) as f:
        dashboard_str = f.read()
    relation_set(relation_id, relation_settings={"dashboard": dashboard_str,
                                                 "name": "RabbitMQ-Overview"})


@hooks.hook('prometheus-rules-relation-joined',
            'prometheus-rules-relation-created')
def prometheus_rules_joined(relation_id=None, remote_unit=None):
    """
    prometheus rules relation joined
    send the prometheus rules via relation
    """
    with open(os.path.join("files", "prom_rule_rmq_splitbrain.yaml")) as f:
        rule = f.read()
    relation_set(relation_id, relation_settings={"groups": rule})


@hooks.hook('scrape-relation-joined', 'scrape-relation-created')
def prometheus_scrape_joined(relation_id=None, remote_unit=None):
    """
    scrape relation joined
    enable prometheus plugin and open port
    """
    err_msg = "rabbitmq-server needs to be >= 3.8 to support Prometheus plugin"
    if cmp_pkgrevno('rabbitmq-server', '3.8.0') < 0:
        log(err_msg, level=WARNING)
        status_set("blocked", err_msg)
        raise Exception(err_msg)
    rabbit.enable_plugin(PROM_PLUGIN)
    open_port(RMQ_MON_PORT)
    relation_set(relation_id, relation_settings={"port": RMQ_MON_PORT})


@hooks.hook('scrape-relation-broken')
def prometheus_scape_broken():
    """
    scrape relation broken
    the relation has been completely removed
    disable prometheus plugin and close port
    """
    rabbit.disable_plugin(PROM_PLUGIN)
    close_port(RMQ_MON_PORT)
    log("scrape relation broken, disabled plugin and close port", level=INFO)


@validate_amqp_config_tracker
@hooks.hook('amqp-relation-changed')
def amqp_changed(relation_id=None, remote_unit=None,
                 check_deferred_restarts=True):
    """Update amqp relations.

    :param relation_id: Relation id to update
    :type relation_id: str
    :param remote_unit: Remote unit on relation_id to update
    :type remote_unit: str
    :param check_deferred_events: Whether to check if restarts are
                                  permitted before running hook.
    :type check_deferred_events: bool
    """
    allowed, reason = is_hook_allowed(
        'amqp-relation-changed',
        check_deferred_restarts=check_deferred_restarts)
    if not allowed:
        log(reason, "WARN")
        return
    singleset = set(['username', 'vhost'])
    host_addr = ch_ip.get_relation_ip(
        rabbit_net_utils.AMQP_INTERFACE,
        cidr_network=config(rabbit_net_utils.AMQP_OVERRIDE_CONFIG))

    sent_update = False
    if rabbit.leader_node_is_ready():
        relation_settings = {'hostname': host_addr,
                             'private-address': host_addr}
        # NOTE: active/active case
        if config('prefer-ipv6'):
            relation_settings['private-address'] = host_addr

        current = relation_get(rid=relation_id, unit=remote_unit)
        if singleset.issubset(current):
            if not all([current.get('username'), current.get('vhost')]):
                log('Relation not ready.', DEBUG)
                return

            # Provide credentials to relations. If password is already
            # available on peer relation then use it instead of reconfiguring.
            username = current['username']
            vhost = current['vhost']
            admin = current.get('admin', False)
            ttlname = current.get('ttlname')
            ttlreg = current.get('ttlreg')
            ttl = current.get('ttl')
            amqp_rid = relation_id or get_relation_id()
            password = configure_amqp(username, vhost, amqp_rid, admin=admin,
                                      ttlname=ttlname, ttlreg=ttlreg, ttl=ttl)
            relation_settings['password'] = password
        else:
            # NOTE(hopem): we should look at removing this code since i don't
            #              think it's ever used anymore and stems from the days
            #              when we needed to ensure consistency between
            #              peerstorage (replaced by leader get/set) and amqp
            #              relations.
            queues = {}
            for k, v in current.items():
                amqp_rid = k.split('_')[0]
                x = '_'.join(k.split('_')[1:])
                if amqp_rid not in queues:
                    queues[amqp_rid] = {}

                queues[amqp_rid][x] = v

            for amqp_rid in queues:
                if singleset.issubset(queues[amqp_rid]):
                    username = queues[amqp_rid]['username']
                    vhost = queues[amqp_rid]['vhost']
                    ttlname = queues[amqp_rid].get('ttlname')
                    ttlreg = queues[amqp_rid].get('ttlreg')
                    ttl = queues[amqp_rid].get('ttl')
                    password = configure_amqp(username, vhost, amqp_rid,
                                              admin=admin, ttlname=ttlname,
                                              ttlreg=ttlreg, ttl=ttl)
                    key = '_'.join([amqp_rid, 'password'])
                    relation_settings[key] = password

        ssl_utils.configure_client_ssl(relation_settings)

        if is_clustered():
            relation_settings['clustered'] = 'true'
            # NOTE(dosaboy): this stanza can be removed once we fully remove
            #                deprecated HA support.
            if is_relation_made('ha'):
                # active/passive settings
                relation_settings['vip'] = config('vip')
                # or ha-vip-only to support active/active, but
                # accessed via a VIP for older clients.
                if config('ha-vip-only') is True:
                    relation_settings['ha-vip-only'] = 'true'

        # set if need HA queues or not
        if cmp_pkgrevno('rabbitmq-server', '3.0.1') < 0:
            relation_settings['ha_queues'] = True

        log("Updating relation {} keys {}"
            .format(relation_id or get_relation_id(),
                    ','.join(relation_settings.keys())), DEBUG)
        peer_store_and_set(relation_id=relation_id,
                           relation_settings=relation_settings)
        sent_update = True
    elif not is_leader() and rabbit.client_node_is_ready():
        if not rabbit.clustered():
            log("This node is not clustered yet, defer sending data to client",
                level=DEBUG)
            return
        log("Propagating peer settings to all amqp relations", DEBUG)

        # NOTE(jamespage) clear relation to deal with data being
        #                 removed from peer storage.
        relation_clear(relation_id)

        # Each unit needs to set the db information otherwise if the unit
        # with the info dies the settings die with it Bug# 1355848
        for rel_id in relation_ids('amqp'):
            peerdb_settings = peer_retrieve_by_prefix(rel_id)
            if 'password' in peerdb_settings:
                peerdb_settings['hostname'] = host_addr
                peerdb_settings['private-address'] = host_addr
                relation_set(relation_id=rel_id, **peerdb_settings)
                sent_update = True
    kvstore = kv()
    update_done = kvstore.get(INITIAL_CLIENT_UPDATE_KEY, False)
    if sent_update and not update_done:
        kvstore.set(key=INITIAL_CLIENT_UPDATE_KEY, value=True)
        kvstore.flush()


@hooks.hook('cluster-relation-joined')
def cluster_joined(relation_id=None):
    relation_settings = {
        'hostname': rabbit.get_unit_hostname(),
        'private-address':
            ch_ip.get_relation_ip(
                rabbit_net_utils.CLUSTER_INTERFACE,
                cidr_network=config(rabbit_net_utils.CLUSTER_OVERRIDE_CONFIG)),
    }

    relation_set(relation_id=relation_id,
                 relation_settings=relation_settings)

    if is_relation_made('ha') and \
            config('ha-vip-only') is False:
        log('hacluster relation is present, skipping native '
            'rabbitmq cluster config.')
        return

    try:
        if not is_leader():
            log('Not the leader, deferring cookie propagation to leader')
            return
    except NotImplementedError:
        if is_newer():
            log('cluster_joined: Relation greater.')
            return

    if not os.path.isfile(rabbit.COOKIE_PATH):
        log('erlang cookie missing from %s' % rabbit.COOKIE_PATH,
            level=ERROR)
        return

    if is_leader():
        log('Leader peer_storing cookie', level=INFO)
        cookie = open(rabbit.COOKIE_PATH, 'r').read().strip()
        peer_store('cookie', cookie)
        peer_store('leader_node_ip', unit_private_ip())
        peer_store('leader_node_hostname', rabbit.get_unit_hostname())


@hooks.hook('cluster-relation-changed')
@rabbit.restart_on_change(rabbit.restart_map())
def cluster_changed(relation_id=None, remote_unit=None):
    # Future travelers beware ordering is significant
    rdata = relation_get(rid=relation_id, unit=remote_unit)

    # sync passwords
    blacklist = ['hostname', 'private-address', 'public-address']
    whitelist = [a for a in rdata.keys() if a not in blacklist]
    peer_echo(includes=whitelist)

    cookie = peer_retrieve('cookie')
    if not cookie:
        log('cluster_changed: cookie not yet set.', level=INFO)
        return

    if rdata:
        hostname = rdata.get('hostname', None)
        private_address = rdata.get('private-address', None)

        if hostname and private_address:
            rabbit.update_hosts_file({private_address: hostname})

    # sync the cookie with peers if necessary
    update_cookie()

    if is_relation_made('ha') and \
            config('ha-vip-only') is False:
        log('hacluster relation is present, skipping native '
            'rabbitmq cluster config.', level=INFO)
        return

    if rabbit.is_sufficient_peers():
        # NOTE(freyes): all the nodes need to marked as 'clustered'
        # (LP: #1691510)
        rabbit.cluster_with()
        # Local rabbit maybe clustered now so check and inform clients if
        # needed.
        update_clients()
        if is_leader():
            if (leader_get(rabbit.CLUSTER_MODE_KEY) !=
                    config(rabbit.CLUSTER_MODE_KEY)):
                log("Informing peers via leaderdb to change {} to {}".format(
                    rabbit.CLUSTER_MODE_KEY,
                    config(rabbit.CLUSTER_MODE_KEY)))
                leader_set({
                    rabbit.CLUSTER_MODE_KEY: config(
                        rabbit.CLUSTER_MODE_KEY)})
                rabbit.ConfigRenderer(
                    rabbit.CONFIG_FILES).write_all()

    if not is_leader() and is_relation_made('nrpe-external-master'):
        update_nrpe_checks()


@hooks.hook('stop')
def stop():
    """Gracefully remove ourself from RabbitMQ cluster before unit is removed

    If RabbitMQ have objections to node removal, for example because of this
    being the only disc node to leave the cluster, the operation will fail and
    unit removal will be blocked with error for operator to investigate.

    In the event of a unit being forcefully or abrubtly removed from the
    cluster without a chance to remove itself, it will be left behind as a
    stopped node in the RabbitMQ cluster.  Having a dormant no longer existing
    stopped node lying around will cause trouble in the event that all RabbitMQ
    nodes are shut down.  In such a situation the cluster most likely will not
    start again without operator intervention as RabbitMQ will want to
    interrogate the now non-existing stopped node about any queue it thinks it
    would be most likely to have authoritative knowledge about.

    For this reason any abruptly removed nodes will be cleaned up periodically
    by the leader unit during its update-status hook run.

    This call is placed in stop hook and not in the cluster-relation-departed
    hook because the latter is not called on the unit being removed.
    """
    rabbit.leave_cluster()


def update_cookie(leaders_cookie=None):
    # sync cookie
    if leaders_cookie:
        cookie = leaders_cookie
    else:
        cookie = peer_retrieve('cookie')
    cookie_local = None
    with open(rabbit.COOKIE_PATH, 'r') as f:
        cookie_local = f.read().strip()

    if cookie_local == cookie:
        log('Cookie already synchronized with peer.')
        return
    elif not is_restart_permitted():
        raise Exception("rabbitmq-server must be restarted but not permitted")

    service_stop('rabbitmq-server')
    with open(rabbit.COOKIE_PATH, 'wb') as out:
        out.write(cookie.encode('ascii'))
    if not is_unit_paused_set():
        service_restart('rabbitmq-server')
        rabbit.wait_app()


@hooks.hook('ha-relation-joined')
@rabbit.restart_on_change({rabbit.ENV_CONF:
                           rabbit.restart_map()[rabbit.ENV_CONF]})
def ha_joined():
    corosync_bindiface = config('ha-bindiface')
    corosync_mcastport = config('ha-mcastport')
    vip = config('vip')
    vip_iface = config('vip_iface')
    vip_cidr = config('vip_cidr')
    vip_only = config('ha-vip-only')

    if None in [corosync_bindiface, corosync_mcastport, vip, vip_iface,
                vip_cidr] and vip_only is True:
        log('Insufficient configuration data to configure VIP-only hacluster.',
            level=ERROR)
        sys.exit(1)

    ctxt = {rabbit.ENV_CONF: rabbit.CONFIG_FILES()[rabbit.ENV_CONF]}
    rabbit.ConfigRenderer(ctxt).write(rabbit.ENV_CONF)

    relation_settings = {}
    relation_settings['corosync_bindiface'] = corosync_bindiface
    relation_settings['corosync_mcastport'] = corosync_mcastport

    if vip_only is True:
        relation_settings['resources'] = {
            'res_rabbitmq_vip': 'ocf:heartbeat:IPaddr2',
        }
        relation_settings['resource_params'] = {
            'res_rabbitmq_vip': 'params ip="%s" cidr_netmask="%s" nic="%s"' %
                                (vip, vip_cidr, vip_iface),
        }
    else:
        relation_settings['resources'] = {
            'res_rabbitmq_vip': 'ocf:heartbeat:IPaddr2',
            'res_rabbitmq-server': 'lsb:rabbitmq-server',
        }

        relation_settings['resource_params'] = {
            'res_rabbitmq_vip': 'params ip="%s" cidr_netmask="%s" nic="%s"' %
                                (vip, vip_cidr, vip_iface),
            'res_rabbitmq-server': 'op start start-delay="5s" '
                                   'op monitor interval="5s"',
        }

    for rel_id in relation_ids('ha'):
        relation_set(relation_id=rel_id, relation_settings=relation_settings)

    env_vars = {
        'OPENSTACK_PORT_EPMD': 4369,
        'OPENSTACK_PORT_MCASTPORT': config('ha-mcastport'),
    }
    save_script_rc(**env_vars)


@hooks.hook('ha-relation-changed')
def ha_changed():
    if not is_clustered():
        return
    vip = config('vip')
    log('ha_changed(): We are now HA clustered. '
        'Advertising our VIP (%s) to all AMQP clients.' %
        vip)


@hooks.hook('nrpe-external-master-relation-changed')
def update_nrpe_checks():
    # NOTE (rgildein): This function has been changed to remove redundant
    # checks and scripts based on rabbitmq configuration, but the main logic
    # was unchanged.
    #
    # The function logic is based on these three functions:
    # 1) copy all the custom NRPE scripts and create cron file
    # 2) add NRPE checks and remove redundant
    # 2.a) update the NRPE vhost check for TLS and non-TLS
    # 2.b) update the NRPE queues check
    # 2.c) update the NRPE cluster check
    # 3) remove redundant scripts - this must be done after removing
    #                               the relevant check
    rabbit.sync_nrpe_files()

    hostname, unit, vhosts, user, password = rabbit.get_nrpe_credentials()
    nrpe_compat = nrpe.NRPE(hostname=hostname)

    for vhost in vhosts:
        rabbit.create_vhost(vhost['vhost'])
        rabbit.grant_permissions(user, vhost['vhost'])

        rabbit.nrpe_update_vhost_check(
            nrpe_compat, unit, user, password, vhost)
        rabbit.nrpe_update_vhost_ssl_check(
            nrpe_compat, unit, user, password, vhost)

    rabbit.nrpe_update_queues_check(nrpe_compat, RABBIT_DIR)
    rabbit.nrpe_update_cluster_check(nrpe_compat, user, password)
    nrpe_compat.write()

    rabbit.remove_nrpe_files()


@hooks.hook('upgrade-charm')
@harden()
def upgrade_charm():
    pre_install_hooks()

    # Ensure older passwd files in /var/lib/juju are moved to
    # /var/lib/rabbitmq which will end up replicated if clustered
    for f in [f for f in os.listdir('/var/lib/juju')
              if os.path.isfile(os.path.join('/var/lib/juju', f))]:
        if f.endswith('.passwd'):
            s = os.path.join('/var/lib/juju', f)
            d = os.path.join('/var/lib/charm/{}'.format(service_name()), f)

            log('upgrade_charm: Migrating stored passwd'
                ' from %s to %s.' % (s, d))
            shutil.move(s, d)
    if is_elected_leader('res_rabbitmq_vip'):
        rabbit.migrate_passwords_to_peer_relation()

    # explicitly update buggy file name naigos.passwd
    old = os.path.join('var/lib/rabbitmq', 'naigos.passwd')
    if os.path.isfile(old):
        new = os.path.join('var/lib/rabbitmq', 'nagios.passwd')
        shutil.move(old, new)

    # NOTE(freyes): cluster_with() will take care of marking the node as
    # 'clustered' for existing deployments (LP: #1691510).
    rabbit.cluster_with()

    # Ensure all client connections are up to date on upgrade
    update_clients()

    # BUG:#1804348
    # for the check_rabbitmq.py script, python3-amqplib needs to be installed;
    # if previous version was a python2 version of the charm this won't happen
    # unless the source is changed.  Ensure it is installed here if needed.
    # LP:#1928802 - also include python3-croniter as its needed for
    # check_rabbitmq_queues.py as of change ab79c3ee
    apt_update(fatal=True)
    missing_packages = filter_installed_packages(['python3-amqplib',
                                                  'python3-croniter'])
    if missing_packages:
        apt_install(missing_packages, fatal=True)


MAN_PLUGIN = 'rabbitmq_management'
PROM_PLUGIN = 'rabbitmq_prometheus'
RMQ_MON_PORT = 15692


@hooks.hook('config-changed')
@rabbit.restart_on_change(rabbit.restart_map())
@harden()
def config_changed(check_deferred_restarts=True):
    """Run config-chaged hook.

    :param check_deferred_events: Whether to check if restarts are
                                  permitted before running hook.
    :type check_deferred_events: bool
    """
    configure_deferred_restarts(rabbit.services())
    allowed, reason = is_hook_allowed(
        'config-changed',
        check_deferred_restarts=check_deferred_restarts)
    if not allowed:
        log(reason, "WARN")
        return
    # Update hosts with this unit's information
    cluster_ip = ch_ip.get_relation_ip(
        rabbit_net_utils.CLUSTER_INTERFACE,
        cidr_network=config(rabbit_net_utils.CLUSTER_OVERRIDE_CONFIG))
    rabbit.update_hosts_file({cluster_ip: rabbit.get_unit_hostname()})

    # Add archive source if provided and not in the upgrade process
    if not leader_get("cluster_series_upgrading"):
        add_source(config('source'), config('key'))
    # Copy in defaults file for updated ulimits
    shutil.copyfile(
        'templates/rabbitmq-server',
        '/etc/default/rabbitmq-server')

    # Install packages to ensure any changes to source
    # result in an upgrade if applicable only if we change the 'source'
    # config option
    if rabbit.archive_upgrade_available():
        # Avoid packge upgrade collissions
        # Stopping and attempting to start rabbitmqs at the same time leads to
        # failed restarts
        rabbit.cluster_wait()
        rabbit.install_or_upgrade_packages()

    if config('ssl') == 'off':
        open_port(5672)
        close_port(int(config('ssl_port')))
    elif config('ssl') == 'on':
        open_port(5672)
        open_port(int(config('ssl_port')))
    elif config('ssl') == 'only':
        close_port(5672)
        open_port(int(config('ssl_port')))
    else:
        log("Unknown ssl config value: '%s'" % config('ssl'), level=ERROR)

    chown(RABBIT_DIR, rabbit.RABBIT_USER, rabbit.RABBIT_USER)
    chmod(RABBIT_DIR, 0o775)

    if rabbit.management_plugin_enabled():
        rabbit.enable_plugin(MAN_PLUGIN)
        open_port(rabbit.get_managment_port())
    else:
        rabbit.disable_plugin(MAN_PLUGIN)
        close_port(rabbit.get_managment_port())
        # LY: Close the old managment port since it may have been opened in a
        #     previous version of the charm. close_port is a noop if the port
        #     is not open
        close_port(55672)

    # NOTE(jamespage): If a newer RMQ version is
    # installed and the old style configuration file
    # is still on disk, remove before re-rendering
    # any new configuration.
    if (os.path.exists(rabbit.RABBITMQ_CONFIG) and
            cmp_pkgrevno('rabbitmq-server', '3.7') >= 0):
        os.remove(rabbit.RABBITMQ_CONFIG)

    rabbit.ConfigRenderer(
        rabbit.CONFIG_FILES()).write_all()

    if is_relation_made("ha"):
        ha_is_active_active = config("ha-vip-only")

        if ha_is_active_active:
            update_nrpe_checks()
        else:
            if is_elected_leader('res_rabbitmq_vip'):
                update_nrpe_checks()
            else:
                log("hacluster relation is present but this node is not active"
                    " skipping update nrpe checks")
    elif is_relation_made('nrpe-external-master'):
        update_nrpe_checks()

    # Only set values if this is the leader
    if not is_leader():
        return

    rabbit.set_all_mirroring_queues(config('mirroring-queues'))

    # Update cluster in case min-cluster-size has changed
    for rid in relation_ids('cluster'):
        for unit in related_units(rid):
            cluster_changed(relation_id=rid, remote_unit=unit)

    # NOTE(jamespage): Workaround until we have a good way
    #                  of generally disabling notifications
    #                  based on which services are deployed.
    if 'openstack' in rabbit.list_vhosts():
        rabbit.configure_notification_ttl('openstack',
                                          config('notification-ttl'))


@hooks.hook('leader-elected')
def leader_elected():
    status_set("maintenance", "{} is the elected leader".format(local_unit()))


@hooks.hook('leader-settings-changed')
@rabbit.restart_on_change(rabbit.restart_map())
def leader_settings_changed():

    if is_unit_paused_set():
        log("Do not run config_changed while unit is paused", "WARNING")
        return

    if not os.path.exists(rabbit.RABBITMQ_CTL):
        log('Deferring cookie configuration, RabbitMQ not yet installed')
        return
    # Get cookie from leader, update cookie locally and
    # force cluster-relation-changed hooks to run on peers
    cookie = leader_get(attribute='cookie')
    if cookie:
        update_cookie(leaders_cookie=cookie)
        # Force cluster-relation-changed hooks to run on peers
        # This will precipitate peer clustering
        # Without this a chicken and egg scenario prevails when
        # using LE and peerstorage
        for rid in relation_ids('cluster'):
            relation_set(relation_id=rid, relation_settings={'cookie': cookie})
    update_clients()
    rabbit.ConfigRenderer(
        rabbit.CONFIG_FILES()).write_all()


def pre_install_hooks():
    for f in glob.glob('exec.d/*/charm-pre-install'):
        if os.path.isfile(f) and os.access(f, os.X_OK):
            subprocess.check_call(['sh', '-c', f])


@hooks.hook('pre-series-upgrade')
def series_upgrade_prepare():
    set_unit_upgrading()
    if not is_unit_paused_set():
        log("Pausing unit for series upgrade.")
        rabbit.pause_unit_helper(rabbit.ConfigRenderer(rabbit.CONFIG_FILES()))
    if is_leader():
        if not leader_get('cluster_series_upgrading'):
            # Inform the entire cluster a series upgrade is occurring.
            # Run the complete-cluster-series-upgrade action on the leader to
            # clear this setting when the full cluster has completed its
            # upgrade.
            leader_set(cluster_series_upgrading=True)


@hooks.hook('post-series-upgrade')
def series_upgrade_complete():
    log("Running complete series upgrade hook", "INFO")
    # NOTE(jamespage): If a newer RMQ version is
    # installed and the old style configuration file
    # is still on disk, remove before re-rendering
    # any new configuration.
    if (os.path.exists(rabbit.RABBITMQ_CONFIG) and
            cmp_pkgrevno('rabbitmq-server', '3.7') >= 0):
        os.remove(rabbit.RABBITMQ_CONFIG)
        rabbit.ConfigRenderer(
            rabbit.CONFIG_FILES()).write_all()
    clear_unit_paused()
    clear_unit_upgrading()
    rabbit.resume_unit_helper(rabbit.ConfigRenderer(rabbit.CONFIG_FILES()))


@hooks.hook('certificates-relation-joined')
def certs_joined(relation_id=None):
    req = ch_cert_utils.CertRequest()
    ip, target_cn = ssl_utils.get_unit_amqp_endpoint_data()
    req.add_entry(None, target_cn, [ip])
    relation_set(
        relation_id=relation_id,
        relation_settings=req.get_request())


@hooks.hook('certificates-relation-changed')
def certs_changed(relation_id=None, unit=None):
    # Ensure Rabbit has restart before telling the clients as rabbit may
    # take time to restart.
    @rabbit.restart_on_change(rabbit.restart_map())
    def render_and_restart():
        rabbit.ConfigRenderer(
            rabbit.CONFIG_FILES()).write_all()
    render_and_restart()
    update_clients()


@hooks.hook('update-status')
@harden()
def update_status():
    log('Updating status.')


if __name__ == '__main__':
    try:
        hooks.execute(sys.argv)
    except UnregisteredHookError as e:
        log('Unknown hook {} - skipping.'.format(e))
    # This solves one off problems waiting for the cluster to complete
    # It will get executed only once as soon as leader_node_is_ready()
    # or client_node_is_ready() returns True
    # Subsequent client requests will be handled by normal
    # amqp-relation-changed hooks
    kvstore = kv()
    if not kvstore.get(INITIAL_CLIENT_UPDATE_KEY, False):
        log(
            "Rerunning update_clients as initial update not yet performed",
            level=DEBUG)
        update_clients()

    rabbit.assess_status(rabbit.ConfigRenderer(rabbit.CONFIG_FILES()))
