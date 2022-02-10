<h1 id="provides">provides</h1>


<h1 id="provides.TlsProvides">TlsProvides</h1>

```python
TlsProvides(self, endpoint_name, relation_ids=None)
```

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

<h2 id="provides.TlsProvides.all_published_certs">all_published_certs</h2>


List of all [Certificate][] instances that this provider has published
for all related applications.

<h2 id="provides.TlsProvides.all_requests">all_requests</h2>


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

<h2 id="provides.TlsProvides.new_application_requests">new_application_requests</h2>


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

<h2 id="provides.TlsProvides.new_client_requests">new_client_requests</h2>


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

<h2 id="provides.TlsProvides.new_requests">new_requests</h2>


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

<h2 id="provides.TlsProvides.new_server_requests">new_server_requests</h2>


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

<h2 id="provides.TlsProvides.set_ca">set_ca</h2>

```python
TlsProvides.set_ca(certificate_authority)
```

Publish the CA to all related applications.

<h2 id="provides.TlsProvides.set_chain">set_chain</h2>

```python
TlsProvides.set_chain(chain)
```

Publish the chain of trust to all related applications.

<h2 id="provides.TlsProvides.set_client_cert">set_client_cert</h2>

```python
TlsProvides.set_client_cert(cert, key)
```

Deprecated.  This is only for backwards compatibility.

Publish a globally shared client cert and key.

<h2 id="provides.TlsProvides.set_server_cert">set_server_cert</h2>

```python
TlsProvides.set_server_cert(scope, cert, key)
```

Deprecated.  Use one of the [new_requests][] collections and
`request.set_cert()` instead.

Set the server cert and key for the request identified by `scope`.

<h2 id="provides.TlsProvides.set_server_multicerts">set_server_multicerts</h2>

```python
TlsProvides.set_server_multicerts(scope)
```

Deprecated.  Done automatically.

<h2 id="provides.TlsProvides.add_server_cert">add_server_cert</h2>

```python
TlsProvides.add_server_cert(scope, cn, cert, key)
```

Deprecated.  Use `request.set_cert()` instead.

<h2 id="provides.TlsProvides.get_server_requests">get_server_requests</h2>

```python
TlsProvides.get_server_requests()
```

Deprecated.  Use the [new_requests][] or [server_requests][]
collections instead.

One provider can have many requests to generate server certificates.
Return a map of all server request objects indexed by a unique
identifier.

