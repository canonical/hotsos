# Interface prometheus-manual

This is a [Juju][] interface layer that enables a charm which provides manual
or raw metric scraper job configuration stanzas for Prometheus 2.

The format for the job configuration data can be found in the [Prometheus
Configuration Docs][].  The job configuration will be included as an item
under `scrape_configs` largely unchanged, except for two things:

* To ensure uniqueness, the provided job name will have a UUID appended to it.
* Because the CA cert must be written to disk separately from the config, any
  `tls_config` sections will have their `ca_file` field values replaced with
  the path to the file where the provided `ca_cert` data is written.

# Example Usage

First, you must define the relation endpoint in your charm's `metadata.yaml`:

```yaml
provides:
  prometheus:
    interface: prometheus-manual
```

Next, you must ensure the interface layer is included in your `layer.yaml`:

```yaml
includes:
  - interface:prometheus-manual
```

Then, in your reactive code, add the following, modifying the job data as
your charm needs:

```python
from charms.reactive import endpoint_from_flag


@when('endpoint.prometheus.joined',
      'tls.ca.available')
def register_prometheus_jobs():
    prometheus = endpoint_from_flag('endpoint.prometheus.joined')
    tls = endpoint_from_flag('tls.ca.available')
    prometheus.register_job(job_name='kubernetes-apiservers',
                            ca_cert=tls.root_ca_cert,
                            job_data={
                                'kubernetes_sd_configs': [{'role': 'endpoints'}],
                                'scheme': 'https',
                                'tls_config': {'ca_file': '__ca_file__'},  # placeholder for saved filename
                                'bearer_token': get_token('system:prometheus'),
                            })
    prometheus.register_job(job_name='kubernetes-nodes',
                            ca_cert=tls.root_ca_cert,
                            job_data={
                                'kubernetes_sd_configs': [{'role': 'node'}],
                                'scheme': 'https',
                                'tls_config': {'ca_file': '__ca_file__'},  # placeholder for saved filename
                                'bearer_token': get_token('system:prometheus'),
                            })
```

<!-- charm-layer-docs generated reference -->

# Reference

* [common.md](common.md)
  * [JobRequest](docs/common.md#jobrequest)
    * [egress_subnets](docs/common.md#jobrequest-egress_subnets)
    * [fromkeys](docs/common.md#jobrequest-fromkeys)
    * [ingress_address](docs/common.md#jobrequest-ingress_address)
    * [is_created](docs/common.md#jobrequest-is_created)
    * [is_received](docs/common.md#jobrequest-is_received)
    * [respond](docs/common.md#jobrequest-respond)
    * [to_json](docs/common.md#jobrequest-to_json)
  * [JobResponse](docs/common.md#jobresponse)
    * [fromkeys](docs/common.md#jobresponse-fromkeys)
* [provides.md](provides.md)
  * [PrometheusManualProvides](docs/provides.md#prometheusmanualprovides)
    * [all_departed_units](docs/provides.md#prometheusmanualprovides-all_departed_units)
    * [all_joined_units](docs/provides.md#prometheusmanualprovides-all_joined_units)
    * [all_units](docs/provides.md#prometheusmanualprovides-all_units)
    * [endpoint_name](docs/provides.md#prometheusmanualprovides-endpoint_name)
    * [is_joined](docs/provides.md#prometheusmanualprovides-is_joined)
    * [joined](docs/provides.md#prometheusmanualprovides-joined)
    * [manage_flags](docs/provides.md#prometheusmanualprovides-manage_flags)
    * [register_job](docs/provides.md#prometheusmanualprovides-register_job)
    * [relations](docs/provides.md#prometheusmanualprovides-relations)
    * [requests](docs/provides.md#prometheusmanualprovides-requests)
    * [responses](docs/provides.md#prometheusmanualprovides-responses)
* [requires.md](requires.md)
  * [PrometheusManualRequires](docs/requires.md#prometheusmanualrequires)
    * [all_departed_units](docs/requires.md#prometheusmanualrequires-all_departed_units)
    * [all_joined_units](docs/requires.md#prometheusmanualrequires-all_joined_units)
    * [all_requests](docs/requires.md#prometheusmanualrequires-all_requests)
    * [all_units](docs/requires.md#prometheusmanualrequires-all_units)
    * [endpoint_name](docs/requires.md#prometheusmanualrequires-endpoint_name)
    * [is_joined](docs/requires.md#prometheusmanualrequires-is_joined)
    * [jobs](docs/requires.md#prometheusmanualrequires-jobs)
    * [joined](docs/requires.md#prometheusmanualrequires-joined)
    * [manage_flags](docs/requires.md#prometheusmanualrequires-manage_flags)
    * [new_jobs](docs/requires.md#prometheusmanualrequires-new_jobs)
    * [new_requests](docs/requires.md#prometheusmanualrequires-new_requests)
    * [relations](docs/requires.md#prometheusmanualrequires-relations)

<!-- /charm-layer-docs generated reference -->

# Contact Information

Maintainer: Cory Johns &lt;Cory.Johns@canonical.com&gt;


[Juju]: https://jujucharms.com
[Prometheus Configuration Docs]: https://prometheus.io/docs/prometheus/latest/configuration/configuration/
