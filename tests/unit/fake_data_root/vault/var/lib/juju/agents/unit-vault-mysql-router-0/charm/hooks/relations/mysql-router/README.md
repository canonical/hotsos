# Overview

MySQL Router Interface

This interface layer handles the communication between MySQL Router and a MySQL
InnoDB Cluster and facilitates proxying database requests from database
clients.

    * requires handles communication with MySQL InnoDB Cluster
    * provides handles communication with database clients

# Usage

## Requires

On the requires side, the interface handles requesting a user for MySQL Router
and also handles proxying database requests to the MySQL InnoDB cluster from
its provides side.

All requests over the mysql-router interface are prefixed using the following
pattern:

```
 {prefix}_username
 {prefix}_hostname
 {prefix}_database
```

Examples:

The mysql-router user request using the prefix, "mysqlrouter":
```
mysqlrouter_username="myr-user" mysqlrouter_hostname="192.168.1.5"
```

A proxied DB request using the prefix, "novaapi":

```
novaapi_username="nova" novaapi_hostname="192.168.1.20" novaapi_databse="nova_api"
```

The interface layer will set the following states, as appropriate:

  * `{relation_name}.connected`  The relation is established, but no data has
    yet been exchanged.
  * `{relation_name}.available`  MySQL Router has a user in the MySQL InnoDB
    Cluster.
  * `{relation_name}.available.proxy`  Proxied database requests are complete.

    Received connection information is available via the following methods:
    * `allowed_units(prefix)`
    * `database(prefix)`
    * `db_host(prefix)`
    * `hostname(prefix)`
    * `username(prefix)`
    * `password(prefix)`

Requests can be made of the MySQL InnoDB Cluster with the following methods:

For MySQL Router itself:

```python
    db_router.configure_db_router("myr-user", "192.168.1.5", "mysqlrouter")
```

For a proxied database request:

```python
    db_router.configure_proxy_db("nova_api", "nova", "192.168.1.20", "novaapi")
```


For example:

```python
from charms.reactive import when, when_not

@when('db-router.connected')
def setup_database(db_router):
    db_router.configure_db_router("myr-user", "192.168.1.5", "mysqlrouter")

@when('db-router.available')
def use_database(db_router):
    # Multiple Database requests:
    db_router.configure_proxy_db("nova", "nova", "192.168.1.20", "nova")
    db_router.configure_proxy_db("nova_api", "nova", "192.168.1.20", "novaapi")
    db_router.configure_proxy_db("nova_cell0", "nova", "192.168.1.20", "novacell0")

```

The interface will automatically determine the network space binding on the
local unit to present to the remote mysql-router server based on the name of
the relation. This can be overridden using the hostname parameter in the
configure_db_router and configure_proxy_db methods.


## Provides

The interface layer will set the following states, as appropriate:

  * `{relation_name}.connected`  The relation is established, but the client
    has not provided the database information yet.
  * `{relation_name}.available`  The requested information is complete. The DB,
    user and hostname can be created.
  * Connection information is passed back to the client with the following method:
    * `set_db_connection_info()`

For example:

```python
@when('shared-db.available')
@when_not('db-router.available.proxy')
def use_database(db_router, shared_db):
  instance.proxy_db_and_user_requests(db_router, shared_db)

@when('shared-db.available')
@when('db-router.available.proxy')
def use_database(db_router, shared_db):
  instance.proxy_db_and_user_responses(db_router, shared_db)
```

The interface will automatically determine the network space binding on the
local unit to present to the remote mysql-shared client based on the name of
the relation. This can be overridden using the db_host parameter of the
set_db_connection_info method.
