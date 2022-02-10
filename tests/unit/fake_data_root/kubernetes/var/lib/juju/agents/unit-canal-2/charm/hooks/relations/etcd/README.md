# Overview

This interface layer handles the communication with Etcd via the `etcd`
interface.

# Usage

## Requires

This interface layer will set the following states, as appropriate:

  * `{relation_name}.connected` The relation is established, but Etcd may not
  yet have provided any connection or service information.

  * `{relation_name}.available` Etcd has provided its connection string
    information, and is ready to serve as a KV store.
    The provided information can be accessed via the following methods:
      * `etcd.get_connection_string()`
      * `etcd.get_version()`
  * `{relation_name}.tls.available` Etcd has provided the connection string
    information, and the tls client credentials to communicate with it.
    The client credentials can be accessed via:
    * `{relation_name}.get_client_credentials()` returning a dictionary of
       the clinet certificate, key and CA.
    * `{relation_name}.save_client_credentials(key, cert, ca)` is a convenience
      method to save the client certificate, key and CA to files of your
      choosing.


For example, a common application for this is configuring an applications
backend key/value storage, like Docker.

```python
@when('etcd.available', 'docker.available')
def swarm_etcd_cluster_setup(etcd):
    con_string = etcd.connection_string().replace('http', 'etcd')
    opts = {}
    opts['connection_string'] = con_string
    render('docker-compose.yml', 'files/swarm/docker-compose.yml', opts)

```


## Provides

A charm providing this interface is providing the Etcd rest api service.

This interface layer will set the following states, as appropriate:

  * `{relation_name}.connected` One or more clients of any type have
    been related. The charm should call the following methods to provide the
    appropriate information to the clients:

    * `{relation_name}.set_connection_string(string, version)`
    * `{relation_name}.set_client_credentials(key, cert, ca)`

Example:

```python
@when('db.connected')
def send_connection_details(db):
    cert = leader_get('client_certificate')
    key = leader_get('client_key')
    ca = leader_get('certificate_authority')
    # Set the key, cert, and ca on the db relation
    db.set_client_credentials(key, cert, ca)

    port = hookenv.config().get('port')
    # Get all the peers participating in the cluster relation.
    addresses = cluster.get_peer_addresses()
    connections = []
    for address in addresses:
        connections.append('http://{0}:{1}'.format(address, port))
    # Set the connection string on the db relation.
    db.set_connection_string(','.join(conections))
```


# Contact Information

### Maintainer
- Charles Butler <charles.butler@canonical.com>


# Etcd

- [Etcd](https://coreos.com/etcd/) home page
- [Etcd bug trackers](https://github.com/coreos/etcd/issues)
- [Etcd Juju Charm](http://jujucharms.com/?text=etcd)
