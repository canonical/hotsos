# Kubernetes-master

[Kubernetes](http://kubernetes.io/) is an open source system for managing
application containers across a cluster of hosts. The Kubernetes project was
started by Google in 2014, combining the experience of running production
workloads combined with best practices from the community.

The Kubernetes project defines some new terms that may be unfamiliar to users
or operators. For more information please refer to the concept guide in the
[getting started guide](https://kubernetes.io/docs/home/).

This charm is an encapsulation of the Kubernetes master processes and the
operations to run on any cloud for the entire lifecycle of the cluster.

This charm is built from other charm layers using the Juju reactive framework.
The other layers focus on specific subset of operations making this layer
specific to operations of Kubernetes master processes.

# Charmed Kubernetes

This charm is not fully functional when deployed by itself. It requires other
charms to model a complete Kubernetes cluster. A Kubernetes cluster needs a
distributed key value store such as [Etcd](https://coreos.com/etcd/) and the
kubernetes-worker charm which delivers the Kubernetes node services. A cluster
also requires a Software Defined Network (SDN), a Container Runtime such as
[containerd](https://jaas.ai/u/containers/containerd), and Transport Layer
Security (TLS) so the components in a cluster communicate securely.

Please take a look at the [Charmed Kubernetes](https://jaas.ai/charmed-kubernetes)
or the [Kubernetes core](https://jaas.ai/kubernetes-core) bundles for
examples of complete models of Kubernetes clusters.

For full install instructions, please see the [Charmed Kubernetes documentation](https://ubuntu.com/kubernetes/docs/quickstart).

For details on configuring and operating this charm, see the [kubernetes-master documentation](https://ubuntu.com/kubernetes/docs/charm-kubernetes-master) on the same site.

# Developers

## Building the charm

```
make charm
```

## Testing the charm

```
tox
```

Note that the unit tests use [`charms.unit_test`](https://pypi.org/project/charms.unit-test/)
so all charms.reactive helpers are automatically patched with fakes and little manual
patching needs to be done. Things like `set_flag` and `is_flag_set` can be used directly.
