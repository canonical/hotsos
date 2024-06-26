# Must include cover all summary plugin handlers that need to be autoregister
from . import (  # noqa: F401
    juju,
    kernel,
    kubernetes,
    lxd,
    maas,
    mysql,
    openstack,
    openvswitch,
    pacemaker,
    rabbitmq,
    sosreport,
    storage,
    system,
    vault
)
