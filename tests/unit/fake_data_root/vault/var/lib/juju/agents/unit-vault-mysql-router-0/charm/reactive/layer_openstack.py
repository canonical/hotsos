import charms.reactive as reactive

import charmhelpers.core.hookenv as hookenv
import charmhelpers.core.unitdata as unitdata
import charmhelpers.contrib.openstack.utils as os_utils

import charms_openstack.bus
import charms_openstack.charm as charm
import charms_openstack.charm.defaults as defaults


charms_openstack.bus.discover()


@reactive.when_not('charm.installed')
@reactive.when('charms.openstack.do-default-charm.installed')
def default_install():
    """Provide a default install handler

    The instance automagically becomes the derived OpenStackCharm instance.
    The kv() key charmers.openstack-release-version' is used to cache the
    release being used for this charm.  It is determined by the
    default_select_release() function below, unless this is overridden by
    the charm author
    """
    unitdata.kv().unset(defaults.OPENSTACK_RELEASE_KEY)
    with charm.provide_charm_instance() as instance:
        instance.install()
    reactive.set_state('charm.installed')
    if hookenv.is_subordinate():
        reactive.set_state('charm.is-subordinate')


@reactive.when('config.changed',
               'charms.openstack.do-default-config.changed')
def default_config_changed():
    """Default handler for config.changed state from reactive.  Just see if
    our status has changed.  This is just to clear any errors that may have
    got stuck due to missing async handlers, etc.
    """
    with charm.provide_charm_instance() as instance:
        instance.config_changed()
        instance.assess_status()


@reactive.hook('upgrade-charm')
def default_upgrade_charm():
    """Default handler for the 'upgrade-charm' hook.
    This calls the charm.singleton.upgrade_charm() function as a default.
    """
    reactive.set_state('run-default-upgrade-charm')
    if hookenv.is_subordinate():
        reactive.set_state('charm.is-subordinate')


@reactive.when('charms.openstack.do-default-upgrade-charm',
               'run-default-upgrade-charm')
def run_default_upgrade_charm():
    with charm.provide_charm_instance() as instance:
        instance.upgrade_charm()
    reactive.remove_state('run-default-upgrade-charm')


@reactive.hook('update-status')
def default_update_status():
    """Default handler for update-status state.

    Sets the state so that the default update-status handler can be called.
    Sets the flag is-update-status-hook to indicate that the current hook is an
    update-status hook; registers an atexit handler to clear the flag at the
    end of the hook.
    """
    reactive.set_flag('run-default-update-status')
    reactive.set_flag('is-update-status-hook')

    def atexit_clear_update_status_flag():
        reactive.clear_flag('is-update-status-hook')

    hookenv.atexit(atexit_clear_update_status_flag)


@reactive.when('is-update-status-hook')
def check_really_is_update_status():
    """Clear the is-update-status-hook if the hook is not assess-status.

    This is in case the previous update-status hook execution died for some
    reason and the flag never got cleared.
    """
    if hookenv.hook_name() != 'update-status':
        reactive.clear_flag('is-update-status-hook')


@reactive.when('charms.openstack.do-default-update-status',
               'run-default-update-status')
def run_default_update_status():
    with charm.provide_charm_instance() as instance:
        instance.assess_status()
    reactive.remove_state('run-default-update-status')


@reactive.when('storage-backend.connected',
               'charms.openstack.do-default-storage-backend.connected')
def run_storage_backend():
    with charm.provide_charm_instance() as instance:
        instance.send_storage_backend_data()


# Series upgrade hooks are a special case and reacting to the hook directly
# makes sense as we may not want other charm code to run
@reactive.hook('pre-series-upgrade')
def default_pre_series_upgrade():
    """Default handler for pre-series-upgrade.
    """
    with charm.provide_charm_instance() as instance:
        instance.series_upgrade_prepare()


@reactive.hook('post-series-upgrade')
def default_post_series_upgrade():
    """Default handler for post-series-upgrade.
    """
    with charm.provide_charm_instance() as instance:
        instance.series_upgrade_complete()


@reactive.when('certificates.available',
               'charms.openstack.do-default-certificates.available')
@reactive.when_not('is-update-status-hook')
def default_request_certificates():
    """When the certificates interface is available, this default handler
    requests TLS certificates.
    """
    tls = reactive.endpoint_from_flag('certificates.available')
    with charm.provide_charm_instance() as instance:
        for cn, req in instance.get_certificate_requests().items():
            tls.add_request_server_cert(cn, req['sans'])
        tls.request_server_certs()
        instance.assess_status()


@reactive.when('charms.openstack.do-default-certificates.available')
@reactive.when_any(
    'certificates.ca.changed',
    'certificates.certs.changed')
@reactive.when_not('is-update-status-hook')
def default_configure_certificates():
    """When the certificates interface is available, this default handler
    updates on-disk certificates and switches on the TLS support.
    """
    tls = reactive.endpoint_from_flag('certificates.available')
    with charm.provide_charm_instance() as instance:
        instance.configure_tls(tls)
        # make charms.openstack required relation check happy
        reactive.set_flag('certificates.connected')
        for flag in 'certificates.ca.changed', 'certificates.certs.changed':
            if reactive.is_flag_set(flag):
                reactive.clear_flag(flag)
        instance.assess_status()


@reactive.when('charms.openstack.do-default-config-rendered')
@reactive.when_not('charm.paused', 'config.rendered')
def default_config_not_rendered():
    """Disable services until charm code has set the config.rendered state."""
    with charm.provide_charm_instance() as instance:
        instance.disable_services()
        instance.assess_status()


@reactive.when('charms.openstack.do-default-config-rendered',
               'config.rendered')
@reactive.when_not('charm.paused')
def default_config_rendered():
    """Enable services when charm code has set the config.rendered state."""
    with charm.provide_charm_instance() as instance:
        instance.enable_services()
        instance.assess_status()


@reactive.when('charm.is-subordinate')
def subordinate_maybe_publish_releases_packages_map():
    """Publish rel-pkg map on opt-in container relations if subordinate."""
    for endpoint_name in os_utils.container_scoped_relations():
        if (not reactive.is_flag_set('{}.connected'.format(endpoint_name)) or
                hookenv.hook_name() not in (
                    'upgrade-charm',
                    '{}-relation-joined'.format(endpoint_name),
                    '{}-relation-changed'.format(endpoint_name))):
            # Avoid calling into endpoint code before relation actually joined
            continue
        # Publish/Update our release package map if we are a subordinate
        # charm with endpoints that have implemented the feature
        ep = reactive.endpoint_from_name(endpoint_name)
        try:
            with charm.provide_charm_instance() as instance:
                ep.publish_releases_packages_map(
                    instance.releases_packages_map)
        except AttributeError:
            # Either the charm does not contiain interface code for the
            # endpoint or the interface implementation has not opted into
            # the requested functionality.
            pass
