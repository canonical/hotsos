<h1 id="tls_certificates_common.CertificateRequest">CertificateRequest</h1>

```python
CertificateRequest(self, unit, cert_type, cert_name, common_name, sans)
```

<h2 id="tls_certificates_common.CertificateRequest.application_name">application_name</h2>

Name of the application which the request came from.

:returns: Name of application
:rtype: str

<h2 id="tls_certificates_common.CertificateRequest.cert">cert</h2>


The cert published for this request, if any.

<h2 id="tls_certificates_common.CertificateRequest.cert_type">cert_type</h2>


Type of certificate, 'server' or 'client', being requested.

<h2 id="tls_certificates_common.CertificateRequest.resolve_unit_name">resolve_unit_name</h2>

```python
CertificateRequest.resolve_unit_name(unit)
```
Return name of unit associated with this request.

unit_name should be provided in the relation data to ensure
compatability with cross-model relations. If the unit name
is absent then fall back to unit_name attribute of the
unit associated with this request.

:param unit: Unit to extract name from
:type unit: charms.reactive.endpoints.RelatedUnit
:returns: Name of unit
:rtype: str

<h1 id="tls_certificates_common.Certificate">Certificate</h1>

```python
Certificate(self, cert_type, common_name, cert, key)
```

Represents a created certificate and key.

The ``cert_type``, ``common_name``, ``cert``, and ``key`` values can
be accessed either as properties or as the contents of the dict.

