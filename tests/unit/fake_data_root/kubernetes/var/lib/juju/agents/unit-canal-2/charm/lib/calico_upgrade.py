import os
import shutil
import yaml
from subprocess import check_call, check_output, CalledProcessError
from charms.layer.canal import arch
from charms.reactive import endpoint_from_flag
from charmhelpers.core.hookenv import resource_get, status_set, log

CALICOCTL_PATH = '/opt/calicoctl'
ETCD_KEY_PATH = os.path.join(CALICOCTL_PATH, 'etcd-key')
ETCD_CERT_PATH = os.path.join(CALICOCTL_PATH, 'etcd-cert')
ETCD_CA_PATH = os.path.join(CALICOCTL_PATH, 'etcd-ca')
CALICO_UPGRADE_DIR = '/opt/calico-upgrade'
ETCD2_DATA_PATH = CALICO_UPGRADE_DIR + '/etcd2.yaml'
ETCD3_DATA_PATH = CALICO_UPGRADE_DIR + '/etcd3.yaml'


class ResourceMissing(Exception):
    pass


class DryRunFailed(Exception):
    pass


def cleanup():
    shutil.rmtree(CALICO_UPGRADE_DIR, ignore_errors=True)


def configure():
    cleanup()
    os.makedirs(CALICO_UPGRADE_DIR)

    # Extract calico-upgrade resource
    architecture = arch()
    if architecture == 'amd64':
        resource_name = 'calico-upgrade'
    else:
        resource_name = 'calico-upgrade-' + architecture
    archive = resource_get(resource_name)

    if not archive:
        message = 'Missing calico-upgrade resource'
        status_set('blocked', message)
        raise ResourceMissing(message)

    check_call(['tar', '-xvf', archive, '-C', CALICO_UPGRADE_DIR])

    # Configure calico-upgrade, etcd2 (data source)
    etcd = endpoint_from_flag('etcd.available')
    etcd_endpoints = etcd.get_connection_string()
    etcd2_data = {
        'apiVersion': 'v1',
        'kind': 'calicoApiConfig',
        'metadata': None,
        'spec': {
            'datastoreType': 'etcdv2',
            'etcdEndpoints': etcd_endpoints,
            'etcdKeyFile': ETCD_KEY_PATH,
            'etcdCertFile': ETCD_CERT_PATH,
            'etcdCACertFile': ETCD_CA_PATH
        }
    }
    with open(ETCD2_DATA_PATH, 'w') as f:
        yaml.dump(etcd2_data, f)

    # Configure calico-upgrade, etcd3 (data destination)
    etcd3_data = {
        'apiVersion': 'projectcalico.org/v3',
        'kind': 'CalicoAPIConfig',
        'metadata': None,
        'spec': {
            'datastoreType': 'etcdv3',
            'etcdEndpoints': etcd_endpoints,
            'etcdKeyFile': ETCD_KEY_PATH,
            'etcdCertFile': ETCD_CERT_PATH,
            'etcdCACertFile': ETCD_CA_PATH
        }
    }
    with open(ETCD3_DATA_PATH, 'w') as f:
        yaml.dump(etcd3_data, f)


def invoke(*args):
    cmd = [CALICO_UPGRADE_DIR + '/calico-upgrade'] + list(args)
    cmd += [
        '--apiconfigv1', ETCD2_DATA_PATH,
        '--apiconfigv3', ETCD3_DATA_PATH
    ]
    try:
        return check_output(cmd)
    except CalledProcessError as e:
        log(e.output)
        raise


def dry_run():
    output = invoke('dry-run', '--output-dir', CALICO_UPGRADE_DIR)
    if b'Successfully validated v1 to v3 conversion' not in output:
        raise DryRunFailed()


def start():
    invoke('start', '--no-prompts', '--output-dir', CALICO_UPGRADE_DIR)


def complete():
    invoke('complete', '--no-prompts')
