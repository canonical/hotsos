import os

from hotsos.core import plugintools
from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import (
    APTPackageHelper,
    HostNetworkingHelper,
    PebbleHelper,
    SnapPackageHelper,
    SystemdHelper,
)
from hotsos.core.utils import cached_property

SERVICES = [r"etcd\S*",
            r"calico\S*",
            r"flannel\S*",
            r"containerd\S*",
            r"dockerd\S*",
            r"kubelet\S*",
            r"kube-\S*",
            ]

# Packages that only exist in a K8s deployment
K8S_PACKAGES = [r'cdk-addons',
                r'helm',
                r'kubernetes-[\S]+',
                r'kube-[\S]+',
                r'kubectl',
                r'kubelet',
                r'kubeadm',
                r'kubefed',
                ]
# Packages that are used in a K8s deployment
K8S_PACKAGE_DEPS = [r'charm[\S]+',
                    r'docker',
                    r'go',
                    r'vault',
                    r'etcd',
                    r'conjure-up',
                    ]
# Snap-only deps
K8S_PACKAGE_DEPS_SNAP = [r'core[0-9]*']


class KubernetesBase(object):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.nethelp = HostNetworkingHelper()
        self._containers = []
        self._pods = []

    @cached_property
    def flannel_ports(self):
        ports = []
        for port in self.nethelp.host_interfaces:
            if "flannel" in port.name:
                ports.append(port)

        return ports

    @cached_property
    def bind_interfaces(self):
        """
        Fetch interfaces used by Kubernetes.
        """
        return {'flannel': self.flannel_ports}

    @cached_property
    def pods(self):
        if self._pods:
            return self._pods

        _pods = []
        pods_path = os.path.join(HotSOSConfig.data_root,
                                 "var/log/pods")
        if os.path.exists(pods_path):
            for pod in os.listdir(pods_path):
                _pods.append(pod)

        self._pods = sorted(_pods)
        return self._pods

    @cached_property
    def containers(self):
        if self._containers:
            return self._containers

        _containers = []
        containers_path = os.path.join(HotSOSConfig.data_root,
                                       "var/log/containers")
        if os.path.exists(containers_path):
            for pod in os.listdir(containers_path):
                pod = pod.partition('.log')[0]
                _containers.append(pod)

        self._containers = sorted(_containers)
        return self._containers


class KubernetesChecksBase(KubernetesBase, plugintools.PluginPartBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        deps = K8S_PACKAGE_DEPS
        # Deployments can use snap or apt versions of packages so we check both
        self.apt = APTPackageHelper(core_pkgs=K8S_PACKAGES, other_pkgs=deps)
        snap_deps = deps + K8S_PACKAGE_DEPS_SNAP
        self.snaps = SnapPackageHelper(core_snaps=K8S_PACKAGES,
                                       other_snaps=snap_deps)
        self.pebble = PebbleHelper(service_exprs=SERVICES)
        self.systemd = SystemdHelper(service_exprs=SERVICES)

    @property
    def plugin_runnable(self):
        if self.apt.core or self.snaps.core:
            return True

        return False
