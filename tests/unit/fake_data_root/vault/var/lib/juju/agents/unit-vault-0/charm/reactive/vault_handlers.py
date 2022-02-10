import base64
import os
import psycopg2
import subprocess
import tenacity
import traceback
import yaml
from pathlib import Path


from charmhelpers.contrib.charmsupport.nrpe import (
    NRPE,
    add_init_service_checks,
    get_nagios_hostname,
    get_nagios_unit_name,
    remove_deprecated_check,
)

from charmhelpers.contrib.openstack.utils import (
    is_unit_paused_set,
    pause_unit,
    resume_unit,
)

from charmhelpers.core.hookenv import (
    application_version_set,
    atexit,
    config,
    DEBUG,
    ERROR,
    hook_name,
    leader_get,
    leader_set,
    local_unit,
    log,
    network_get_primary_address,
    open_port,
    status_set,
    unit_private_ip,
)

from charmhelpers.core.host import (
    service,
    service_restart,
    service_running,
    write_file,
    is_container,
)

from charmhelpers.core.templating import (
    render,
)

from charmhelpers.core import unitdata

from charms.reactive import (
    hook,
    is_state,
    remove_state,
    set_state,
    when,
    any_file_changed,
    when_not,
    when_any,
)

from charms.reactive.relations import (
    endpoint_from_flag,
    endpoint_from_name,
)

from charms.reactive.flags import (
    is_flag_set,
    set_flag,
    clear_flag,
)

from charms.layer import snap

import lib.charm.vault as vault
import lib.charm.vault_pki as vault_pki

# See https://www.vaultproject.io/docs/configuration/storage/postgresql.html

VAULT_TABLE_DDL = """
CREATE TABLE IF NOT EXISTS vault_kv_store (
  parent_path TEXT COLLATE "C" NOT NULL,
  path        TEXT COLLATE "C",
  key         TEXT COLLATE "C",
  value       BYTEA,
  CONSTRAINT pkey PRIMARY KEY (path, key)
);
"""

VAULT_INDEX_DDL = """
CREATE INDEX IF NOT EXISTS parent_path_idx ON vault_kv_store (parent_path);
"""


OPTIONAL_INTERFACES = [
    ['etcd'],
]
REQUIRED_INTERFACES = [
    ['shared-db', 'db.master']
]

VAULT_CONFIG = '/var/snap/vault/common/vault.hcl'
VAULT_SYSTEMD_CONFIG = '/etc/systemd/system/vault.service'


def ssl_available(config):
    if '' in (config['ssl-cert'], config['ssl-key']):
        return False
    return True


def save_etcd_client_credentials(etcd, key, cert, ca):
    """Save etcd TLS key, cert and ca to disk"""
    credentials = etcd.get_client_credentials()
    write_file(key, credentials['client_key'], perms=0o600)
    write_file(cert, credentials['client_cert'], perms=0o600)
    write_file(ca, credentials['client_ca'], perms=0o600)


def validate_snap_channel(channel):
    """Validate a provided snap channel

    Any prefix is ignored ('0.10' in '0.10/stable' for example).

    :param: channel: string of the snap channel to validate
    :returns: boolean: whether provided channel is valid
    """
    channel_suffix = channel.split('/')[-1]
    if channel_suffix not in ('stable', 'candidate', 'beta', 'edge'):
        return False
    return True


@hook('update-status')
def update_status():
    """Handle update-status

    Sets the flag is-update-status-hook to indicate that the current hook is an
    update-status hook; registers an atexit handler to clear the flag at the
    end of the hook.

    This can be used to gate handlers that should not be run during
    update-status which is supposed to be a light-weight status update.
    """
    set_flag('is-update-status-hook')

    def atexit_clear_update_status_flag():
        clear_flag('is-update-status-hook')

    atexit(atexit_clear_update_status_flag)


@when('is-update-status-hook')
def check_really_is_update_status():
    """Clear the is-update-status-hook if the hook is not assess-status.

    This is in case the previous update-status hook execution died for some
    reason and the flag never got cleared.
    """
    if hook_name() != 'update-status':
        clear_flag('is-update-status-hook')


@when_not('snap.installed.vault')
def snap_install():
    channel = config('channel') or 'stable'
    if validate_snap_channel(channel):
        clear_flag('snap.channel.invalid')
        snap.install('core')
        snap.install('vault', channel=channel)
    else:
        set_flag('snap.channel.invalid')


@when_not("is-update-status-hook")
@when('config.changed.channel')
@when('snap.installed.vault')
def snap_refresh():
    channel = config('channel') or 'stable'
    if validate_snap_channel(channel):
        clear_flag('snap.channel.invalid')
        snap.refresh('vault', channel=channel)
        if vault.can_restart():
            log("Restarting vault", level=DEBUG)
            service_restart('vault')
            if config('totally-unsecure-auto-unlock'):
                vault.prepare_vault()
    else:
        set_flag('snap.channel.invalid')


def configure_vault(context):
    log("Running configure_vault", level=DEBUG)
    context['disable_mlock'] = is_container() or config('disable-mlock')

    context['ssl_available'] = is_state('vault.ssl.available')

    if is_flag_set('etcd.tls.available'):
        etcd = endpoint_from_flag('etcd.available')
        log("Etcd detected, adding to context", level=DEBUG)
        context['etcd_conn'] = etcd.connection_string()
        context['etcd_tls_ca_file'] = '/var/snap/vault/common/etcd-ca.pem'
        context['etcd_tls_cert_file'] = '/var/snap/vault/common/etcd-cert.pem'
        context['etcd_tls_key_file'] = '/var/snap/vault/common/etcd.key'
        save_etcd_client_credentials(etcd,
                                     key=context['etcd_tls_key_file'],
                                     cert=context['etcd_tls_cert_file'],
                                     ca=context['etcd_tls_ca_file'])
        context['api_addr'] = vault.get_api_url()
        context['cluster_addr'] = vault.get_cluster_url()
        log("Etcd detected, setting api_addr to {}".format(
            context['api_addr']))
    else:
        log("Etcd not detected", level=DEBUG)
    log("Rendering vault.hcl.j2", level=DEBUG)
    render(
        'vault.hcl.j2',
        VAULT_CONFIG,
        context,
        perms=0o600)
    log("Rendering vault systemd configuation", level=DEBUG)
    render(
        'vault.service.j2',
        VAULT_SYSTEMD_CONFIG,
        {},
        perms=0o644)
    service('enable', 'vault')
    log("Opening vault port", level=DEBUG)
    open_port(8200)
    set_flag('configured')
    if any_file_changed([VAULT_CONFIG, VAULT_SYSTEMD_CONFIG]):
        # force a restart if config has changed
        clear_flag('started')


@when_not("is-update-status-hook")
@when('snap.installed.vault')
@when('db.master.available')
@when('vault.schema.created')
@when('vault.ssl.configured')
def configure_vault_psql(psql):
    context = {
        'storage_name': 'psql',
        'psql_db_conn': psql.master,
    }
    configure_vault(context)


@when_not("is-update-status-hook")
@when('snap.installed.vault')
@when('shared-db.available')
@when('vault.ssl.configured')
def configure_vault_mysql(mysql):
    if (not mysql.allowed_units() or
            local_unit() not in mysql.allowed_units()):
        log("Deferring vault configuration until"
            " MySQL access is granted", level=DEBUG)
        return
    context = {
        'storage_name': 'mysql',
        'mysql_db_relation': mysql,
    }
    if mysql.ssl_ca():
        _db_tls_ca_file = "/var/snap/vault/common/db-tls-ca.pem"
        _db_tls_ca = base64.decodebytes(mysql.ssl_ca().encode())
        write_file(_db_tls_ca_file, _db_tls_ca, perms=0o600)
        context["tls_ca_file"] = _db_tls_ca_file
    configure_vault(context)


@when_not("is-update-status-hook")
@when('config.changed.disable-mlock')
def disable_mlock_changed():
    remove_state('configured')


@hook('upgrade-charm')
def upgrade_charm():
    remove_state('configured')
    remove_state('vault.nrpe.configured')
    remove_state('vault.ssl.configured')
    remove_state('vault.requested-lb')


@when_not("is-update-status-hook")
@when('db.connected')
def request_db(pgsql):
    pgsql.set_database('vault')


@when_not("is-update-status-hook")
@when('shared-db.connected')
def mysql_setup(database):
    """Handle the default database connection setup
    """
    db = {
        'database': 'vault',
        'username': 'vault',
    }
    database.configure(**db)


@when_not("is-update-status-hook")
@when('db.master.available')
@when_not('vault.schema.created')
def create_vault_table(pgsql):
    status_set('maintenance', 'connecting to database')
    conn = psycopg2.connect(str(pgsql.master))
    cur = conn.cursor()
    status_set('maintenance', 'creating vault table')
    cur.execute(VAULT_TABLE_DDL)
    status_set('maintenance', 'creating vault index')
    cur.execute(VAULT_INDEX_DDL)
    status_set('maintenance', 'committing database schema')
    conn.commit()
    cur.close()
    conn.close()
    set_state('vault.schema.created')
    status_set('active', 'database schema created and committed')


@when_not('db.master.available')
def database_not_ready():
    remove_state('vault.schema.created')


@when_not("is-update-status-hook")
@when('snap.installed.vault')
@when_not('vault.ssl.configured')
def configure_ssl():
    c = config()
    if ssl_available(c):
        status_set('maintenance', 'installing SSL key and cert')
        ssl_key = base64.decodebytes(c['ssl-key'].encode())
        write_file('/var/snap/vault/common/vault.key', ssl_key, perms=0o600)
        ssl_cert = base64.decodebytes(c['ssl-cert'].encode())
        if c['ssl-chain']:
            ssl_cert = ssl_cert + base64.decodebytes(c['ssl-chain'].encode())
        write_file('/var/snap/vault/common/vault.crt', ssl_cert, perms=0o600)
        set_state('vault.ssl.available')
    else:
        remove_state('vault.ssl.available')

    if c['ssl-ca']:
        ssl_ca = base64.decodebytes(c['ssl-ca'].encode())
        write_file('/usr/local/share/ca-certificates/vault-ca.crt',
                   ssl_ca, perms=0o644)
        subprocess.check_call(['update-ca-certificates', '--fresh'])

    set_state('vault.ssl.configured')
    remove_state('configured')


@when('config.changed.ssl-cert')
def ssl_cert_changed():
    remove_state('vault.ssl.configured')


@when('config.changed.ssl-chain')
def ssl_chain_changed():
    remove_state('vault.ssl.configured')


@when('config.changed.ssl-key')
def ssl_key_changed():
    remove_state('vault.ssl.configured')


@when('config.changed.ssl-ca')
def ssl_ca_changed():
    remove_state('vault.ssl.configured')


@when_not("is-update-status-hook")
@when('configured')
@when('nrpe-external-master.available')
@when_not('vault.nrpe.configured')
def update_nagios(svc):
    status_set('maintenance', 'configuring Nagios checks')
    hostname = get_nagios_hostname()
    current_unit = get_nagios_unit_name()
    nrpe = NRPE(hostname=hostname)
    remove_deprecated_check(nrpe, ['vault_version'])
    add_init_service_checks(nrpe, ['vault'], current_unit)
    try:
        os.remove('/usr/lib/nagios/plugins/check_vault_version.py')
    except FileNotFoundError:
        pass
    write_file(
        '/usr/lib/nagios/plugins/check_vault_health.py',
        open('files/nagios/check_vault_health.py', 'rb').read(),
        perms=0o755)
    nrpe.add_check(
        'vault_health',
        'Check running vault server version and health',
        '/usr/lib/nagios/plugins/check_vault_health.py',
    )
    nrpe.write()
    set_state('vault.nrpe.configured')


@when('config.changed.nagios_context')
def nagios_context_changed():
    remove_state('vault.nrpe.configured')


@when('config.changed.nagios_servicegroups')
def nagios_servicegroups_changed():
    remove_state('vault.nrpe.configured')


@when_not("is-update-status-hook")
@when('ha.connected')
def cluster_connected(hacluster):
    """Configure HA resources in corosync"""
    dns_record = config('dns-ha-access-record')
    cfg = config()
    vips = config('vip') or None
    if vips and dns_record:
        set_flag('config.dns_vip.invalid')
        log("Unsupported configuration. vip and dns-ha cannot both be set",
            level=ERROR)
        return
    else:
        clear_flag('config.dns_vip.invalid')

    if vips:
        vips = vips.split()

        # the `vip` config option has changed and there was a value previously
        # set, the principle needs to ask hacluster to remove it from
        # pacemaker's configuration (LP: #1952363).
        if cfg.changed('vip') and cfg.previous('vip'):
            old_vips = cfg.previous('vip').split()
            vips_to_del = set(old_vips) - set(vips)
            for vip in vips_to_del:
                log("Registering %s for deletion" % vip)
                hacluster.remove_vip('vault', vip)

        for vip in vips:
            if vip == vault.get_vip(binding='external'):
                hacluster.add_vip('vault-ext', vip)
            else:
                hacluster.add_vip('vault', vip)
    elif dns_record:
        try:
            ip = network_get_primary_address('access')
        except NotImplementedError:
            ip = unit_private_ip()
        hacluster.add_dnsha('vault', ip, dns_record, 'access')
    hacluster.bind_resources()


@when_not("is-update-status-hook")
@when('configured')
@when_not('started')
def start_vault():
    # start or restart vault
    vault.opportunistic_restart()

    @tenacity.retry(wait=tenacity.wait_exponential(multiplier=1, max=10),
                    stop=tenacity.stop_after_attempt(10),
                    retry=tenacity.retry_if_result(lambda b: not b))
    def _check_vault_running():
        return service_running('vault')

    if _check_vault_running():
        set_flag('started')
        clear_flag('failed.to.start')
        if config('totally-unsecure-auto-unlock'):
            vault.prepare_vault()
    else:
        set_flag('failed.to.start')


@when_not("is-update-status-hook")
@when('leadership.is_leader',
      'secrets.connected')
@when_any('endpoint.secrets.new-request', 'secrets.refresh')
def configure_secrets_backend():
    """ Process requests for setup and access to simple kv secret backends """
    @tenacity.retry(wait=tenacity.wait_exponential(multiplier=1, max=10),
                    stop=tenacity.stop_after_attempt(10),
                    reraise=True)
    def _check_vault_status(client):
        if (not service_running('vault') or
                not client.is_initialized() or
                client.is_sealed()):
            return False
        return True

    # NOTE: use localhost listener as policy only allows 127.0.0.1 to
    #       administer the local vault instances via the charm
    client = vault.get_client(url=vault.VAULT_LOCALHOST_URL)

    status_ok = _check_vault_status(client)
    if not status_ok:
        log('Unable to process new secret backend requests,'
            ' deferring until vault is fully configured', level=DEBUG)
        return

    charm_role_id = vault.get_local_charm_access_role_id()
    if charm_role_id is None:
        log('Charm access to vault not configured, deferring'
            ' secrets backend setup', level=DEBUG)
        return
    client.auth_approle(charm_role_id)

    secrets = (endpoint_from_flag('endpoint.secrets.new-request') or
               endpoint_from_flag('secrets.connected'))
    requests = secrets.requests()

    # Configure KV secret backends
    backends = set([request['secret_backend']
                    for request in requests])
    for backend in backends:
        if not backend.startswith('charm-'):
            continue
        vault.configure_secret_backend(client, name=backend)

    refresh_secrets = is_flag_set('secrets.refresh')

    # Configure AppRoles for application unit access
    for request in requests:
        # NOTE: backends must start with charm-
        backend_name = request['secret_backend']
        if not backend_name.startswith('charm-'):
            continue

        unit = request['unit']
        hostname = request['hostname']
        access_address = request['ingress_address']
        isolated = request['isolated']
        unit_name = request.get('unit_name', unit.unit_name).replace('/', '-')
        policy_name = approle_name = 'charm-{}'.format(unit_name)

        if isolated:
            policy_template = vault.SECRET_BACKEND_HCL
        else:
            policy_template = vault.SECRET_BACKEND_SHARED_HCL

        vault.configure_policy(
            client,
            name=policy_name,
            hcl=policy_template.format(backend=backend_name,
                                       hostname=hostname)
        )

        cidr = '{}/32'.format(access_address)
        new_role = (approle_name not in client.list_roles())

        approle_id = vault.configure_approle(
            client,
            name=approle_name,
            cidr=cidr,
            policies=[policy_name])

        if new_role or refresh_secrets:
            wrapped_secret = vault.generate_role_secret_id(
                client,
                name=approle_name,
                cidr=cidr
            )
            secrets.set_role_id(unit=unit,
                                role_id=approle_id,
                                token=wrapped_secret)

    clear_flag('endpoint.secrets.new-request')
    clear_flag('secrets.refresh')


@when('endpoint.lb-provider.available')
@when('leadership.is_leader')
@when_not('vault.requested-lb')
def request_lb():
    lb_provider = endpoint_from_name('lb-provider')
    req = lb_provider.get_request('vault')
    req.protocol = req.protocols.tcp
    req.port_mapping = {8220: 8220}
    lb_provider.send_request(req)
    set_flag('vault.requested-lb')


@when('vault.requested-lb')
@when_not('endpoint.lb-provider.available')
def clear_requested_lb():
    clear_flag('vault.requested-lb')


@when_not("is-update-status-hook")
@when('secrets.connected')
def send_vault_url_and_ca():
    secrets = endpoint_from_flag('secrets.connected')
    lb_provider = endpoint_from_name('lb-provider')
    vault_url_external = None
    hostname = config('hostname')
    vip = vault.get_vip()
    if is_flag_set('ha.available'):
        if hostname:
            vault_url = vault.get_api_url(address=hostname)
        else:
            vault_url = vault.get_api_url(address=vip)
            ext_vip = vault.get_vip(binding='external')
            if ext_vip and ext_vip != vip:
                vault_url_external = vault.get_api_url(address=ext_vip,
                                                       binding='external')
    elif vip:
        log("VIP is set but ha.available is not yet set, skipping "
            "send_vault_url_and_ca.", level=DEBUG)
        return
    elif lb_provider.has_response:
        response = lb_provider.get_response('vault')
        if response.error:
            log('Load balancer failed, skipping: '
                '{}'.format(response.error_message or response.error_fields),
                level=ERROR)
            return
        vault_url = vault.get_api_url(address=response.address)
        vault_url_external = vault_url
        lb_provider.ack_response(response)
    else:
        vault_url = vault.get_api_url()
        vault_url_external = vault.get_api_url(binding='external')
        if vault_url_external == vault_url:
            vault_url_external = None

    secrets.publish_url(vault_url=vault_url, remote_binding='access')
    if vault_url_external:
        secrets.publish_url(vault_url=vault_url_external,
                            remote_binding='external')

    if config('ssl-ca'):
        secrets.publish_ca(vault_ca=config('ssl-ca'))


@when('snap.installed.vault')
def prime_assess_status():
    atexit(_assess_status)


def _assess_interface(interface, optional,
                      missing_interfaces, incomplete_interfaces):
    """Assess a named interface for presence and completeness

    Uses reactive flags 'connected' and 'available' to indicate whether
    an interface is present and complete.

    :param: interface: Name of interface to assess.
    :param: options: Boolean indicating whether interface is optional
    :param: missing_interfaces: List of missing interfaces to update
    :param: incomplete_interfaces: List of incomplete interfaces to update
    :returns: bool, bool: Tuple of booleans indicating (missing, incomplete)
    """
    log("Assessing interface {}".format(interface), level=DEBUG)
    base_name = interface.split('.')[0]
    connected = (
        is_flag_set('{}.connected'.format(interface)) or
        is_flag_set('{}.connected'.format(base_name))
    )
    missing = False
    incomplete = False
    if not connected:
        if not optional:
            missing_interfaces.append(base_name)
        missing = True
        incomplete = True
    elif connected and not is_flag_set('{}.available'.format(interface)):
        incomplete_interfaces.append(base_name)
        incomplete = True
    return (missing, incomplete)


def _assess_interface_groups(interfaces, optional,
                             missing_interfaces, incomplete_interfaces):
    """Assess the relation state of a list of interface groups

    :param: interfaces: List of interface groups
    :param: options: Boolean indicating whether interfaces are optional
    :param: missing_interfaces: List of missing interfaces to update
    :param: incomplete_interfaces: List of incomplete interfaces to update
    """
    for interface_group in interfaces:
        log("Processing interface group: {}".format(interface_group),
            level=DEBUG)
        _potentially_missing = []
        _potentially_incomplete = []
        for interface in interface_group:
            missing, incomplete = _assess_interface(
                interface=interface, optional=optional,
                missing_interfaces=_potentially_missing,
                incomplete_interfaces=_potentially_incomplete)
            if not missing and not incomplete:
                break
        else:
            # NOTE(jamespage): If an interface group has an incomplete
            #                  interface then the end user has made a
            #                  choice as to which interface to use, so
            #                  don't flag any interfaces as missing.
            if (not optional and
                    _potentially_missing and not _potentially_incomplete):
                formatted_interfaces = [
                    "'{}'".format(i) for i in _potentially_missing
                ]
                missing_interfaces.append(
                    "{} missing".format(' or '.join(formatted_interfaces))
                )

            # NOTE(jamespage): Only display interfaces as incomplete if
            #                  if they are not in the missing interfaces
            #                  list for this interface group.
            if _potentially_incomplete:
                filtered_interfaces = [
                    i for i in _potentially_incomplete
                    if i not in _potentially_missing
                ]
                formatted_interfaces = [
                    "'{}'".format(i) for i in filtered_interfaces
                ]
                incomplete_interfaces.append(
                    "{} incomplete".format(' or '.join(formatted_interfaces))
                )


def _assess_status():
    """Assess status of relations and services for local unit"""
    if is_flag_set('snap.channel.invalid'):
        status_set('blocked',
                   'Invalid snap channel '
                   'configured: {}'.format(config('channel')))
        return
    if is_flag_set('config.dns_vip.invalid'):
        status_set('blocked',
                   'vip and dns-ha-access-record configured')
        return
    if is_flag_set('config.lb_vip.invalid'):
        status_set('blocked',
                   'lb-provider and vip are mutually exclusive')
        return
    if is_flag_set('config.lb_dns.invalid'):
        status_set('blocked',
                   'lb-provider and dns-ha-access-record are '
                   'mutually exclusive')
        return

    if unitdata.kv().get('charm.vault.series-upgrading'):
        status_set("blocked",
                   "Ready for do-release-upgrade and reboot. "
                   "Set complete when finished.")
        return

    if is_flag_set('failed.to.start'):
        status_set("blocked",
                   "Vault failed to start; check journalctl -u vault")
        return

    _missing_interfaces = []
    _incomplete_interfaces = []

    _assess_interface_groups(REQUIRED_INTERFACES, optional=False,
                             missing_interfaces=_missing_interfaces,
                             incomplete_interfaces=_incomplete_interfaces)

    if _missing_interfaces or _incomplete_interfaces:
        state = 'blocked' if _missing_interfaces else 'waiting'
        status_set(state, ', '.join(_missing_interfaces +
                                    _incomplete_interfaces))
        return

    health = None
    if service_running('vault'):
        try:
            health = vault.get_vault_health()
        except Exception:
            log(traceback.format_exc(), level=ERROR)
            status_set('blocked', 'Vault health check failed')
            return
    else:
        status_set('blocked', 'Vault service not running')
        return

    if health.get('version'):
        application_version_set(health.get('version'))
    else:
        application_version_set('Unknown')
        status_set('blocked', 'Unknown vault version')
        return

    if not health['initialized']:
        status_set('blocked', 'Vault needs to be initialized')
        return

    if health['sealed']:
        status_set('blocked', 'Unit is sealed')
        return

    if not leader_get(vault.CHARM_ACCESS_ROLE_ID):
        status_set(
            'blocked',
            'Vault charm not yet authorized: run authorize-charm action.')
        return

    if not client_approle_authorized():
        status_set('blocked', 'Vault cannot authorize approle')
        return

    lb_provider = endpoint_from_name('lb-provider')
    is_leader = is_flag_set('leadership.is_leader')
    if is_leader and lb_provider and lb_provider.is_available:
        if not lb_provider.has_response:
            status_set('waiting', 'Waiting for load balancer')
            return
        response = lb_provider.get_response('vault')
        if response.error:
            status_set('blocked',
                       'Load balancer failed: '
                       '{}'.format(response.error_message or
                                   response.error_fields))
            return

    is_leader = is_flag_set('leadership.is_leader')
    has_ca = is_flag_set('charm.vault.ca.ready')
    has_cert_reqs = is_flag_set('certificates.certs.requested')
    if is_leader and has_cert_reqs and not has_ca:
        status_set('blocked', 'Missing CA cert')
        return

    has_certs_relation = is_flag_set('certificates.available')
    if is_leader and has_certs_relation and not has_ca:
        status_set('blocked', 'Missing CA cert')
        return

    _assess_interface_groups(OPTIONAL_INTERFACES, optional=True,
                             missing_interfaces=_missing_interfaces,
                             incomplete_interfaces=_incomplete_interfaces)

    if _missing_interfaces or _incomplete_interfaces:
        state = 'blocked' if _missing_interfaces else 'waiting'
        status_set(state, ', '.join(_missing_interfaces +
                                    _incomplete_interfaces))
        return

    mlock_disabled = is_container() or config('disable-mlock')

    vault_installed_version = snap.get_installed_version('vault')
    vault_running_version = health.get('version')
    if vault_installed_version != vault_running_version:
        status_set(
            'active',
            'New version of vault installed, manual intervention required '
            'to restart the service.')
        return

    if is_flag_set('etcd.tls.available'):
        client = vault.get_local_client()
        if not client.ha_status['ha_enabled']:
            status_set(
                'active',
                'Vault running as non-HA, manual intervention required '
                'to restart the service.')
            return

    status_set(
        'active',
        'Unit is ready '
        '(active: {}, mlock: {})'.format(
            str(not health['standby']).lower(),
            'disabled' if mlock_disabled else 'enabled'
        )
    )


def client_approle_authorized():
    if not leader_get(vault.CHARM_ACCESS_ROLE_ID):
        log("Charm not yet authorized", "DEBUG")
        return False
    try:
        vault.get_local_client()
        return True
    except (vault.hvac.exceptions.InternalServerError,
            vault.hvac.exceptions.InvalidRequest,
            vault.VaultNotReady,
            vault.hvac.exceptions.VaultDown,
            vault.requests.exceptions.ReadTimeout):
        log("InternalServerError: Unable to authorize approle. "
            "This may indicate failure to communicate with the database ",
            "WARNING")
        log(traceback.format_exc(), level=ERROR)
        return False


@when_not("is-update-status-hook")
@when_any('db.master.available', 'shared-db.available')
@when('leadership.is_leader',
      'config.set.auto-generate-root-ca-cert')
@when_not('charm.vault.ca.ready',
          'charm.vault.ca.auto-generated')
def auto_generate_root_ca_cert():
    actions_yaml = yaml.safe_load(Path('actions.yaml').read_text())
    props = actions_yaml['generate-root-ca']['properties']
    ttl = config()['default-ca-ttl']
    max_ttl = config()['max-ttl']
    action_config = {key: value['default'] for key, value in props.items()}
    try:
        root_ca = vault_pki.generate_root_ca(
            allow_any_name=action_config['allow-any-name'],
            allowed_domains=action_config['allowed-domains'],
            allow_bare_domains=action_config['allow-bare-domains'],
            allow_subdomains=action_config['allow-subdomains'],
            allow_glob_domains=action_config['allow-glob-domains'],
            enforce_hostnames=action_config['enforce-hostnames'],
            ttl=ttl,
            max_ttl=max_ttl)
        leader_set({'root-ca': root_ca})
        set_flag('charm.vault.ca.ready')
        set_flag('charm.vault.ca.auto-generated')
    except vault.VaultError as e:
        log("Skipping auto-generate root CA cert: {}".format(e))


@when_not("is-update-status-hook")
@when('leadership.is_leader',
      'leadership.set.root-ca')
@when_not('charm.vault.ca.ready')
def takeover_cert_leadership():
    # the CA was configured by a previous leader, but we're the leader now so
    # we need to take over cert management duties
    set_flag('charm.vault.ca.ready')


@when_not("is-update-status-hook")
@when_any('db.master.available', 'shared-db.available')
@when('leadership.is_leader',
      'charm.vault.ca.ready',
      'certificates.available')
def publish_ca_info():
    if not client_approle_authorized():
        log("Vault not authorized: Skipping publicsh_ca_info", "WARNING")
        return
    if is_unit_paused_set():
        log("The Vault unit is paused, passing on publishing ca info.")
        return
    if not service_running('vault'):
        set_flag('failed.to.start')
        return
    client = vault.get_client(url=vault.VAULT_LOCALHOST_URL)
    tls = endpoint_from_flag('certificates.available')
    if client.is_sealed():
        log("Unable to publish ca info, service sealed.")
    else:
        tls.set_ca(vault_pki.get_ca())
        try:
            # this might fail if we were restarted and need to be unsealed
            chain = vault_pki.get_chain()
        except vault.hvac.exceptions.VaultDown:
            chain = None
        if chain:
            tls.set_chain(chain)


@when_not("is-update-status-hook")
@when_any('db.master.available', 'shared-db.available')
@when('leadership.is_leader',
      'charm.vault.ca.ready',
      'certificates.available')
@when_not('config.changed')
def publish_global_client_cert():
    """
    This is for backwards compatibility with older tls-certificate clients
    only.  Obviously, it's not good security / design to have clients sharing
    a certificate, but it seems that there are clients that depend on this
    (though some, like etcd, only block on the flag that it triggers but don't
    actually use the cert), so we have to set it for now.
    """
    if not client_approle_authorized():
        log("Vault not authorized: Skipping publish_global_client_cert",
            "WARNING")
        return
    cert_created = is_flag_set('charm.vault.global-client-cert.created')
    reissue_requested = is_flag_set('certificates.reissue.global.requested')
    tls = endpoint_from_flag('certificates.available')
    if not cert_created or reissue_requested:
        ttl = config()['default-ttl']
        max_ttl = config()['max-ttl']
        bundle = vault_pki.generate_certificate('client',
                                                'global-client',
                                                [], ttl, max_ttl)
        unitdata.kv().set('charm.vault.global-client-cert', bundle)
        set_flag('charm.vault.global-client-cert.created')
        clear_flag('certificates.reissue.global.requested')
    else:
        bundle = unitdata.kv().get('charm.vault.global-client-cert')
    tls.set_client_cert(bundle['certificate'], bundle['private_key'])


@when_not("is-update-status-hook")
@when('leadership.is_leader',
      'charm.vault.ca.ready',
      'certificates.available')
@when_any('certificates.certs.requested',
          'certificates.reissue.requested')
def create_certs():
    reissue_requested = is_flag_set('certificates.reissue.requested')
    tls = endpoint_from_flag('certificates.available')
    requests = tls.all_requests if reissue_requested else tls.new_requests
    if reissue_requested:
        log('Reissuing all certs')
    processed_applications = []
    for request in requests:
        log('Processing certificate request from {} for {}'.format(
            request.unit_name, request.common_name))
        if request.cert_type == 'application':
            cert_type = 'server'
            # When an application cert is published all units recieve the same
            # data so one need to process one request per application.
            if request.application_name in processed_applications:
                log('Already done {}'.format(request.application_name))
                continue
            else:
                processed_applications.append(request.application_name)
        else:
            cert_type = request.cert_type
        try:
            ttl = config()['default-ttl']
            max_ttl = config()['max-ttl']
            bundle = vault_pki.generate_certificate(cert_type,
                                                    request.common_name,
                                                    request.sans, ttl, max_ttl)
            request.set_cert(bundle['certificate'], bundle['private_key'])
        except vault.VaultInvalidRequest as e:
            log(str(e), level=ERROR)
            continue  # TODO: report failure back to client
    clear_flag('certificates.reissue.requested')


# Series upgrade hooks are a special case and reacting to the hook directly
# makes sense as we may not want other charm code to run
@hook('pre-series-upgrade')
def pre_series_upgrade():
    """Handler for pre-series-upgrade.
    """
    unitdata.kv().set('charm.vault.series-upgrading', True)


@hook('post-series-upgrade')
def post_series_upgrade():
    """Handler for post-series-upgrade.
    """
    unitdata.kv().set('charm.vault.series-upgrading', False)


@when_not("is-update-status-hook")
@when('leadership.is_leader',
      'charm.vault.ca.ready')
@when_not('pki.backend.tuned')
def tune_pki_backend():
    """Ensure Vault PKI backend is correctly tuned
    """
    ttl = config()['default-ttl']
    max_ttl = config()['max-ttl']
    vault_pki.tune_pki_backend(ttl=ttl, max_ttl=max_ttl)
    set_flag('pki.backend.tuned')


@when_not("is-update-status-hook")
@when_any('db.master.available', 'shared-db.available')
@when('leadership.is_leader',
      'charm.vault.ca.ready')
@when('config.set.default-ttl')
@when('config.set.max-ttl')
def tune_pki_backend_config_changed():
    if not client_approle_authorized():
        log("Vault not authorized: Skipping tune_pki_backend_config_changed",
            "WARNING")
        return
    if is_unit_paused_set():
        log("The Vault unit is paused, passing on tunning pki backend.")
        return
    if not service_running('vault'):
        set_flag('failed.to.start')
        return
    client = vault.get_client(url=vault.VAULT_LOCALHOST_URL)
    if client.is_sealed():
        log("Unable to tune pki backend, service sealed.")
    else:
        ttl = config()['default-ttl']
        max_ttl = config()['max-ttl']
        vault_pki.tune_pki_backend(ttl=ttl, max_ttl=max_ttl)
        vault_pki.update_roles(max_ttl=max_ttl)


def _action_vault_unit(f):
    """Helper used to execute actions on the vault unit.

    Note: the service name and port are not expected to change.
    """
    f(_assess_status, ["vault"], [8200])


def pause_vault_unit():
    """Pause the vault unit.

    This function is using the 'pause_unit' helper which will also
    check whether the service is well stopped and port is no longer
    listening.
    """
    _action_vault_unit(pause_unit)


def resume_vault_unit():
    """Resume the vault unit.

    This function is using the 'resume_unit' helper which will also
    check whether the service is well running and port listening.
    """
    _action_vault_unit(resume_unit)
