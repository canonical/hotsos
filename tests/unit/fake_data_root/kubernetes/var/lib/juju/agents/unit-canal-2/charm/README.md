# Canal Charm

Canal is a community-driven initiative that aims to allow users to easily
deploy Calico and flannel networking together as a unified networking
solution - combining Calico’s industry-leading network policy enforcement with
the rich superset of Calico and flannel overlay and non-overlay network
connectivity options.

This charm will deploy flannel and calico as background services, and configure
CNI to use them, on any principal charm that implements the [kubernetes-cni][]
interface.

This charm is a component of Charmed Kubernetes. For full information,
please visit the [official Charmed Kubernetes docs](https://www.ubuntu.com/kubernetes/docs/charm-canal).

[kubernetes-cni]: https://github.com/juju-solutions/interface-kubernetes-cni
