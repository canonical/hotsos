from lib.charms.layer.container_runtime_common import (
    get_hosts
)


def test_get_hosts():
    CONFIG = {
        'NO_PROXY': "192.168.2.1, 192.168.2.0/29, hello.com"
    }

    hosts = get_hosts(CONFIG)

    assert hosts == "192.168.2.1,192.168.2.1,\
192.168.2.2,192.168.2.3,192.168.2.4,192.168.2.5,\
192.168.2.6,hello.com"


def test_return_conf():
    CONFIG = {
        'NO_PROXY': ""
    }

    hosts = get_hosts(CONFIG)

    assert hosts == ""
