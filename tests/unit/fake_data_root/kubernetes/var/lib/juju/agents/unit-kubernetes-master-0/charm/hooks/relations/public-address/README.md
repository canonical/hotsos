# Overview

This interface layer implements a public address protocol useful for load 
balancers and their subordinates. The load balancers (providers) set their 
own public address and port, which is then available to the subordinates 
(requirers).

# Usage

## Provides

By providing the `public-address` interface, your charm is providing an HTTP 
server that can load-balance for another HTTP based service.

Your charm need only provide the address and port on which it is serving its 
content, as soon as the `{relation_name}.available` state is set:

```python
from charmhelpers.core import hookenv
@when('website.available')
def configure_website(website):
    website.set_address_port(hookenv.unit_get('public-address'), hookenv.config('port'))
```

## Requires

By requiring the `public-address` interface, your charm is consuming one or 
more HTTP servers, to load-balance a set of servers, etc.

Your charm should respond to the `{relation_name}.available` state, which
indicates that there is at least one HTTP server connected.

The `get_addresses_ports()` method returns a list of available addresses and
ports.

The return value is a list of dicts of the following form:

```python
[
    {
        'public-address': address_of_host,
        'port': port_for_host,
    },
    # ...
]
```

A trivial example of handling this interface would be:

```python
from charmhelpers.core import hookenv
@when('loadbalancer.available')
def update_reverse_proxy_config(loadbalancer):
    hosts = loadbalancer.get_addresses_ports()
    for host in hosts:
        hookenv.log('The loadbalancer for this unit is {}:{}'.format(
                host['public-address'],
                host['port']))
```
