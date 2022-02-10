from base64 import b64decode
from subprocess import check_call

from charms.layer import status
from charms.reactive import (
    clear_flag,
    set_flag,
    when,
    when_not
)

from charmhelpers.core import hookenv, host


@when_not('cgroups.modified')
def enable_grub_cgroups():
    """
    Run script to enable cgroups
    in GRUB.  Be aware, this will
    reboot the host.

    :return: None
    """
    cfg = hookenv.config()
    if cfg.get('enable-cgroups'):
        hookenv.log('Calling enable_grub_cgroups.sh and rebooting machine.')
        check_call(['scripts/enable_grub_cgroups.sh'])
        set_flag('cgroups.modified')


@when('config.changed.custom-registry-ca')
def install_custom_ca():
    """
    Installs a configured CA cert into the system-wide location.
    """
    ca_cert = hookenv.config().get('custom-registry-ca')
    if ca_cert:
        try:
            # decode to bytes, as that's what install_ca_cert wants
            _ca = b64decode(ca_cert)
        except Exception:
            status.blocked('Invalid base64 value for custom-registry-ca config')
            return
        else:
            host.install_ca_cert(_ca, name='juju-custom-registry')
            charm = hookenv.charm_name()
            hookenv.log('Custom registry CA has been installed for {}'.format(charm))

            # manage appropriate charm flags to recycle the runtime daemon
            if charm == 'docker':
                clear_flag('docker.available')
                set_flag('docker.restart')
            elif charm == 'containerd':
                set_flag('containerd.restart')
            else:
                hookenv.log('Unknown runtime: {}. '
                            'Cannot request a service restart.'.format(charm))
