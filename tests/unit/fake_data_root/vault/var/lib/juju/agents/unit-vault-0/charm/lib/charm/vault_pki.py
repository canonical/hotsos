import hvac

import charmhelpers.contrib.network.ip as ch_ip
import charmhelpers.core.hookenv as hookenv

from . import vault

CHARM_PKI_MP = "charm-pki-local"
CHARM_PKI_ROLE = "local"
CHARM_PKI_ROLE_CLIENT = "local-client"


def configure_pki_backend(client, name, ttl=None, max_ttl=None):
    """Ensure a pki backend is enabled

    :param client: Vault client
    :type client: hvac.Client
    :param name: Name of backend to enable
    :type name: str
    :param ttl: TTL
    :type ttl: str
    """
    if not vault.is_backend_mounted(client, name):
        client.enable_secret_backend(
            backend_type='pki',
            description='Charm created PKI backend',
            mount_point=name,
            # Default ttl to 10 years
            config={
                'default_lease_ttl': ttl or '8759h',
                'max_lease_ttl': max_ttl or '87600h'})


def disable_pki_backend():
    """Ensure a pki backend is disabled
    """
    client = vault.get_local_client()
    if vault.is_backend_mounted(client, CHARM_PKI_MP):
        client.delete('{}/root'.format(CHARM_PKI_MP))
        client.delete('{}/roles/{}'.format(CHARM_PKI_MP,
                                           CHARM_PKI_ROLE_CLIENT))
        client.delete('{}/roles/{}'.format(CHARM_PKI_MP,
                                           CHARM_PKI_ROLE))
        client.disable_secret_backend(CHARM_PKI_MP)


def tune_pki_backend(ttl=None, max_ttl=None):
    """Assert tuning options for Charm PKI backend

    :param ttl: TTL
    :type ttl: str
    """
    client = vault.get_local_client()
    if vault.is_backend_mounted(client, CHARM_PKI_MP):
        client.tune_secret_backend(
            backend_type='pki',
            mount_point=CHARM_PKI_MP,
            default_lease_ttl=ttl or '8759h',
            max_lease_ttl=max_ttl or '87600h')


def is_ca_ready(client, name, role):
    """Check if CA is ready for use

    :returns: Whether CA is ready
    :rtype: bool
    """
    return client.read('{}/roles/{}'.format(name, role)) is not None


def get_chain(name=None):
    """Check if CA is ready for use

    :returns: Whether CA is ready
    :rtype: bool
    """
    client = vault.get_local_client()
    if not name:
        name = CHARM_PKI_MP
    return client.read('{}/cert/ca_chain'.format(name))['data']['certificate']


def get_ca():
    """Get the root CA certificate.

    :returns: Root CA certificate
    :rtype: str
    """
    return hookenv.leader_get('root-ca')


def generate_certificate(cert_type, common_name, sans, ttl, max_ttl):
    """
    Create a certificate and key for the given CN and SANs, if requested.

    May raise VaultNotReady if called too early, or VaultInvalidRequest if
    something is wrong with the request.

    :param request: Certificate request from the tls-certificates interface.
    :type request: CertificateRequest
    :returns: The newly created cert, issuing ca and key
    :rtype: tuple
    """
    client = vault.get_local_client()
    configure_pki_backend(client, CHARM_PKI_MP, ttl, max_ttl)
    if not is_ca_ready(client, CHARM_PKI_MP, CHARM_PKI_ROLE):
        raise vault.VaultNotReady("CA not ready")
    role = None
    if cert_type == 'server':
        role = CHARM_PKI_ROLE
    elif cert_type == 'client':
        role = CHARM_PKI_ROLE_CLIENT
    else:
        raise vault.VaultInvalidRequest('Unsupported cert_type: '
                                        '{}'.format(cert_type))
    config = {
        'common_name': common_name,
    }
    if sans:
        ip_sans, alt_names = sort_sans(sans)
        if ip_sans:
            config['ip_sans'] = ','.join(ip_sans)
        if alt_names:
            config['alt_names'] = ','.join(alt_names)
    try:
        response = client.write('{}/issue/{}'.format(CHARM_PKI_MP, role),
                                **config)
        if not response['data']:
            raise vault.VaultError(response.get('warnings', 'unknown error'))
    except hvac.exceptions.InvalidRequest as e:
        raise vault.VaultInvalidRequest(str(e)) from e
    return response['data']


def get_csr(ttl=None, common_name=None, locality=None,
            country=None, province=None,
            organization=None, organizational_unit=None):
    """Generate a csr for the vault Intermediate Authority

    Depending on the configuration of the CA signing this CR some of the
    fields embedded in the CSR may have to match the CA.

    :param ttl: TTL
    :type ttl: string
    :param country: The C (Country) values in the subject field of the CSR
    :type country: string
    :param province: The ST (Province) values in the subject field of the CSR.
    :type province: string
    :param organization: The O (Organization) values in the subject field of
                         the CSR
    :type organization: string
    :param organizational_unit: The OU (OrganizationalUnit) values in the
                                subject field of the CSR.
    :type organizational_unit: string
    :param common_name: The CN (Common_Name) values in the
                                subject field of the CSR.
    :param locality: The L (Locality) values in the
                                subject field of the CSR.
    :returns: Certificate signing request
    :rtype: string
    """
    client = vault.get_local_client()
    configure_pki_backend(client, CHARM_PKI_MP)
    config = {
        #  Year - 1 hour
        'ttl': ttl or '87599h',
        'country': country,
        'province': province,
        'ou': organizational_unit,
        'organization': organization,
        'common_name': common_name or ("Vault Intermediate Certificate "
                                       "Authority " "({})".format(CHARM_PKI_MP)
                                       ),
        'locality': locality}
    config = {k: v for k, v in config.items() if v}
    csr_info = client.write(
        '{}/intermediate/generate/internal'.format(CHARM_PKI_MP),
        **config)
    if not csr_info['data']:
        raise vault.VaultError(csr_info.get('warnings', 'unknown error'))
    return csr_info['data']['csr']


def upload_signed_csr(pem, allowed_domains, allow_subdomains=True,
                      enforce_hostnames=False, allow_any_name=True,
                      max_ttl=None):
    """Upload signed csr to intermediate pki

    :param pem: signed csr in pem format
    :type pem: string
    :param allow_subdomains: Specifies if clients can request certificates with
                             CNs that are subdomains of the CNs:
    :type allow_subdomains: bool
    :param enforce_hostnames: Specifies if only valid host names are allowed
                              for CNs, DNS SANs, and the host part of email
                              addresses.
    :type enforce_hostnames: bool
    :param allow_any_name: Specifies if clients can request any CN
    :type allow_any_name: bool
    :param max_ttl: Specifies the maximum Time To Live
    :type max_ttl: str
    """
    client = vault.get_local_client()
    # Set the intermediate certificate authorities signing certificate to the
    # signed certificate.
    # (hvac module doesn't expose a method for this, hence the _post call)
    client._post(
        'v1/{}/intermediate/set-signed'.format(CHARM_PKI_MP),
        json={'certificate': pem.rstrip()})
    # Generated certificates can have the CRL location and the location of the
    # issuing certificate encoded.
    addr = vault.get_access_address()
    client.write(
        '{}/config/urls'.format(CHARM_PKI_MP),
        issuing_certificates="{}/v1/{}/ca".format(addr, CHARM_PKI_MP),
        crl_distribution_points="{}/v1/{}/crl".format(addr, CHARM_PKI_MP)
    )
    # Configure a role which maps to a policy for accessing this pki
    if not max_ttl:
        max_ttl = '87598h'
    write_roles(client,
                allow_any_name=allow_any_name,
                allowed_domains=allowed_domains,
                allow_subdomains=allow_subdomains,
                enforce_hostnames=enforce_hostnames,
                max_ttl=max_ttl,
                client_flag=True)


def generate_root_ca(ttl='87599h', allow_any_name=True, allowed_domains=None,
                     allow_bare_domains=False, allow_subdomains=False,
                     allow_glob_domains=True, enforce_hostnames=False,
                     max_ttl='87598h'):
    """Configure Vault to generate a self-signed root CA.

    :param ttl: TTL of the root CA certificate
    :type ttl: string
    :param allow_any_name: Specifies if clients can request certs for any CN.
    :type allow_any_name: bool
    :param allow_any_name: List of CNs for which clients can request certs.
    :type allowed_domains: list
    :param allow_bare_domains: Specifies if clients can request certs for CNs
                               exactly matching those in allowed_domains.
    :type allow_bare_domains: bool
    :param allow_subdomains: Specifies if clients can request certificates with
                             CNs that are subdomains of those in
                             allowed_domains, including wildcard subdomains.
    :type allow_subdomains: bool
    :param allow_glob_domains: Specifies whether CNs in allowed-domains can
                               contain glob patterns (e.g.,
                               'ftp*.example.com'), in which case clients will
                               be able to request certificates for any CN
                               matching the glob pattern.
    :type allow_glob_domains: bool
    :param enforce_hostnames: Specifies if only valid host names are allowed
                              for CNs, DNS SANs, and the host part of email
                              addresses.
    :type enforce_hostnames: bool
    :param max_ttl: Specifies the maximum Time To Live for generated certs.
    :type max_ttl: str
    """
    client = vault.get_local_client()
    configure_pki_backend(client, CHARM_PKI_MP)
    if is_ca_ready(client, CHARM_PKI_MP, CHARM_PKI_ROLE):
        raise vault.VaultError('PKI CA already configured')
    config = {
        'common_name': ("Vault Root Certificate Authority "
                        "({})".format(CHARM_PKI_MP)),
        'ttl': ttl,
    }
    csr_info = client.write(
        '{}/root/generate/internal'.format(CHARM_PKI_MP),
        **config)
    if not csr_info['data']:
        raise vault.VaultError(csr_info.get('warnings', 'unknown error'))
    cert = csr_info['data']['certificate']
    # Generated certificates can have the CRL location and the location of the
    # issuing certificate encoded.
    addr = vault.get_access_address()
    client.write(
        '{}/config/urls'.format(CHARM_PKI_MP),
        issuing_certificates="{}/v1/{}/ca".format(addr, CHARM_PKI_MP),
        crl_distribution_points="{}/v1/{}/crl".format(addr, CHARM_PKI_MP)
    )

    write_roles(client,
                allow_any_name=allow_any_name,
                allowed_domains=allowed_domains,
                allow_bare_domains=allow_bare_domains,
                allow_subdomains=allow_subdomains,
                allow_glob_domains=allow_glob_domains,
                enforce_hostnames=enforce_hostnames,
                max_ttl=max_ttl,
                client_flag=True)
    return cert


def sort_sans(sans):
    """
    Split SANs into IP SANs and name SANs

    :param sans: List of SANs
    :type sans: list
    :returns: List of IP SANs and list of name SANs
    :rtype: ([], [])
    """
    ip_sans = {s for s in sans if ch_ip.is_ip(s)}
    alt_names = set(sans).difference(ip_sans)
    return sorted(list(ip_sans)), sorted(list(alt_names))


def write_roles(client, **kwargs):
    # Configure a role for using this PKI to issue server certs
    client.write(
        '{}/roles/{}'.format(CHARM_PKI_MP, CHARM_PKI_ROLE),
        server_flag=True,
        **kwargs)
    # Configure a role for using this PKI to issue client-only certs
    client.write(
        '{}/roles/{}'.format(CHARM_PKI_MP, CHARM_PKI_ROLE_CLIENT),
        server_flag=False,  # client certs cannot be used as server certs
        **kwargs)


def update_roles(**kwargs):
    client = vault.get_local_client()
    # local and local-client contain the same data except for server_flag,
    # so we only need to read one, but update both
    local = client.read(
        '{}/roles/{}'.format(CHARM_PKI_MP, CHARM_PKI_ROLE))['data']
    # the reason we handle as kwargs here is because updating n-1 fields
    # causes all the others to reset. Therefore we always need to read what
    # the current values of all fields are, and apply all of them as well
    # so they are not reset. In case of new fields are added in the future,
    # this code makes sure that they are not reset automatically (if set
    # somewhere else in code) when this function is invoked.
    local.update(**kwargs)
    del local['server_flag']
    write_roles(client, **local)
