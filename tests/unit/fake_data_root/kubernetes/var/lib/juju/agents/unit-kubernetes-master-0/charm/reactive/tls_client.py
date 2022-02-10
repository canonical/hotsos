import os

from pathlib import Path
from subprocess import check_call

from charms import layer
from charms.reactive import hook
from charms.reactive import set_state, remove_state
from charms.reactive import when
from charms.reactive import set_flag, clear_flag
from charms.reactive import endpoint_from_flag
from charms.reactive.helpers import data_changed

from charmhelpers.core import hookenv, unitdata
from charmhelpers.core.hookenv import log


@when('certificates.ca.available')
def store_ca(tls):
    '''Read the certificate authority from the relation object and install
    the ca on this system.'''
    # Get the CA from the relationship object.
    certificate_authority = tls.get_ca()
    if certificate_authority:
        layer_options = layer.options('tls-client')
        ca_path = layer_options.get('ca_certificate_path')
        changed = data_changed('certificate_authority', certificate_authority)
        if ca_path:
            if changed or not os.path.exists(ca_path):
                log('Writing CA certificate to {0}'.format(ca_path))
                # ensure we have a newline at the end of the certificate.
                # some things will blow up without one.
                # See https://bugs.launchpad.net/charm-kubernetes-master/+bug/1828034
                if not certificate_authority.endswith('\n'):
                    certificate_authority += '\n'
                _write_file(ca_path, certificate_authority)
                set_state('tls_client.ca.written')
            set_state('tls_client.ca.saved')
        if changed:
            # Update /etc/ssl/certs and generate ca-certificates.crt
            install_ca(certificate_authority)


@when('certificates.server.cert.available')
def store_server(tls):
    '''Read the server certificate and server key from the relation object
    and save them to the certificate directory..'''
    server_cert, server_key = tls.get_server_cert()
    chain = tls.get_chain()
    if chain:
        server_cert = server_cert + '\n' + chain
    if server_cert and server_key:
        layer_options = layer.options('tls-client')
        cert_path = layer_options.get('server_certificate_path')
        key_path = layer_options.get('server_key_path')
        cert_changed = data_changed('server_certificate', server_cert)
        key_changed = data_changed('server_key', server_key)
        if cert_path:
            if cert_changed or not os.path.exists(cert_path):
                log('Writing server certificate to {0}'.format(cert_path))
                _write_file(cert_path, server_cert)
                set_state('tls_client.server.certificate.written')
            set_state('tls_client.server.certificate.saved')
        if key_path:
            if key_changed or not os.path.exists(key_path):
                log('Writing server key to {0}'.format(key_path))
                _write_file(key_path, server_key)
            set_state('tls_client.server.key.saved')


@when('certificates.client.cert.available')
def store_client(tls):
    '''Read the client certificate and client key from the relation object
    and copy them to the certificate directory.'''
    client_cert, client_key = tls.get_client_cert()
    chain = tls.get_chain()
    if chain:
        client_cert = client_cert + '\n' + chain
    if client_cert and client_key:
        layer_options = layer.options('tls-client')
        cert_path = layer_options.get('client_certificate_path')
        key_path = layer_options.get('client_key_path')
        cert_changed = data_changed('client_certificate', client_cert)
        key_changed = data_changed('client_key', client_key)
        if cert_path:
            if cert_changed or not os.path.exists(cert_path):
                log('Writing client certificate to {0}'.format(cert_path))
                _write_file(cert_path, client_cert)
                set_state('tls_client.client.certificate.written')
            set_state('tls_client.client.certificate.saved')
        if key_path:
            if key_changed or not os.path.exists(key_path):
                log('Writing client key to {0}'.format(key_path))
                _write_file(key_path, client_key)
            set_state('tls_client.client.key.saved')


@when('certificates.certs.changed')
def update_certs():
    tls = endpoint_from_flag('certificates.certs.changed')
    certs_paths = unitdata.kv().get('layer.tls-client.cert-paths', {})
    all_ready = True
    any_changed = False
    maps = {
        'server': tls.server_certs_map,
        'client': tls.client_certs_map,
    }

    if maps.get('client') == {}:
        log(
            'No client certs found using maps. Checking for global \
            client certificates.',
            'WARNING'
        )
        # Check for global certs,
        # Backwards compatibility https://bugs.launchpad.net/charm-kubernetes-master/+bug/1825819
        cert_pair = tls.get_client_cert()
        if cert_pair is not None:
            for client_name in certs_paths.get('client', {}).keys():
                maps.get('client').update({
                    client_name: cert_pair
                })

    chain = tls.get_chain()
    for cert_type in ('server', 'client'):
        for common_name, paths in certs_paths.get(cert_type, {}).items():
            cert_pair = maps[cert_type].get(common_name)
            if not cert_pair:
                all_ready = False
                continue
            if not data_changed('layer.tls-client.'
                                '{}.{}'.format(cert_type, common_name), cert_pair):
                continue

            cert = None
            key = None
            if type(cert_pair) is not tuple:
                if paths['crt']:
                    cert = cert_pair.cert
                if paths['key']:
                    key = cert_pair.key
            else:
                cert, key = cert_pair

            if cert:
                if chain:
                    cert = cert + '\n' + chain
                _ensure_directory(paths['crt'])
                Path(paths['crt']).write_text(cert)

            if key:
                _ensure_directory(paths['key'])
                Path(paths['key']).write_text(key)

            any_changed = True
            # clear flags first to ensure they are re-triggered if left set
            clear_flag('tls_client.{}.certs.changed'.format(cert_type))
            clear_flag('tls_client.{}.cert.{}.changed'.format(cert_type,
                                                              common_name))
            set_flag('tls_client.{}.certs.changed'.format(cert_type))
            set_flag('tls_client.{}.cert.{}.changed'.format(cert_type,
                                                            common_name))
    if all_ready:
        set_flag('tls_client.certs.saved')
    if any_changed:
        clear_flag('tls_client.certs.changed')
        set_flag('tls_client.certs.changed')
    clear_flag('certificates.certs.changed')


def install_ca(certificate_authority):
    '''Install a certificiate authority on the system by calling the
    update-ca-certificates command.'''
    if certificate_authority:
        name = hookenv.service_name()
        # Create a path to install CAs on Debian systems.
        ca_path = '/usr/local/share/ca-certificates/{0}.crt'.format(name)
        log('Writing CA certificate to {0}'.format(ca_path))
        _write_file(ca_path, certificate_authority)
        # Update the trusted CAs on this system (a time expensive operation).
        check_call(['update-ca-certificates'])
        log('Generated ca-certificates.crt for {0}'.format(name))
        set_state('tls_client.ca_installed')


@hook('upgrade-charm')
def remove_states():
    remove_state('tls_client.ca.saved')
    remove_state('tls_client.server.certificate.saved')
    remove_state('tls_client.server.key.saved')
    remove_state('tls_client.client.certificate.saved')
    remove_state('tls_client.client.key.saved')


def _ensure_directory(path):
    '''Ensure the parent directory exists creating directories if necessary.'''
    directory = os.path.dirname(path)
    if not os.path.isdir(directory):
        os.makedirs(directory)
    os.chmod(directory, 0o770)


def _write_file(path, content):
    '''Write the path to a file.'''
    _ensure_directory(path)
    with open(path, 'w') as stream:
        stream.write(content)
    os.chmod(path, 0o440)
