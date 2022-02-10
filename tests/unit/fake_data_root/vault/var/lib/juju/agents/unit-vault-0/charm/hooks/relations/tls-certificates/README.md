# Interface tls-certificates

This is a [Juju][] interface layer that enables a charm which requires TLS
certificates to relate to a charm which can provide them, such as [Vault][] or
[EasyRSA][]

To get started please read the [Introduction to PKI][] which defines some PKI
terms, concepts and processes used in this document.

# Example Usage

Let's say you have a charm which needs a server certificate for a service it
provides to other charms and a client certificate for a database it consumes
from another charm.  The charm provides its own service on the `clients`
relation endpoint, and it consumes the database on the `db` relation endpoint.

First, you must define the relation endpoint in your charm's `metadata.yaml`:

```yaml
requires:
  cert-provider:
    interface: tls-certificates
```

Next, you must ensure the interface layer is included in your `layer.yaml`:

```yaml
includes:
  - interface:tls-certificates
```

Then, in your reactive code, add the following, changing `update_certs` to
handle the certificates however your charm needs:

```python
from charmhelpers.core import hookenv, host
from charms.reactive import endpoint_from_flag


@when('cert-provider.ca.changed')
def install_root_ca_cert():
    cert_provider = endpoint_from_flag('cert-provider.ca.available')
    host.install_ca_cert(cert_provider.root_ca_cert)
    clear_flag('cert-provider.ca.changed')


@when('cert-provider.available')
def request_certificates():
    cert_provider = endpoint_from_flag('cert-provider.available')

    # get ingress info
    ingress_for_clients = hookenv.network_get('clients')['ingress-addresses']
    ingress_for_db = hookenv.network_get('db')['ingress-addresses']

    # use first ingress address as primary and any additional as SANs
    server_cn, server_sans = ingress_for_clients[0], ingress_for_clients[:1]
    client_cn, client_sans = ingress_for_db[0], ingress_for_db[:1]

    # request a single server and single client cert; note that multiple certs
    # of either type can be requested as long as they have unique common names
    cert_provider.request_server_cert(server_cn, server_sans)
    cert_provider.request_client_cert(client_cn, client_sans)


@when('cert-provider.certs.changed')
def update_certs():
    cert_provider = endpoint_from_flag('cert-provider.available')
    server_cert = cert_provider.server_certs[0]  # only requested one
    myserver.update_server_cert(server_cert.cert, server_cert.key)

    client_cert = cert_provider.client_certs[0]  # only requested one
    myclient.update_client_cert(client_cert.cert, client_cert.key)
    clear_flag('cert-provider.certs.changed')
```


# Reference

  * [Requires](docs/requires.md)
  * [Provides](docs/provides.md)

# Contact Information

Maintainer: Cory Johns &lt;Cory.Johns@canonical.com&gt;


[Juju]: https://jujucharms.com
[Vault]: https://jujucharms.com/u/openstack-charmers/vault
[EasyRSA]: https://jujucharms.com/u/containers/easyrsa
[Introduction to PKI]: https://github.com/OpenVPN/easy-rsa/blob/master/doc/Intro-To-PKI.md
