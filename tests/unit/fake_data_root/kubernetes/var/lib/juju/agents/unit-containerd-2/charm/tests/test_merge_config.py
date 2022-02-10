from lib.charms.layer.container_runtime_common import (
    merge_config
)


def test_get_hosts():
    CONFIG = {
        'NO_PROXY': '192.168.2.1, 192.168.2.0/29, hello.com',
        'https_proxy': 'https://hop.proxy',
        'HTTP_PROXY': '',

    }
    ENVIRONMENT = {
        'HTTPS_PROXY': 'https://proxy.hop',
        'HTTP_PROXY': 'http://proxy.hop',
        'no_proxy': 'not tha proxy'
    }

    merged = merge_config(CONFIG, ENVIRONMENT)

    assert merged == {
        'NO_PROXY': '192.168.2.1, 192.168.2.0/29, hello.com',
        'HTTPS_PROXY': 'https://hop.proxy',
        'HTTP_PROXY': 'http://proxy.hop',
        'no_proxy': '192.168.2.1, 192.168.2.0/29, hello.com',
        'https_proxy': 'https://hop.proxy',
        'http_proxy': 'http://proxy.hop'
    }


def test_get_hosts_no_local_conf():
    CONFIG = {
        'NO_PROXY': '',
        'https_proxy': '',
        'HTTP_PROXY': '',
    }
    ENVIRONMENT = {
        'HTTPS_PROXY': 'https://proxy.hop',
        'HTTP_PROXY': 'http://proxy.hop',
        'no_proxy': 'not tha proxy'
    }

    merged = merge_config(CONFIG, ENVIRONMENT)

    assert merged == {
        'HTTPS_PROXY': 'https://proxy.hop',
        'HTTP_PROXY': 'http://proxy.hop',
        'NO_PROXY': 'not tha proxy',
        'https_proxy': 'https://proxy.hop',
        'http_proxy': 'http://proxy.hop',
        'no_proxy': 'not tha proxy'
    }


def test_get_hosts_no_env_conf():
    ENVIRONMENT = {
        'NO_PROXY': '',
        'HTTPS_PROXY': '',
        'HTTP_PROXY': '',
    }
    CONFIG = {
        'HTTPS_PROXY': 'https://proxy.hop',
        'HTTP_PROXY': 'http://proxy.hop',
        'no_proxy': 'not tha proxy'
    }

    merged = merge_config(CONFIG, ENVIRONMENT)

    assert merged == {
        'HTTPS_PROXY': 'https://proxy.hop',
        'HTTP_PROXY': 'http://proxy.hop',
        'NO_PROXY': 'not tha proxy',
        'no_proxy': 'not tha proxy',
        'https_proxy': 'https://proxy.hop',
        'http_proxy': 'http://proxy.hop',
    }
