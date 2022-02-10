import os
import subprocess
from charms import layer
from charms.reactive import hook, when_not, remove_state, set_state
from charmhelpers.core.templating import render


@hook('upgrade-charm')
def upgrade_charm():
    remove_state('cdk-service-kicker.installed')


@when_not('cdk-service-kicker.installed')
def install_cdk_service_kicker():
    ''' Installs the cdk-service-kicker service. Workaround for
    https://github.com/juju-solutions/bundle-canonical-kubernetes/issues/357
    '''
    source = 'cdk-service-kicker'
    dest = '/usr/bin/cdk-service-kicker'
    services = layer.options('cdk-service-kicker').get('services')
    context = {'services': ' '.join(services)}
    render(source, dest, context)
    os.chmod('/usr/bin/cdk-service-kicker', 0o775)

    source = 'cdk-service-kicker.service'
    dest = '/etc/systemd/system/cdk-service-kicker.service'
    context = {}
    render(source, dest, context)
    command = ['systemctl', 'enable', 'cdk-service-kicker']
    subprocess.check_call(command)

    set_state('cdk-service-kicker.installed')
