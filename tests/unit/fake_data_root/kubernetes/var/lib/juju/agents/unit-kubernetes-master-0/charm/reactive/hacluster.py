from charms import layer

from charms.reactive import hook
from charms.reactive import when, when_not, clear_flag, set_flag, is_flag_set
from charms.reactive import endpoint_from_flag

from charms.layer.kubernetes_common import get_ingress_address

from charmhelpers.core import hookenv
from charmhelpers.core import unitdata

db = unitdata.kv()


@hook('upgrade-charm')
def do_upgrade():
    # bump the services from upstart to systemd. :-/
    hacluster = endpoint_from_flag('ha.connected')
    if not hacluster:
        return

    if not is_flag_set('layer-hacluster.upgraded-systemd'):
        services = db.get('layer-hacluster.services', {'current_services': {},
                                                       'desired_services': {},
                                                       'deleted_services': {}})
        for name, service in services['current_services'].items():
            hookenv.log("changing service {} to systemd service".format(name))
            hacluster.remove_init_service(name, service)
            hacluster.add_systemd_service(name, service)

        # change any pending lsb entries to systemd
        for name, service in services['desired_services'].items():
            msg = "changing pending service {} to systemd service"
            hookenv.log(msg.format(name))
            hacluster.remove_init_service(name, service)
            hacluster.add_systemd_service(name, service)

        clear_flag('layer-hacluster.configured')
        set_flag('layer-hacluster.upgraded-systemd')


@when('ha.connected', 'layer.hacluster.services_configured')
@when_not('layer-hacluster.configured')
def configure_hacluster():
    """Configure HA resources in corosync"""
    hacluster = endpoint_from_flag('ha.connected')
    vips = hookenv.config('ha-cluster-vip').split()
    dns_record = hookenv.config('ha-cluster-dns')
    if vips and dns_record:
        set_flag('layer-hacluster.dns_vip.invalid')
        msg = "Unsupported configuration. " \
              "ha-cluster-vip and ha-cluster-dns cannot both be set",
        hookenv.log(msg)
        return
    else:
        clear_flag('layer-hacluster.dns_vip.invalid')
    if vips:
        for vip in vips:
            hacluster.add_vip(hookenv.application_name(), vip)
    elif dns_record:
        layer_options = layer.options('hacluster')
        binding_address = layer_options.get('binding_address')
        ip = get_ingress_address(binding_address)
        hacluster.add_dnsha(hookenv.application_name(), ip, dns_record,
                            'public')

    services = db.get('layer-hacluster.services', {'current_services': {},
                                                   'desired_services': {},
                                                   'deleted_services': {}})
    for name, service in services['deleted_services'].items():
        hacluster.remove_systemd_service(name, service)
    for name, service in services['desired_services'].items():
        hacluster.add_systemd_service(name, service)
        services['current_services'][name] = service

    services['deleted_services'] = {}
    services['desired_services'] = {}

    hacluster.bind_resources()
    set_flag('layer-hacluster.configured')


@when('config.changed.ha-cluster-vip',
      'ha.connected')
def update_vips():
    hacluster = endpoint_from_flag('ha.connected')
    config = hookenv.config()
    original_vips = set(config.previous('ha-cluster-vip').split())
    new_vips = set(config['ha-cluster-vip'].split())
    old_vips = original_vips - new_vips

    for vip in old_vips:
        hacluster.remove_vip(hookenv.application_name(), vip)

    clear_flag('layer-hacluster.configured')


@when('config.changed.ha-cluster-dns',
      'ha.connected')
def update_dns():
    hacluster = endpoint_from_flag('ha.connected')
    config = hookenv.config()
    original_dns = set(config.previous('ha-cluster-dns').split())
    new_dns = set(config['ha-cluster-dns'].split())
    old_dns = original_dns - new_dns

    for dns in old_dns:
        hacluster.remove_dnsha(hookenv.application_name, 'public')

    clear_flag('layer-hacluster.configured')
