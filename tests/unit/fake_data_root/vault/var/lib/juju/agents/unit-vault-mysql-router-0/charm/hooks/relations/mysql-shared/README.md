# Overview

This interface layer handles the communication with MySQL via the `mysql-shared`
interface protocol.

# Usage

## Requires

The interface layer will set the following states, as appropriate:

  * `{relation_name}.connected`  The relation is established, but MySQL has not
    been provided the database information.
  * `{relation_name}.available`  MySQL is ready for use.  You can get the base
    connection information via the following methods:
    * `allowed_units()`
    * `database()`
    * `db_host()`
    * `hostname()`
    * `username()`
    * `password()`
  * `{relation_name}.available.access_network`  MySQL access network is ready
    for use.  You can get this optional connection information via the following
    method:
    * `access_network()`
  * `{relation_name}.available.ssl`  MySQL ssl data is ready for use.  You can
    get this optional connection information via the following methods:
    * `ssl_ca()`
    * `ssl_cert()`
    * `ssl_key()`

For example:

```python
from charmhelpers.core.hookenv import log, status_set, unit_get
from charms.reactive import when, when_not


@when('database.connected')
def setup_database(database):
    database.configure('mydatabase', 'myusername', prefix="first")
    database.configure('mydatabase2', 'myusername2', prefix="second")

@when('database.available')
def use_database(database):
    # base data provided by our charm layer
    log("first_database=%s" % database.database("first"))
    log("first_username=%s" % database.username("first"))
    log("first_hostname=%s" % database.hostname("first"))
    log("second_database=%s" % database.database("second"))
    log("second_username=%s" % database.username("second"))
    log("second_hostname=%s" % database.hostname("second"))

    # base data provided by mysql
    log("db_host=%s" % database.db_host())
    log("first_password=%s" % database.password("first"))
    log("first_allowed_units=%s" % database.allowed_units("first"))
    log("second_password=%s" % database.password("second"))
    log("second_allowed_units=%s" % database.allowed_units("second"))

@when('database.available.access_network')
def use_database_access_network(database):
    # optional data provided by mysql
    log("access-network=%s" % database.access_network())

@when('database.available.ssl')
def use_database_ssl(database):
    # optional data provided by mysql
    log("ssl_ca=%s" % database.ssl_ca())
    log("ssl_cert=%s" % database.ssl_cert())
    log("ssl_key=%s" % database.ssl_key())

@when('database.connected')
@when_not('database.available')
def waiting_mysql(database):
    status_set('waiting', 'Waiting for MySQL')

@when('database.connected', 'database.available')
def unit_ready(database):
    status_set('active', 'Unit is ready')
```

In Juju 2.0 environments, the interface will automatically determine the network
space binding on the local unit to present to the remote mysql-shared service
based on the name of the relation.  In older Juju versions, the private-address
of the unit will be used instead.  This can be overridden using the hostname
parameter of the configure method.

```python
@when('database.connected')
def setup_database(database):
    database.configure('mydatabase', 'myusername', hostname='hostname.override')
```

## Provides

The interface layer will set the following states, as appropriate:

  * `{relation_name}.connected`  The relation is established, but the client
    has not provided the database information yet.
  * `{relation_name}.available`  The requested information is complete. The DB,
    user and hostname can be created.
  * connection information is passed back to the client with the following method:
    * `set_db_connection_info()`

For example:

```python
@reactive.when('leadership.is_leader')
@reactive.when('leadership.set.cluster-instances-clustered')
@reactive.when('shared-db.available')
def shared_db_respond(shared_db):
    with charm.provide_charm_instance() as instance:
        instance.create_databases_and_users(shared_db)
        instance.assess_status()
```

The interface will automatically determine the network space binding on the
local unit to present to the remote mysql-shared client based on the name of
the relation. This can be overridden using the db_host parameter of the
set_db_connection_info method.
