import os
import traceback
from shlex import split
from subprocess import check_output, STDOUT

from charms.reactive import set_state, remove_state, when, when_not, hook
from charms.reactive import when_any
from charms.reactive import endpoint_from_flag
from charms.templating.jinja2 import render
from charmhelpers.core import hookenv
from charmhelpers.core.hookenv import config
from charmhelpers.core.hookenv import application_version_set
from charmhelpers.core.host import service_running
from charmhelpers.contrib.charmsupport import nrpe

from charms.layer import status


# This needs to match up with CALICOCTL_PATH in calico.py
CALICOCTL_PATH = '/opt/calicoctl'
ETCD_KEY_PATH = os.path.join(CALICOCTL_PATH, 'etcd-key')
ETCD_CERT_PATH = os.path.join(CALICOCTL_PATH, 'etcd-cert')
ETCD_CA_PATH = os.path.join(CALICOCTL_PATH, 'etcd-ca')

MONITORED_SERVICES = ['flannel', 'calico-node']


@hook('upgrade-charm')
def upgrade_charm():
    remove_state('canal.cni.available')
    remove_state('canal.version.set')
    remove_state('canal.cni.configured')
    try:
        hookenv.log('Deleting /etc/cni/net.d/10-canal.conf')
        os.remove('/etc/cni/net.d/10-canal.conf')
    except FileNotFoundError as e:
        hookenv.log(e)


@hook('pre-series-upgrade')
def pre_series_upgrade():
    status.blocked('Series upgrade in progress')


@when('etcd.available', 'cni.connected', 'flannel.service.started',
      'calico.service.installed', 'calico.pool.configured')
@when_not('canal.cni.configured')
def configure_cni():
    ''' Configure Calico CNI. '''
    status.maintenance('Configuring Calico CNI')
    try:
        subnet = get_flannel_subnet()
    except FlannelSubnetNotFound:
        hookenv.log(traceback.format_exc())
        status.waiting('Waiting for Flannel')
        return
    os.makedirs('/etc/cni/net.d', exist_ok=True)
    cni = endpoint_from_flag('cni.connected')
    etcd = endpoint_from_flag('etcd.available')
    cni_config = cni.get_config()
    context = {
        'connection_string': etcd.get_connection_string(),
        'etcd_key_path': ETCD_KEY_PATH,
        'etcd_cert_path': ETCD_CERT_PATH,
        'etcd_ca_path': ETCD_CA_PATH,
        'kubeconfig_path': cni_config.get('kubeconfig_path', '/root/cdk/kubeconfig'),
        'subnet': subnet
    }
    render('10-canal.conflist', '/etc/cni/net.d/10-canal.conflist', context)
    cni.set_config(cidr=config('cidr'), cni_conf_file='10-canal.conflist')
    set_state('canal.cni.configured')


@when('flannel.binaries.installed', 'calico.binaries.installed')
@when_not('canal.version.set', 'canal.stopping')
def set_canal_version():
    ''' Surface the currently deployed version of canal to Juju '''
    # Get flannel version
    cmd = 'flanneld -version'
    output = check_output(split(cmd), stderr=STDOUT).decode('utf-8')
    if not output:
        hookenv.log('No version output from flanneld, will retry')
        return
    flannel_version = output.split('v')[-1].strip()

    # Please refer to layer-canal/versioning.md before changing this.
    calico_version = '3.10.1'

    version = '%s/%s' % (flannel_version, calico_version)
    application_version_set(version)
    set_state('canal.version.set')


def get_failing_services():
    failing_services = []
    services = ['calico-node', 'flannel']
    for service in services:
        if not service_running(service):
            failing_services.append(service)
    return failing_services


@when('flannel.service.started', 'calico.service.installed',
      'calico.pool.configured')
@when('canal.cni.configured')
def ready():
    ''' Indicate that canal is active. '''
    failing_services = get_failing_services()
    if len(failing_services) > 0:
        msg = 'Waiting for service: {}'.format(', '.join(failing_services))
        status.waiting(msg)
    else:
        try:
            status.active('Flannel subnet ' + get_flannel_subnet())
        except FlannelSubnetNotFound:
            status.waiting('Waiting for Flannel')


@hook('stop')
def stop():
    set_state('canal.stopping')


@when('flannel.service.started',
      'calico.service.installed',
      'nrpe-external-master.available')
@when_not('nrpe-external-master.initial-config')
def configure_nrpe(unused=None):
    hookenv.log('Configuring nrpe checks for services: '
                '{}'.format(MONITORED_SERVICES))
    # The current nrpe-external-master interface doesn't handle a lot of logic,
    # use the charm-helpers code for now.
    hostname = nrpe.get_nagios_hostname()
    current_unit = nrpe.get_nagios_unit_name()
    nrpe_setup = nrpe.NRPE(hostname=hostname, primary=False)
    nrpe.add_init_service_checks(nrpe_setup, MONITORED_SERVICES, current_unit)
    nrpe_setup.write()

    set_state('nrpe-external-master.initial-config')


@when_any('config.changed.nagios_context',
          'config.changed.nagios_servicegroups')
@when('nrpe-external-master.initial-config')
def update_nagios():
    configure_nrpe()


@when_not('nrpe-external-master.available')
@when('nrpe-external-master.initial-config')
def remove_nrpe_config():
    hookenv.log('Removing nrpe checks for services: '
                '{}'.format(MONITORED_SERVICES))
    hostname = nrpe.get_nagios_hostname()
    nrpe_setup = nrpe.NRPE(hostname=hostname, primary=False)

    for check in MONITORED_SERVICES:
        nrpe_setup.remove_check(shortname=check)
    nrpe_setup.write()

    remove_state('nrpe-external-master.initial-config')


def get_flannel_subnet():
    ''' Returns the flannel subnet reserved for this unit '''
    try:
        with open('/run/flannel/subnet.env') as f:
            raw_data = dict(line.strip().split('=') for line in f)
        return raw_data['FLANNEL_SUBNET']
    except FileNotFoundError as e:
        raise FlannelSubnetNotFound() from e


class FlannelSubnetNotFound(Exception):
    pass
