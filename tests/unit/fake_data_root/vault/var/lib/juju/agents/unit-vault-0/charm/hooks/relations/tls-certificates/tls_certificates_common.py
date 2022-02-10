from charms.reactive import clear_flag, is_data_changed, data_changed


class CertificateRequest(dict):
    def __init__(self, unit, cert_type, cert_name, common_name, sans):
        self._unit = unit
        self._cert_type = cert_type
        super().__init__({
            'certificate_name': cert_name,
            'common_name': common_name,
            'sans': sans,
        })

    @property
    def _key(self):
        return '.'.join((self._unit.relation.relation_id,
                         self.unit_name,
                         self.common_name))

    def resolve_unit_name(self, unit):
        """Return name of unit associated with this request.

        unit_name should be provided in the relation data to ensure
        compatability with cross-model relations. If the unit name
        is absent then fall back to unit_name attribute of the
        unit associated with this request.

        :param unit: Unit to extract name from
        :type unit: charms.reactive.endpoints.RelatedUnit
        :returns: Name of unit
        :rtype: str
        """
        unit_name = unit.received_raw['unit_name']
        if not unit_name:
            unit_name = unit.unit_name
        return unit_name

    @property
    def unit_name(self):
        """Name of this unit.

        :returns: Name of unit
        :rtype: str
        """
        return self.resolve_unit_name(unit=self._unit).replace('/', '_')

    @property
    def application_name(self):
        """Name of the application which the request came from.

        :returns: Name of application
        :rtype: str
        """
        return self.resolve_unit_name(unit=self._unit).split('/')[0]

    @property
    def cert_type(self):
        """
        Type of certificate, 'server' or 'client', being requested.
        """
        return self._cert_type

    @property
    def cert_name(self):
        return self['certificate_name']

    @property
    def common_name(self):
        return self['common_name']

    @property
    def sans(self):
        return self['sans']

    @property
    def _publish_key(self):
        if self.cert_type == 'server':
            return '{}.processed_requests'.format(self.unit_name)
        elif self.cert_type == 'client':
            return '{}.processed_client_requests'.format(self.unit_name)
        raise ValueError('Unknown cert_type: {}'.format(self.cert_type))

    @property
    def _server_cert_key(self):
        return '{}.server.cert'.format(self.unit_name)

    @property
    def _server_key_key(self):
        return '{}.server.key'.format(self.unit_name)

    @property
    def _is_top_level_server_cert(self):
        return (self.cert_type == 'server' and
                self.common_name == self._unit.received_raw['common_name'])

    @property
    def cert(self):
        """
        The cert published for this request, if any.
        """
        cert, key = None, None
        if self._is_top_level_server_cert:
            tpr = self._unit.relation.to_publish_raw
            cert = tpr[self._server_cert_key]
            key = tpr[self._server_key_key]
        else:
            tp = self._unit.relation.to_publish
            certs_data = tp.get(self._publish_key, {})
            cert_data = certs_data.get(self.common_name, {})
            cert = cert_data.get('cert')
            key = cert_data.get('key')
        if cert and key:
            return Certificate(self.cert_type, self.common_name, cert, key)
        return None

    @property
    def is_handled(self):
        has_cert = self.cert is not None
        same_sans = not is_data_changed(self._key,
                                        sorted(set(self.sans or [])))
        return has_cert and same_sans

    def set_cert(self, cert, key):
        rel = self._unit.relation
        if self._is_top_level_server_cert:
            # backwards compatibility; if this is the cert that was requested
            # as a single server cert, set it in the response as the single
            # server cert
            rel.to_publish_raw.update({
                self._server_cert_key: cert,
                self._server_key_key: key,
            })
        else:
            data = rel.to_publish.get(self._publish_key, {})
            data[self.common_name] = {
                'cert': cert,
                'key': key,
            }
            rel.to_publish[self._publish_key] = data
        if not rel.endpoint.new_server_requests:
            clear_flag(rel.endpoint.expand_name('{endpoint_name}.server'
                                                '.cert.requested'))
        if not rel.endpoint.new_requests:
            clear_flag(rel.endpoint.expand_name('{endpoint_name}.'
                                                'certs.requested'))
        data_changed(self._key, sorted(set(self.sans or [])))


class ApplicationCertificateRequest(CertificateRequest):
    """
    A request for an application consistent certificate.

    This is a request for a certificate that works for all units of an
    application. All sans and cns are added together to produce one
    certificate and the same certificate and key are sent to all the
    units of an application. Only one ApplicationCertificateRequest
    is needed per application.
    """

    @property
    def _key(self):
        """Key to identify this cert.

        :returns: cert key
        :rtype: str
        """
        return '{}.{}'.format(self._unit.relation.relation_id, 'app_cert')

    @property
    def cert(self):
        """
        The cert published for this request, if any.

        :returns: Certificate
        :rtype: Certificate or None
        """
        cert, key = None, None
        tp = self._unit.relation.to_publish
        certs_data = tp.get(self._publish_key, {})
        cert_data = certs_data.get('app_data', {})
        cert = cert_data.get('cert')
        key = cert_data.get('key')
        if cert and key:
            return Certificate(self.cert_type, self.common_name, cert, key)
        return None

    @property
    def is_handled(self):
        """Whether the certificate has been handled.

        :returns: If the cert has been handled
        :rtype: bool
        """
        has_cert = self.cert is not None
        same_sans = not is_data_changed(self._key,
                                        sorted(set(self.sans or [])))
        return has_cert and same_sans

    @property
    def sans(self):
        """Generate a list of all sans from all units of application

        Examine all units of the application and compile a list of
        all sans. CNs are treated as addition san entries.

        :returns: List of sans
        :rtype: List[str]
        """
        _sans = []
        for unit in self._unit.relation.units:
            reqs = unit.received['application_cert_requests'] or {}
            for cn, req in reqs.items():
                _sans.append(cn)
                _sans.extend(req['sans'])
        return sorted(list(set(_sans)))

    @property
    def _request_key(self):
        """Key used to request cert

        :returns: Key used to request cert
        :rtype: str
        """
        return 'application_cert_requests'

    def derive_publish_key(self, unit=None):
        """Derive the application cert publish key for a unit.

        :param unit: Unit to extract name from
        :type unit: charms.reactive.endpoints.RelatedUnit
        :returns: publish key
        :rtype: str
        """
        if not unit:
            unit = self._unit
        unit_name = self.resolve_unit_name(unit).replace('/', '_')
        return '{}.processed_application_requests'.format(unit_name)

    @property
    def _publish_key(self):
        """Key used to publish cert

        :returns: Key used to publish cert
        :rtype: str
        """
        return self.derive_publish_key(unit=self._unit)

    def set_cert(self, cert, key):
        """Send the cert and key to all units of the application

        :param cert: TLS Certificate
        :type cert: str
        :param key: TLS Private Key
        :type cert: str
        """
        rel = self._unit.relation
        for unit in self._unit.relation.units:
            pub_key = self.derive_publish_key(unit=unit)
            data = rel.to_publish.get(
                pub_key,
                {})
            data['app_data'] = {
                'cert': cert,
                'key': key,
            }
            rel.to_publish[pub_key] = data
        if not rel.endpoint.new_application_requests:
            clear_flag(rel.endpoint.expand_name(
                '{endpoint_name}.application.certs.requested'))
        data_changed(self._key, sorted(set(self.sans or [])))


class Certificate(dict):
    """
    Represents a created certificate and key.

    The ``cert_type``, ``common_name``, ``cert``, and ``key`` values can
    be accessed either as properties or as the contents of the dict.
    """
    def __init__(self, cert_type, common_name, cert, key):
        super().__init__({
            'cert_type': cert_type,
            'common_name': common_name,
            'cert': cert,
            'key': key,
        })

    @property
    def cert_type(self):
        return self['cert_type']

    @property
    def common_name(self):
        return self['common_name']

    @property
    def cert(self):
        return self['cert']

    @property
    def key(self):
        return self['key']
