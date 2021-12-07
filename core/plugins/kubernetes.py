import os

from core import (
    checks,
    constants,
    host_helpers,
    plugintools,
)

SERVICES = [r"etcd\S*",
            r"calico\S*",
            r"flannel\S*",
            r"containerd\S*",
            r"dockerd\S*",
            r"kubelet\S*",
            r"kube-\S*",
            ]

# Packages that only exist in a K8s deployment
K8S_PACKAGES = [r'charm[\S]+',
                r'cdk-addons',
                r'helm',
                r'kubernetes-[\S]+',
                r'kube-[\S]+',
                r'kubectl',
                r'kubelet',
                r'kubeadm',
                r'kubefed',
                ]
# Packages that are used in a K8s deployment
K8S_PACKAGE_DEPS = [r'docker',
                    r'go',
                    r'vault',
                    r'etcd',
                    r'conjure-up',
                    ]
# Snap-only deps
K8S_PACKAGE_DEPS_SNAP = [r'core[0-9]*']


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

        _pods = []
        pods_path = os.path.join(constants.DATA_ROOT,
                                 "var/log/pods")
        if os.path.exists(pods_path):
            for pod in os.listdir(pods_path):
                _pods.append(pod)

        self._pods = sorted(_pods)
        return self._pods

    @property
    def containers(self):
        if self._containers:
            return self._containers

        _containers = []
        containers_path = os.path.join(constants.DATA_ROOT,
                                       "var/log/containers")
        if os.path.exists(containers_path):
            for pod in os.listdir(containers_path):
                pod = pod.partition('.log')[0]
                _containers.append(pod)

        self._containers = sorted(_containers)
        return self._containers


class KubernetesChecksBase(KubernetesBase, plugintools.PluginPartBase,
                           checks.ServiceChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        deps = K8S_PACKAGE_DEPS
        # Deployments can use snap or apt versions of packages so we check both
        self.apt_check = checks.APTPackageChecksBase(core_pkgs=K8S_PACKAGES,
                                                     other_pkgs=deps)
        snap_deps = deps + K8S_PACKAGE_DEPS_SNAP
        self.snap_check = checks.SnapPackageChecksBase(core_snaps=K8S_PACKAGES,
                                                       other_snaps=snap_deps)

    @property
    def plugin_runnable(self):
        if self.apt_check.core or self.snap_check.core:
            return True

        return False
