# Interface grafana-dashboard

This is a [Juju][] interface layer that enables a charm which provides
dashboards to be imported into Grafana.

You can download existing [Grafana Dashboards][] or use the [Grafana Dashboard
Reference][] to create your own.

# Example Usage

First, you must define the relation endpoint in your charm's `metadata.yaml`:

```yaml
provides:
  grafana:
    interface: grafana-dashboard
```

Next, you must ensure the interface layer is included in your `layer.yaml`:

```yaml
includes:
  - interface:grafana-dashboard
```

Then, in your reactive code, add the following, modifying the dashboard data as
your charm needs:

```python
import json
from charms.reactive import endpoint_from_flag


@when('endpoint.grafana.joined')
def register_grafana_dashboards():
    grafana = endpoint_from_flag('endpoint.grafana.joined')
    for dashboard_file in Path('files/grafana').glob('*.json'):
        dashboard = json.loads(dashboard_file.read_text())
        grafana.register_dashboard(name=dashboard_file.stem,
                                   dashboard=dashboard)
```

<!-- charm-layer-docs generated reference -->

# Reference

* [common.md](common.md)
  * [ImportRequest](docs/common.md#importrequest)
    * [egress_subnets](docs/common.md#importrequest-egress_subnets)
    * [ingress_address](docs/common.md#importrequest-ingress_address)
    * [is_created](docs/common.md#importrequest-is_created)
    * [is_received](docs/common.md#importrequest-is_received)
    * [respond](docs/common.md#importrequest-respond)
  * [ImportResponse](docs/common.md#importresponse)
    * [name](docs/common.md#importresponse-name)
* [provides.md](provides.md)
  * [GrafanaDashboardProvides](docs/provides.md#grafanadashboardprovides)
    * [all_departed_units](docs/provides.md#grafanadashboardprovides-all_departed_units)
    * [all_joined_units](docs/provides.md#grafanadashboardprovides-all_joined_units)
    * [all_units](docs/provides.md#grafanadashboardprovides-all_units)
    * [endpoint_name](docs/provides.md#grafanadashboardprovides-endpoint_name)
    * [failed_imports](docs/provides.md#grafanadashboardprovides-failed_imports)
    * [is_joined](docs/provides.md#grafanadashboardprovides-is_joined)
    * [joined](docs/provides.md#grafanadashboardprovides-joined)
    * [manage_flags](docs/provides.md#grafanadashboardprovides-manage_flags)
    * [register_dashboard](docs/provides.md#grafanadashboardprovides-register_dashboard)
    * [relations](docs/provides.md#grafanadashboardprovides-relations)
    * [requests](docs/provides.md#grafanadashboardprovides-requests)
    * [responses](docs/provides.md#grafanadashboardprovides-responses)
* [requires.md](requires.md)
  * [GrafanaDashboardRequires](docs/requires.md#grafanadashboardrequires)
    * [all_departed_units](docs/requires.md#grafanadashboardrequires-all_departed_units)
    * [all_joined_units](docs/requires.md#grafanadashboardrequires-all_joined_units)
    * [all_requests](docs/requires.md#grafanadashboardrequires-all_requests)
    * [all_units](docs/requires.md#grafanadashboardrequires-all_units)
    * [endpoint_name](docs/requires.md#grafanadashboardrequires-endpoint_name)
    * [is_joined](docs/requires.md#grafanadashboardrequires-is_joined)
    * [joined](docs/requires.md#grafanadashboardrequires-joined)
    * [manage_flags](docs/requires.md#grafanadashboardrequires-manage_flags)
    * [new_requests](docs/requires.md#grafanadashboardrequires-new_requests)
    * [relations](docs/requires.md#grafanadashboardrequires-relations)

<!-- /charm-layer-docs generated reference -->

# Contact Information

Maintainer: Cory Johns &lt;Cory.Johns@canonical.com&gt;


[Juju]: https://jujucharms.com
[Grafana Dashboards]: https://grafana.com/grafana/dashboards
[Grafana Dashboard Reference]: https://grafana.com/docs/reference/dashboard/
