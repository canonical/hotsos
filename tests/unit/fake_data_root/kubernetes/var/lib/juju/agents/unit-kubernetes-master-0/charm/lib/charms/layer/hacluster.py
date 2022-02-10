from charms.reactive import clear_flag, set_flag
from charmhelpers.core import unitdata

db = unitdata.kv()


def add_service_to_hacluster(name, service_name):
    """Adds a service to be monitored under HAcluster.
       Takes a name for this entry and a service_name,
       which is the name used by systemd/initd to identify
       the service.
    """
    services = db.get('layer-hacluster.services', {'current_services': {},
                                                   'desired_services': {},
                                                   'deleted_services': {}})
    if name not in services['current_services']:
        services['desired_services'][name] = service_name
    db.set('layer-hacluster.services', services)
    clear_flag('layer-hacluster.configured')
    set_flag('layer.hacluster.services_configured')


def remove_service_from_hacluster(name, service_name):
    """Removes a service to be monitored under HAcluster.
       Takes a name for this entry and a service_name,
       which is the name used by systemd/initd to identify
       the service.
    """
    services = db.get('layer-hacluster.services', {'current_services': {},
                                                   'desired_services': {},
                                                   'deleted_services': {}})
    if name in services['current_services']:
        services['deleted_services'][name] = service_name

    if name in services['desired_services']:
        del services['desired_services'][name]

    db.set('layer-hacluster.services', services)
    clear_flag('layer-hacluster.configured')
