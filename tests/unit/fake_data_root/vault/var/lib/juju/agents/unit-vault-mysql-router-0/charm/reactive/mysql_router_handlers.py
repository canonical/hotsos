import charms.reactive as reactive

import charms_openstack.bus
import charms_openstack.charm as charm

import charm.openstack.mysql_router as mysql_router  # noqa

charms_openstack.bus.discover()


charm.use_defaults(
    'charm.installed',
    'config.changed',
    'update-status',
    'upgrade-charm')


@reactive.when('charm.installed')
@reactive.when('db-router.connected')
def db_router_request(db_router):
    """Send DB Router request to MySQL InnoDB Cluster.

    Using the db-router interface send connection request.

    :param db_router: DB-Router interface
    :type db_router_interface: MySQLRouterRequires object
    """
    with charm.provide_charm_instance() as instance:
        db_router.set_prefix(instance.db_prefix)
        db_router.configure_db_router(
            instance.db_router_user,
            instance.db_router_address,
            prefix=instance.db_prefix)
        # Reset on scale in
        db_router.set_or_clear_available()
        instance.assess_status()


@reactive.when('charm.installed')
@reactive.when(mysql_router.DB_ROUTER_AVAILABLE)
@reactive.when_not(mysql_router.MYSQL_ROUTER_BOOTSTRAPPED)
def bootstrap_mysqlrouter(db_router):
    """Bootstrap MySQL Router.

    :param db_router: DB-Router interface
    :type db_router_interface: MySQLRouterRequires object
    """
    with charm.provide_charm_instance() as instance:
        instance.bootstrap_mysqlrouter()
        instance.assess_status()


@reactive.when('charm.installed')
@reactive.when(mysql_router.DB_ROUTER_AVAILABLE)
@reactive.when(mysql_router.MYSQL_ROUTER_BOOTSTRAPPED)
@reactive.when_not(mysql_router.MYSQL_ROUTER_STARTED)
def start_mysqlrouter(db_router):
    """Start MySQL Router.

    :param db_router: DB-Router interface
    :type db_router_interface: MySQLRouterRequires object
    """
    with charm.provide_charm_instance() as instance:
        instance.start_mysqlrouter()
        instance.assess_status()


@reactive.when(mysql_router.MYSQL_ROUTER_STARTED)
@reactive.when(mysql_router.DB_ROUTER_AVAILABLE)
@reactive.when('shared-db.available')
def proxy_shared_db_requests(shared_db, db_router):
    """Proxy database and user requests to the MySQL InnoDB Cluster.

    Take requests from the shared-db relation and proxy them to the
    db-router relation using their respective endpoints.

    :param shared_db: Shared-DB interface
    :type shared-db: MySQLSharedProvides object
    :param db_router: DB-Router interface
    :type db_router_interface: MySQLRouterRequires object
    """
    with charm.provide_charm_instance() as instance:
        instance.proxy_db_and_user_requests(shared_db, db_router)
        instance.assess_status()


@reactive.when(mysql_router.MYSQL_ROUTER_STARTED)
@reactive.when(mysql_router.DB_ROUTER_PROXY_AVAILABLE)
@reactive.when('shared-db.available')
def proxy_shared_db_responses(shared_db, db_router):
    """Proxy database and user responses to clients.

    Take responses from the db-router relation and proxy them to the
    shared-db relation using their respective endpoints.

    :param shared_db: Shared-DB interface
    :type shared-db: MySQLSharedProvides object
    :param db_router: DB-Router interface
    :type db_router_interface: MySQLRouterRequires object
    """
    with charm.provide_charm_instance() as instance:
        instance.config_changed()
        instance.proxy_db_and_user_responses(db_router, shared_db)
        instance.assess_status()
