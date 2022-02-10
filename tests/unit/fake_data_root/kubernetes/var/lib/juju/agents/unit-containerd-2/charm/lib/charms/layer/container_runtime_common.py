import os
import shutil
import ipaddress
from pathlib import Path

from charmhelpers.core.hookenv import (
    log,
    env_proxy_settings
)


certs_dir = Path('/root/cdk')
ca_crt_path = certs_dir / 'ca.crt'
server_crt_path = certs_dir / 'server.crt'
server_key_path = certs_dir / 'server.key'
client_crt_path = certs_dir / 'client.crt'
client_key_path = certs_dir / 'client.key'


def get_hosts(config):
    """
    :param config: Dictionary
    :return: String
    """
    if config is not None:
        hosts = []
        for address in config.get('NO_PROXY', '').split(','):
            address = address.strip()
            try:
                net = ipaddress.ip_network(address)
                ip_addresses = [str(ip) for ip in net.hosts()]
                if ip_addresses == []:
                    hosts.append(address)
                else:
                    hosts += ip_addresses
            except ValueError:
                hosts.append(address)
        parsed_hosts = ','.join(hosts)
        return parsed_hosts


def merge_config(config, environment):
    """
    :param config: Dictionary
    :param environment: Dictionary
    :return: Dictionary
    """
    keys = ['HTTP_PROXY', 'HTTPS_PROXY', 'NO_PROXY']

    for key in keys:
        if config.get(key.lower(), '') == '' and \
                config.get(key, '') == '':
            value = environment.get(key) if environment.get(key, '') != '' \
                else environment.get(key.lower(), '')

            if value != '':
                config[key] = value
                config[key.lower()] = value
    # Normalize
    for key in keys:
        value = config.get(key) if config.get(key, '') != '' \
            else config.get(key.lower(), '')
        config[key] = value
        config[key.lower()] = value

    return config


def check_for_juju_https_proxy(config):
    """
    If config values are defined take precedent.

    LP: https://bugs.launchpad.net/charm-layer-docker/+bug/1831712

    :param config: Dictionary
    :return: Dictionary
    """
    environment_config = env_proxy_settings()
    charm_config = dict(config())

    if environment_config is None or \
            charm_config.get('disable-juju-proxy'):
        return charm_config

    no_proxy = get_hosts(environment_config)

    environment_config.update({
        'NO_PROXY': no_proxy,
        'no_proxy': no_proxy
    })

    return merge_config(charm_config, environment_config)


def manage_registry_certs(cert_dir, remove=False):
    """
    Add or remove TLS data for a specific registry.

    When present, the container runtime will use certificates when
    communicating with a specific registry.

    :param cert_dir: String directory to store the client certificates
    :param remove: Boolean remove cert data (defauts to add)
    :return: None
    """
    if remove:
        if os.path.isdir(cert_dir):
            log('Disabling registry TLS: {}.'.format(cert_dir))
            shutil.rmtree(cert_dir)
    else:
        os.makedirs(cert_dir, exist_ok=True)
        client_tls = {
            client_crt_path: os.path.join(cert_dir, 'client.cert'),
            client_key_path: os.path.join(cert_dir, 'client.key')
        }
        for f, link in client_tls.items():
            try:
                os.remove(link)
            except FileNotFoundError:
                pass
            log('Creating registry TLS link: {}.'.format(link))
            os.symlink(f, link)
