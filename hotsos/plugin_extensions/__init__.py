# Must include all summary plugin handlers that need to be autoregister
from . import (  # noqa: F401
    juju,
    kernel,
    kubernetes,
    landscape,
    lxd,
    maas,
    microcloud,
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
