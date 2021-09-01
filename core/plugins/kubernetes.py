import os

from core import (
    checks,
    constants,
    host_helpers,
    plugintools,
)

SERVICES = ["etcdctl",
            "calicoctl",
            "flanneld",
            "kubectl2",
            "kubelet",
            "containerd-shim",
            "containerd",
            "dockerd",
            "kubelet",
            "kube-proxy",
            "calico-node",
            ]

# Snaps that only exist in a K8s deployment
SNAPS_K8S = [r'charm[\S]+',
             r'conjure-up',
             r'cdk-addons',
             r'helm',
             r'kubernetes-[\S]+',
             r'kube-[\S]+',
             r'kubectl',
             r'kubelet',
             r'kubeadm',
             r'kubefed',
             ]
# Snaps that are used in a K8s deployment
SNAPS_DEPS = [r'core[0-9]*',
              r'docker',
              r'go',
              r'vault',
              r'etcd',
              ]


class KubernetesBase(object):

    def __init__(self):
        super().__init__(SERVICES, hint_range=(0, 3))
        self.nethelp = host_helpers.HostNetworkingHelper()
        self._containers = []
        self._pods = []

    @property
    def flannel_ports(self):
        ports = []
        for port in self.nethelp.host_interfaces:
            if "flannel" in port.name:
                ports.append(port)

        return ports

    @property
    def bind_interfaces(self):
        """
        Fetch interfaces used by Kubernetes.
        """
        return {'flannel': self.flannel_ports}

    @property
    def pods(self):
        if self._pods:
            return self._pods

        pods_path = os.path.join(constants.DATA_ROOT,
                                 "var/log/pods")
        if os.path.exists(pods_path):
            for pod in os.listdir(pods_path):
                self._pods.append(pod)

        return self._pods

    @property
    def containers(self):
        if self._containers:
            return self._containers

        containers_path = os.path.join(constants.DATA_ROOT,
                                       "var/log/containers")
        if os.path.exists(containers_path):
            for pod in os.listdir(containers_path):
                self._containers.append(pod)

        return self._containers


class KubernetesChecksBase(KubernetesBase, plugintools.PluginPartBase,
                           checks.ServiceChecksBase):
    pass
