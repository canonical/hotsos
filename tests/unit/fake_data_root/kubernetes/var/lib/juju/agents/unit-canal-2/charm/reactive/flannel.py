import os
import json
from shlex import split
from subprocess import check_output, check_call, CalledProcessError

from charms.layer.canal import arch, retry

from charms.reactive import set_state, remove_state, when, when_not, hook
from charms.reactive import endpoint_from_flag
from charms.reactive.flags import clear_flag
from charms.reactive.helpers import data_changed
from charms.templating.jinja2 import render
from charmhelpers.core.host import service_start, service_stop, service_restart
from charmhelpers.core.host import service_running, service
from charmhelpers.core.hookenv import log, resource_get, config
from charmhelpers.core.hookenv import network_get

from charms.layer import status


ETCD_PATH = '/etc/ssl/flannel'
ETCD_KEY_PATH = os.path.join(ETCD_PATH, 'client-key.pem')
ETCD_CERT_PATH = os.path.join(ETCD_PATH, 'client-cert.pem')
ETCD_CA_PATH = os.path.join(ETCD_PATH, 'client-ca.pem')


@when_not('flannel.binaries.installed')
def install_flannel_binaries():
    ''' Unpack the Flannel binaries. '''
    # on intel, the resource is called 'flannel'; other arches have a suffix
    architecture = arch()
    if architecture == 'amd64':
        resource_name = 'flannel'
    else:
        resource_name = 'flannel-{}'.format(architecture)

    try:
        archive = resource_get(resource_name)
    except Exception:
        message = 'Error fetching the flannel resource.'
        log(message)
        status.blocked(message)
        return
    if not archive:
        message = 'Missing flannel resource.'
        log(message)
        status.blocked(message)
        return
    filesize = os.stat(archive).st_size
    if filesize < 1000000:
        message = 'Incomplete flannel resource'
        log(message)
        status.blocked(message)
        return
    status.maintenance('Unpacking flannel resource.')
    charm_dir = os.getenv('CHARM_DIR')
    unpack_path = os.path.join(charm_dir, 'files', 'flannel')
    os.makedirs(unpack_path, exist_ok=True)
    cmd = ['tar', 'xfz', archive, '-C', unpack_path]
    log(cmd)
    check_call(cmd)
    apps = [
        {'name': 'flanneld', 'path': '/usr/local/bin'},
        {'name': 'etcdctl', 'path': '/usr/local/bin'}
    ]
    for app in apps:
        unpacked = os.path.join(unpack_path, app['name'])
        app_path = os.path.join(app['path'], app['name'])
        install = ['install', '-v', '-D', unpacked, app_path]
        check_call(install)
    set_state('flannel.binaries.installed')


@when('etcd.tls.available')
@when_not('flannel.etcd.credentials.installed')
def install_etcd_credentials(etcd):
    ''' Install the etcd credential files. '''
    etcd.save_client_credentials(ETCD_KEY_PATH, ETCD_CERT_PATH, ETCD_CA_PATH)
    set_state('flannel.etcd.credentials.installed')


def default_route_interface():
    ''' Returns the network interface of the system's default route '''
    default_interface = None
    cmd = ['route']
    output = check_output(cmd).decode('utf8')
    for line in output.split('\n'):
        if 'default' in line:
            default_interface = line.split(' ')[-1]
            return default_interface


def get_bind_address_interface():
    ''' Returns a non-fan bind-address interface for the cni endpoint.
    Falls back to default_route_interface() if bind-address is not available.
    '''
    try:
        data = network_get('cni')
    except NotImplementedError:
        # Juju < 2.1
        return default_route_interface()

    if 'bind-addresses' not in data:
        # Juju < 2.3
        return default_route_interface()

    for bind_address in data['bind-addresses']:
        if bind_address['interfacename'].startswith('fan-'):
            continue
        return bind_address['interfacename']

    # If we made it here, we didn't find a non-fan CNI bind-address, which is
    # unexpected. Let's log a message and play it safe.
    log('Could not find a non-fan bind-address. Using fallback interface.')
    return default_route_interface()


@when('flannel.binaries.installed', 'flannel.etcd.credentials.installed',
      'etcd.tls.available')
@when_not('flannel.service.installed')
def install_flannel_service():
    ''' Install the flannel service. '''
    status.maintenance('Installing flannel service.')

    # keep track of our etcd connections so we can detect when it changes later
    etcd = endpoint_from_flag('etcd.tls.available')
    etcd_connections = etcd.get_connection_string()
    data_changed('flannel_etcd_connections', etcd_connections)
    data_changed('flannel_etcd_cert', etcd.get_client_credentials())

    iface = config('iface') or get_bind_address_interface()
    context = {'iface': iface,
               'connection_string': etcd_connections,
               'cert_path': ETCD_PATH}
    render('flannel.service', '/lib/systemd/system/flannel.service', context)
    service('enable', 'flannel')
    set_state('flannel.service.installed')
    remove_state('flannel.service.started')


@when('config.changed.iface')
def reconfigure_flannel_service():
    ''' Handle interface configuration change. '''
    remove_state('flannel.service.installed')


@when('flannel.binaries.installed', 'flannel.etcd.credentials.installed',
      'etcd.available')
@when_not('flannel.network.configured')
def invoke_configure_network(etcd):
    ''' invoke network configuration and adjust states '''
    status.maintenance('Negotiating flannel network subnet.')
    if configure_network(etcd):
        set_state('flannel.network.configured')
        remove_state('flannel.service.started')
    else:
        status.waiting('Waiting on etcd.')


@retry(times=3, delay_secs=20)
def configure_network(etcd):
    ''' Store initial flannel data in etcd.

    Returns True if the operation completed successfully.

    '''
    data = json.dumps({
        'Network': config('cidr'),
        'Backend': {
            'Type': 'vxlan'
        }
    })
    cmd = "etcdctl "
    cmd += "--endpoint '{0}' ".format(etcd.get_connection_string())
    cmd += "--cert-file {0} ".format(ETCD_CERT_PATH)
    cmd += "--key-file {0} ".format(ETCD_KEY_PATH)
    cmd += "--ca-file {0} ".format(ETCD_CA_PATH)
    cmd += "set /coreos.com/network/config '{0}'".format(data)
    try:
        check_call(split(cmd))
        return True

    except CalledProcessError:
        log('Unexpected error configuring network. Assuming etcd not'
            ' ready. Will retry in 20s')
        return False


@when('config.changed.cidr')
def reconfigure_network():
    ''' Trigger the network configuration method. '''
    remove_state('flannel.network.configured')


@when('flannel.binaries.installed', 'flannel.service.installed',
      'flannel.network.configured')
@when_not('flannel.service.started')
def start_flannel_service():
    ''' Start the flannel service. '''
    status.maintenance('Starting flannel service.')
    if service_running('flannel'):
        service_restart('flannel')
    else:
        service_start('flannel')
    set_state('flannel.service.started')


@when_not('etcd.connected')
def halt_execution():
    ''' send a clear message to the user that we are waiting on etcd '''
    status.blocked('Waiting for etcd relation.')


@when('etcd.available', 'flannel.service.installed')
def ensure_etcd_connections():
    '''Ensure etcd connection strings are accurate.

    Etcd connection info is written to config files when various install/config
    handlers are run. Watch this data for changes, and when changed, remove
    relevant flags to make sure accurate config is regenerated.
    '''
    etcd = endpoint_from_flag('etcd.available')
    connection_changed = data_changed('flannel_etcd_connections',
                                      etcd.get_connection_string())
    cert_changed = data_changed('flannel_etcd_cert',
                                etcd.get_client_credentials())
    if connection_changed or cert_changed:
        etcd.save_client_credentials(ETCD_KEY_PATH,
                                     ETCD_CERT_PATH,
                                     ETCD_CA_PATH)
        clear_flag('flannel.service.installed')

        # Clearing the above flag will change config that the flannel
        # service depends on. Set ourselves up to (re)invoke the start handler.
        clear_flag('flannel.service.started')


@hook('upgrade-charm')
def reset_states_and_redeploy():
    ''' Remove state and redeploy '''
    remove_state('flannel.binaries.installed')
    remove_state('flannel.service.started')
    remove_state('flannel.network.configured')
    remove_state('flannel.service.installed')


@hook('stop')
def cleanup_deployment():
    ''' Terminate services, and remove the deployed bins '''
    service_stop('flannel')
    down = 'ip link set flannel.1 down'
    delete = 'ip link delete flannel.1'
    try:
        check_call(split(down))
        check_call(split(delete))
    except CalledProcessError:
        log('Unable to remove iface flannel.1')
        log('Potential indication that cleanup is not possible')
    files = ['/usr/local/bin/flanneld',
             '/lib/systemd/system/flannel',
             '/lib/systemd/system/flannel.service',
             '/run/flannel/subnet.env',
             '/usr/local/bin/flanneld',
             '/usr/local/bin/etcdctl',
             '/opt/cni/bin/flannel',
             '/opt/cni/bin/bridge',
             '/opt/cni/bin/host-local',
             '/etc/cni/net.d/10-flannel.conf',
             ETCD_KEY_PATH,
             ETCD_CERT_PATH,
             ETCD_CA_PATH]
    for f in files:
        if os.path.exists(f):
            log('Removing {}'.format(f))
            os.remove(f)
