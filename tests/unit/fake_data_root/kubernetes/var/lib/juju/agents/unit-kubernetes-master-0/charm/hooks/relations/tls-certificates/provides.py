if not __package__:
    # fix relative imports when building docs
    import sys
    __package__ = sys.modules[''].__name__

from charms.reactive import Endpoint
from charms.reactive import when, when_not
from charms.reactive import set_flag, clear_flag, toggle_flag

from .tls_certificates_common import (
    ApplicationCertificateRequest,
    CertificateRequest
)


class TlsProvides(Endpoint):
    """
    The provider's side of the interface protocol.

    The following flags may be set:

      * `{endpoint_name}.available`
        Whenever any clients are joined.

      * `{endpoint_name}.certs.requested`
        When there are new certificate requests of any kind to be processed.
        The requests can be accessed via [new_requests][].

      * `{endpoint_name}.server.certs.requested`
        When there are new server certificate requests to be processed.
        The requests can be accessed via [new_server_requests][].

      * `{endpoint_name}.client.certs.requested`
        When there are new client certificate requests to be processed.
        The requests can be accessed via [new_client_requests][].

    [Certificate]: common.md#tls_certificates_common.Certificate
    [CertificateRequest]: common.md#tls_certificates_common.CertificateRequest
    [all_requests]: provides.md#provides.TlsProvides.all_requests
    [new_requests]: provides.md#provides.TlsProvides.new_requests
    [new_server_requests]: provides.md#provides.TlsProvides.new_server_requests
    [new_client_requests]: provides.md#provides.TlsProvides.new_client_requests
    """

    @when('endpoint.{endpoint_name}.joined')
    def joined(self):
        set_flag(self.expand_name('{endpoint_name}.available'))
        toggle_flag(self.expand_name('{endpoint_name}.certs.requested'),
                    self.new_requests)
        toggle_flag(self.expand_name('{endpoint_name}.server.certs.requested'),
                    self.new_server_requests)
        toggle_flag(self.expand_name('{endpoint_name}.client.certs.requested'),
                    self.new_client_requests)
        toggle_flag(
            self.expand_name('{endpoint_name}.application.certs.requested'),
            self.new_application_requests)
        # For backwards compatibility, set the old "cert" flags as well
        toggle_flag(self.expand_name('{endpoint_name}.server.cert.requested'),
                    self.new_server_requests)
        toggle_flag(self.expand_name('{endpoint_name}.client.cert.requested'),
                    self.new_client_requests)

    @when_not('endpoint.{endpoint_name}.joined')
    def broken(self):
        clear_flag(self.expand_name('{endpoint_name}.available'))
        clear_flag(self.expand_name('{endpoint_name}.certs.requested'))
        clear_flag(self.expand_name('{endpoint_name}.server.certs.requested'))
        clear_flag(self.expand_name('{endpoint_name}.client.certs.requested'))
        clear_flag(
            self.expand_name('{endpoint_name}.application.certs.requested'))

    def set_ca(self, certificate_authority):
        """
        Publish the CA to all related applications.
        """
        for relation in self.relations:
            # All the clients get the same CA, so send it to them.
            relation.to_publish_raw['ca'] = certificate_authority

    def set_chain(self, chain):
        """
        Publish the chain of trust to all related applications.
        """
        for relation in self.relations:
            # All the clients get the same chain, so send it to them.
            relation.to_publish_raw['chain'] = chain

    def set_client_cert(self, cert, key):
        """
        Deprecated.  This is only for backwards compatibility.

        Publish a globally shared client cert and key.
        """
        for relation in self.relations:
            relation.to_publish_raw.update({
                'client.cert': cert,
                'client.key': key,
            })

    def set_server_cert(self, scope, cert, key):
        """
        Deprecated.  Use one of the [new_requests][] collections and
        `request.set_cert()` instead.

        Set the server cert and key for the request identified by `scope`.
        """
        request = self.get_server_requests()[scope]
        request.set_cert(cert, key)

    def set_server_multicerts(self, scope):
        """
        Deprecated.  Done automatically.
        """
        pass

    def add_server_cert(self, scope, cn, cert, key):
        '''
        Deprecated.  Use `request.set_cert()` instead.
        '''
        self.set_server_cert(scope, cert, key)

    def get_server_requests(self):
        """
        Deprecated.  Use the [new_requests][] or [server_requests][]
        collections instead.

        One provider can have many requests to generate server certificates.
        Return a map of all server request objects indexed by a unique
        identifier.
        """
        return {req._key: req for req in self.new_server_requests}

    @property
    def all_requests(self):
        """
        List of all requests that have been made.

        Each will be an instance of [CertificateRequest][].

        Example usage:

        ```python
        @when('certs.regen',
              'tls.certs.available')
        def regen_all_certs():
            tls = endpoint_from_flag('tls.certs.available')
            for request in tls.all_requests:
                cert, key = generate_cert(request.cert_type,
                                          request.common_name,
                                          request.sans)
                request.set_cert(cert, key)
        ```
        """
        requests = []
        for unit in self.all_joined_units:
            # handle older single server cert request
            if unit.received_raw['common_name']:
                requests.append(CertificateRequest(
                    unit,
                    'server',
                    unit.received_raw['certificate_name'],
                    unit.received_raw['common_name'],
                    unit.received['sans'],
                ))

            # handle mutli server cert requests
            reqs = unit.received['cert_requests'] or {}
            for common_name, req in reqs.items():
                requests.append(CertificateRequest(
                    unit,
                    'server',
                    common_name,
                    common_name,
                    req['sans'],
                ))

            # handle client cert requests
            reqs = unit.received['client_cert_requests'] or {}
            for common_name, req in reqs.items():
                requests.append(CertificateRequest(
                    unit,
                    'client',
                    common_name,
                    common_name,
                    req['sans'],
                ))
            # handle application cert requests
            reqs = unit.received['application_cert_requests'] or {}
            for common_name, req in reqs.items():
                requests.append(ApplicationCertificateRequest(
                    unit,
                    'application',
                    common_name,
                    common_name,
                    req['sans']
                ))
        return requests

    @property
    def new_requests(self):
        """
        Filtered view of [all_requests][] that only includes requests that
        haven't been handled.

        Each will be an instance of [CertificateRequest][].

        This collection can also be further filtered by request type using
        [new_server_requests][] or [new_client_requests][].

        Example usage:

        ```python
        @when('tls.certs.requested')
        def gen_certs():
            tls = endpoint_from_flag('tls.certs.requested')
            for request in tls.new_requests:
                cert, key = generate_cert(request.cert_type,
                                          request.common_name,
                                          request.sans)
                request.set_cert(cert, key)
        ```
        """
        return [req for req in self.all_requests if not req.is_handled]

    @property
    def new_server_requests(self):
        """
        Filtered view of [new_requests][] that only includes server cert
        requests.

        Each will be an instance of [CertificateRequest][].

        Example usage:

        ```python
        @when('tls.server.certs.requested')
        def gen_server_certs():
            tls = endpoint_from_flag('tls.server.certs.requested')
            for request in tls.new_server_requests:
                cert, key = generate_server_cert(request.common_name,
                                                 request.sans)
                request.set_cert(cert, key)
        ```
        """
        return [req for req in self.new_requests if req.cert_type == 'server']

    @property
    def new_client_requests(self):
        """
        Filtered view of [new_requests][] that only includes client cert
        requests.

        Each will be an instance of [CertificateRequest][].

        Example usage:

        ```python
        @when('tls.client.certs.requested')
        def gen_client_certs():
            tls = endpoint_from_flag('tls.client.certs.requested')
            for request in tls.new_client_requests:
                cert, key = generate_client_cert(request.common_name,
                                                 request.sans)
                request.set_cert(cert, key)
        ```
        """
        return [req for req in self.new_requests if req.cert_type == 'client']

    @property
    def new_application_requests(self):
        """
        Filtered view of [new_requests][] that only includes application cert
        requests.

        Each will be an instance of [ApplicationCertificateRequest][].

        Example usage:

        ```python
        @when('tls.application.certs.requested')
        def gen_application_certs():
            tls = endpoint_from_flag('tls.application.certs.requested')
            for request in tls.new_application_requests:
                cert, key = generate_application_cert(request.common_name,
                                                      request.sans)
                request.set_cert(cert, key)
        ```

        :returns: List of certificate requests.
        :rtype: [CertificateRequest, ]
        """
        return [req for req in self.new_requests
                if req.cert_type == 'application']

    @property
    def all_published_certs(self):
        """
        List of all [Certificate][] instances that this provider has published
        for all related applications.
        """
        return [req.cert for req in self.all_requests if req.cert]
