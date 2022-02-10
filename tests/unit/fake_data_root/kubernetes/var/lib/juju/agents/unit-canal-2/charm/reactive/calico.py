import os
import yaml
import gzip
import traceback

from socket import gethostname
from conctl import getContainerRuntimeCtl
from subprocess import check_call, check_output, CalledProcessError, STDOUT

import calico_upgrade
from charms.layer.canal import arch
from charms.leadership import leader_get, leader_set
from charms.reactive import when, when_not, when_any, set_state, \
    remove_state, endpoint_from_flag, hook
from charms.reactive.flags import clear_flag
from charms.reactive.helpers import data_changed
from charmhelpers.core import hookenv
from charmhelpers.core.hookenv import log, resource_get, \
    unit_private_ip, is_leader, env_proxy_settings
from charmhelpers.core.host import service, service_restart
from charmhelpers.core.templating import render

from charms.layer import status

# TODO:
#   - Handle the 'stop' hook by stopping and uninstalling all the things.

os.environ['PATH'] += os.pathsep + os.path.join(os.sep, 'snap', 'bin')

try:
    CTL = getContainerRuntimeCtl()
    set_state('calico.ctl.ready')
except RuntimeError:
    log(traceback.format_exc())
    remove_state('calico.ctl.ready')

# This needs to match up with CALICOCTL_PATH in canal.py
CALICOCTL_PATH = '/opt/calicoctl'
ETCD_KEY_PATH = os.path.join(CALICOCTL_PATH, 'etcd-key')
ETCD_CERT_PATH = os.path.join(CALICOCTL_PATH, 'etcd-cert')
ETCD_CA_PATH = os.path.join(CALICOCTL_PATH, 'etcd-ca')
CALICO_UPGRADE_DIR = '/opt/calico-upgrade'


def set_http_proxy():
    """
    Check if we have any values for
    juju_http*_proxy and apply them.
    """
    juju_environment = env_proxy_settings()
    if juju_environment and not juju_environment.get('disable-juju-proxy'):
        upper = ['HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY']
        lower = list(map(str.lower, upper))
        keys = upper + lower
        for key in keys:
            from_juju = juju_environment.get(key, None)
            if from_juju:
                os.environ[key] = from_juju


@hook('upgrade-charm')
def upgrade_charm():
    remove_state('calico.binaries.installed')
    remove_state('calico.service.installed')
    remove_state('calico.pool.configured')
    remove_state('calico.image.pulled')
    remove_state('calico.npc.deployed')
    if is_leader() and not leader_get('calico-v3-data-ready'):
        leader_set({
            'calico-v3-data-migration-needed': True,
            'calico-v3-npc-cleanup-needed': True,
            'calico-v3-completion-needed': True
        })


@when_not('calico.image.pulled')
@when('calico.ctl.ready')
def pull_calico_node_image():
    image = resource_get('calico-node-image')

    if not image or os.path.getsize(image) == 0:
        status.maintenance('Pulling calico-node image')
        image = hookenv.config('calico-node-image')
        set_http_proxy()
        CTL.pull(image)
    else:
        status.maintenance('Loading calico-node image')
        unzipped = '/tmp/calico-node-image.tar'
        with gzip.open(image, 'rb') as f_in:
            with open(unzipped, 'wb') as f_out:
                f_out.write(f_in.read())
        CTL.load(unzipped)

    set_state('calico.image.pulled')


@when_any('config.changed.calico-node-image')
def repull_calico_node_image():
    remove_state('calico.image.pulled')
    remove_state('calico.service.installed')


@when('leadership.is_leader', 'leadership.set.calico-v3-data-migration-needed',
      'etcd.available', 'calico.etcd-credentials.installed')
def upgrade_v3_migrate_data():
    status.maintenance('Migrating data to Calico 3')
    try:
        calico_upgrade.configure()
        calico_upgrade.dry_run()
        calico_upgrade.start()
    except Exception:
        log(traceback.format_exc())
        message = 'Calico upgrade failed, see debug log'
        status.blocked(message)
        return
    leader_set({'calico-v3-data-migration-needed': None})


@when('leadership.is_leader')
@when_not('leadership.set.calico-v3-data-migration-needed')
def v3_data_ready():
    leader_set({'calico-v3-data-ready': True})


@when('leadership.is_leader', 'leadership.set.calico-v3-data-ready',
      'leadership.set.calico-v3-npc-cleanup-needed')
def upgrade_v3_npc_cleanup():
    status.maintenance('Cleaning up Calico 2 policy controller')

    resources = [
        ('Deployment', 'kube-system', 'calico-policy-controller'),
        ('ClusterRoleBinding', None, 'calico-policy-controller'),
        ('ClusterRole', None, 'calico-policy-controller'),
        ('ServiceAccount', 'kube-system', 'calico-policy-controller')
    ]

    for kind, namespace, name in resources:
        args = ['delete', '--ignore-not-found', kind, name]
        if namespace:
            args += ['-n', namespace]
        try:
            kubectl(*args)
        except CalledProcessError:
            log('Failed to cleanup %s %s %s' % (kind, namespace, name))
            return

    leader_set({'calico-v3-npc-cleanup-needed': None})


@when('leadership.is_leader', 'leadership.set.calico-v3-completion-needed',
      'leadership.set.calico-v3-data-ready', 'calico.binaries.installed',
      'calico.service.installed', 'calico.npc.deployed')
@when_not('leadership.set.calico-v3-npc-cleanup-needed')
def upgrade_v3_complete():
    status.maintenance('Completing Calico 3 upgrade')
    try:
        calico_upgrade.configure()
        calico_upgrade.complete()
        calico_upgrade.cleanup()
    except Exception:
        log(traceback.format_exc())
        message = 'Calico upgrade failed, see debug log'
        status.blocked(message)
        return
    leader_set({'calico-v3-completion-needed': None})


@when('leadership.set.calico-v3-data-ready')
@when_not('calico.binaries.installed')
def install_calico_binaries():
    ''' Unpack the Calico binaries. '''
    # on intel, the resource is called 'calico'; other arches have a suffix
    architecture = arch()
    if architecture == 'amd64':
        resource_name = 'calico'
    else:
        resource_name = 'calico-{}'.format(architecture)

    try:
        archive = resource_get(resource_name)
    except Exception:
        message = 'Error fetching the calico resource.'
        log(message)
        status.blocked(message)
        return

    if not archive:
        message = 'Missing calico resource.'
        log(message)
        status.blocked(message)
        return

    filesize = os.stat(archive).st_size
    if filesize < 1000000:
        message = 'Incomplete calico resource'
        log(message)
        status.blocked(message)
        return

    status.maintenance('Unpacking calico resource.')

    charm_dir = os.getenv('CHARM_DIR')
    unpack_path = os.path.join(charm_dir, 'files', 'calico')
    os.makedirs(unpack_path, exist_ok=True)
    cmd = ['tar', 'xfz', archive, '-C', unpack_path]
    log(cmd)
    check_call(cmd)

    apps = [
        {'name': 'calicoctl', 'path': CALICOCTL_PATH},
        {'name': 'calico', 'path': '/opt/cni/bin'},
        {'name': 'calico-ipam', 'path': '/opt/cni/bin'},
    ]

    for app in apps:
        unpacked = os.path.join(unpack_path, app['name'])
        app_path = os.path.join(app['path'], app['name'])
        install = ['install', '-v', '-D', unpacked, app_path]
        check_call(install)

    set_state('calico.binaries.installed')


@when('calico.binaries.installed')
@when_not('etcd.connected')
def blocked_without_etcd():
    status.blocked('Waiting for relation to etcd')


@when('etcd.tls.available')
@when_not('calico.etcd-credentials.installed')
def install_etcd_credentials(etcd):
    etcd.save_client_credentials(ETCD_KEY_PATH, ETCD_CERT_PATH, ETCD_CA_PATH)
    set_state('calico.etcd-credentials.installed')


def get_bind_address():
    ''' Returns a non-fan bind address for the cni endpoint '''
    try:
        data = hookenv.network_get('cni')
    except NotImplementedError:
        # Juju < 2.1
        return unit_private_ip()

    if 'bind-addresses' not in data:
        # Juju < 2.3
        return unit_private_ip()

    for bind_address in data['bind-addresses']:
        if bind_address['interfacename'].startswith('fan-'):
            continue
        return bind_address['addresses'][0]['address']

    # If we made it here, we didn't find a non-fan CNI bind-address, which is
    # unexpected. Let's log a message and play it safe.
    log('Could not find a non-fan bind-address. Using private-address.')
    return unit_private_ip()


@when('calico.binaries.installed', 'etcd.available',
      'calico.etcd-credentials.installed',
      'leadership.set.calico-v3-data-ready')
@when_not('calico.service.installed')
def install_calico_service():
    ''' Install the calico-node systemd service. '''
    status.maintenance('Installing calico-node service.')

    # keep track of our etcd connections so we can detect when it changes later
    etcd = endpoint_from_flag('etcd.available')
    etcd_connections = etcd.get_connection_string()
    data_changed('calico_etcd_connections', etcd_connections)
    data_changed('calico_etcd_cert', etcd.get_client_credentials())

    service_path = os.path.join(os.sep, 'lib', 'systemd', 'system',
                                'calico-node.service')
    render('calico-node.service', service_path, {
        'connection_string': etcd_connections,
        'etcd_key_path': ETCD_KEY_PATH,
        'etcd_ca_path': ETCD_CA_PATH,
        'etcd_cert_path': ETCD_CERT_PATH,
        'nodename': gethostname(),
        # specify IP so calico doesn't grab a silly one from, say, lxdbr0
        'ip': get_bind_address(),
        'calico_node_image': hookenv.config('calico-node-image'),
        'ignore_loose_rpf': hookenv.config('ignore-loose-rpf'),
        'lc_all': os.environ.get('LC_ALL', 'C.UTF-8'),
        'lang': os.environ.get('LANG', 'C.UTF-8')
    })
    check_call(['systemctl', 'daemon-reload'])
    service_restart('calico-node')
    service('enable', 'calico-node')
    set_state('calico.service.installed')


@when('config.changed.ignore-loose-rpf')
def ignore_loose_rpf_changed():
    remove_state('calico.service.installed')


@when('calico.binaries.installed', 'etcd.available',
      'calico.etcd-credentials.installed',
      'leadership.set.calico-v3-data-ready')
@when_not('calico.pool.configured')
def configure_calico_pool(etcd):
    ''' Configure Calico IP pool. '''
    status.maintenance('Configuring Calico IP pool')

    # remove unrecognized pools
    try:
        output = calicoctl('get', 'pool', '-o', 'yaml').decode('utf-8')
    except CalledProcessError:
        log('Failed to get pools')
        status.waiting('Waiting to retry calico pool configuration')
        return

    pool_data = yaml.safe_load(output)
    pools = [item['metadata']['name'] for item in pool_data['items']]
    pools_to_delete = [pool for pool in pools if pool != 'default']

    for pool in pools_to_delete:
        log('Deleting pool: %s' % pool)
        try:
            calicoctl('delete', 'pool', pool, '--skip-not-exists')
        except CalledProcessError:
            log('Failed to delete pool: %s' % pool)
            status.waiting('Waiting to retry calico pool configuration')
            return

    # configure the default pool
    config = hookenv.config()
    context = {
        'cidr': config['cidr']
    }
    render('pool.yaml', '/tmp/calico-pool.yaml', context)
    try:
        calicoctl('apply', '-f', '/tmp/calico-pool.yaml')
    except CalledProcessError:
        status.waiting('Waiting to retry calico pool configuration')
        return
    set_state('calico.pool.configured')


@when_any('config.changed.ipip', 'config.changed.nat-outgoing')
def reconfigure_calico_pool():
    ''' Reconfigure the Calico IP pool '''
    remove_state('calico.pool.configured')


@when('etcd.available', 'calico.service.installed', 'leadership.is_leader',
      'leadership.set.calico-v3-data-ready')
@when_not('calico.npc.deployed')
def deploy_network_policy_controller():
    ''' Deploy the Calico network policy controller. '''
    status.maintenance('Deploying network policy controller.')
    etcd = endpoint_from_flag('etcd.available')
    context = {
        'connection_string': etcd.get_connection_string(),
        'etcd_key_path': ETCD_KEY_PATH,
        'etcd_cert_path': ETCD_CERT_PATH,
        'etcd_ca_path': ETCD_CA_PATH,
        'calico_policy_image': hookenv.config('calico-policy-image'),
        'etcd_cert_last_modified': os.path.getmtime(ETCD_CERT_PATH)
    }
    render('policy-controller.yaml', '/tmp/policy-controller.yaml', context)
    try:
        kubectl('apply', '-f', '/tmp/policy-controller.yaml')
        set_state('calico.npc.deployed')
    except CalledProcessError as e:
        status.waiting('Waiting for kubernetes')
        log(str(e))


@when('etcd.available')
@when_any('calico.service.installed', 'calico.npc.deployed',
          'canal.cni.configured')
def ensure_etcd_connections():
    '''Ensure etcd connection strings are accurate.

    Etcd connection info is written to config files when various install/config
    handlers are run. Watch this info for changes, and when changed, remove
    relevant flags to make sure accurate config is regenerated.
    '''
    etcd = endpoint_from_flag('etcd.available')
    connection_changed = data_changed('calico_etcd_connections',
                                      etcd.get_connection_string())
    cert_changed = data_changed('calico_etcd_cert',
                                etcd.get_client_credentials())
    if connection_changed or cert_changed:
        etcd.save_client_credentials(ETCD_KEY_PATH,
                                     ETCD_CERT_PATH,
                                     ETCD_CA_PATH)
        # NB: dont bother guarding clear_flag with is_flag_set; it's safe to
        # clear an unset flag.
        clear_flag('calico.service.installed')
        clear_flag('calico.npc.deployed')

        # Canal config (from ./canal.py) is dependent on calico; if etcd
        # changed, set ourselves up to (re)configure those canal bits.
        clear_flag('canal.cni.configured')


def calicoctl(*args):
    cmd = ['/opt/calicoctl/calicoctl'] + list(args)
    etcd = endpoint_from_flag('etcd.available')
    env = os.environ.copy()
    env['ETCD_ENDPOINTS'] = etcd.get_connection_string()
    env['ETCD_KEY_FILE'] = ETCD_KEY_PATH
    env['ETCD_CERT_FILE'] = ETCD_CERT_PATH
    env['ETCD_CA_CERT_FILE'] = ETCD_CA_PATH
    try:
        return check_output(cmd, env=env, stderr=STDOUT)
    except CalledProcessError as e:
        log(e.output)
        raise


def kubectl(*args):
    cmd = ['kubectl', '--kubeconfig=/root/.kube/config'] + list(args)
    try:
        return check_output(cmd)
    except CalledProcessError as e:
        log(e.output)
        raise
