# Kube-DNS

This interface allows a DNS provider, such as CoreDNS, to provide name
resolution for a Kubernetes cluster.

(Note: this interface was previously used by the Kubernetes Master charm to
communicate the DNS provider info to the Kubernetes Worker charm, but that
usage was folded into the `kube-control` interface.)


# Provides

The provider should look for the `{endpoint_name}.connected` flag and call
the `set_dns_info` method with the `domain`, `sdn_ip`, and `port` info (note:
these must be provided as keyword arguments).

# Requires

The requirer should look for the `{endpoint_name}.available` flag and call the
`details` method, which will return a dictionary with the `domain`, `sdn-ip`,
and `port` keys.
