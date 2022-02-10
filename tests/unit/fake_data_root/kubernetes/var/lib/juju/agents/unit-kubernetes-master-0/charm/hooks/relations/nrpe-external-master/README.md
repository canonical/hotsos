# nrpe-external-master interface

Use this interface to register nagios checks in your charm layers.

## Purpose

This interface is designed to interoperate with the
[nrpe-external-master](https://jujucharms.com/nrpe-external-master) subordinate charm.

## How to use in your layers

The event handler for `nrpe-external-master.available` is called with an object
through which you can register your own custom nagios checks, when a relation
is established with `nrpe-external-master:nrpe-external-master`.

This object provides a method,

_add_check_(args, name=_check_name_, description=_description_, context=_context_, unit=_unit_)

which is called to register a nagios plugin check for your service.

All arguments are required.

*args* is a list of nagios plugin command line arguments, starting with the path to the plugin executable.

*name* is the name of the check registered in nagios

*description* is some text that describes what the check is for and what it does

*context* is the nagios context name, something that identifies your application

*unit* is `hookenv.local_unit()`

The nrpe subordinate installs `check_http`, so you can use it like this:

```
@when('nrpe-external-master.available')
def setup_nagios(nagios):
    config = hookenv.config()
    unit_name = hookenv.local_unit()
    nagios.add_check(['/usr/lib/nagios/plugins/check_http',
            '-I', '127.0.0.1', '-p', str(config['port']),
            '-e', " 200 OK", '-u', '/publickey'],
        name="check_http",
        description="Verify my awesome service is responding",
        context=config["nagios_context"],
        unit=unit_name,
    )
```
If your `nagios.add_check` defines a custom plugin, you will also need to restart the `nagios-nrpe-server` service. 

Consult the nagios documentation for more information on [how to write your own
plugins](https://assets.nagios.com/downloads/nagioscore/docs/nagioscore/4/en/pluginapi.html)
or [find one](https://www.nagios.org/projects/nagios-plugins/) that does what you need.

## Example deployment

```
$ juju deploy your-awesome-charm
$ juju deploy nrpe-external-master --config site-nagios.yaml
$ juju add-relation your-awesome-charm nrpe-external-master
```

where `site-nagios.yaml` has the necessary configuration settings for the
subordinate to connect to nagios.

