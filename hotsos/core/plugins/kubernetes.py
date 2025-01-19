import os
from dataclasses import dataclass, field
from functools import cached_property

from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import (
    APTPackageHelper,
    HostNetworkingHelper,
    InstallInfoBase,
    PebbleHelper,
    SnapPackageHelper,
    SystemdHelper,
)
from hotsos.core import plugintools

SERVICES = [r"etcd\S*",
            r"calico\S*",
            r"flannel\S*",
            r"containerd\S*",
            r"dockerd\S*",
            r"kubelet\S*",
            r"kube-\S*",
            r"microk8s\S*",
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
                r'microk8s',
                r'k8s',
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
K8S_SNAP_DEPS = K8S_PACKAGE_DEPS + K8S_PACKAGE_DEPS_SNAP
MICROK8S_COMMON = 'var/snap/microk8s/common'


@dataclass
class KubernetesInstallInfo(InstallInfoBase):
    """ Kubernetes installation information. """
    apt: APTPackageHelper = field(default_factory=lambda:
                                  APTPackageHelper(
                                                core_pkgs=K8S_PACKAGES,
                                                other_pkgs=K8S_PACKAGE_DEPS))
    pebble: PebbleHelper = field(default_factory=lambda:
                                 PebbleHelper(service_exprs=SERVICES))
    snaps: SnapPackageHelper = field(default_factory=lambda:
                                     SnapPackageHelper(
                                        core_snaps=K8S_PACKAGES,
                                        other_snaps=K8S_SNAP_DEPS))
    systemd: SystemdHelper = field(default_factory=lambda:
                                   SystemdHelper(service_exprs=SERVICES))


class KubernetesBase():
    """ Base class for Kubernetes checks. """
    @cached_property
    def flannel_ports(self):
        ports = []
        nethelp = HostNetworkingHelper()
        for port in nethelp.host_interfaces:
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
        pods = []
        pods_path = os.path.join(HotSOSConfig.data_root,
                                 "var/log/pods")
        mk8s_pods_path = os.path.join(HotSOSConfig.data_root,
                                      MICROK8S_COMMON, 'var/log/pods')
        for path in [pods_path, mk8s_pods_path]:
            if os.path.exists(path):
                for pod in os.listdir(path):
                    pods.append(pod)

        return sorted(pods)

    @cached_property
    def containers(self):
        containers = []
        containers_path = os.path.join(HotSOSConfig.data_root,
                                       "var/log/containers")
        mk8s_containers_path = os.path.join(HotSOSConfig.data_root,
                                            MICROK8S_COMMON,
                                            'var/log/containers')
        for path in [containers_path, mk8s_containers_path]:
            if os.path.exists(path):
                for ctr in os.listdir(path):
                    ctr = ctr.partition('.log')[0]
                    containers.append(ctr)

        return sorted(containers)


class KubernetesChecks(KubernetesBase, plugintools.PluginPartBase):
    """ Kubernetes checks. """
    plugin_name = 'kubernetes'
    plugin_root_index = 8

    def __init__(self, *args, **kwargs):
        super().__init__()
        KubernetesInstallInfo().mixin(self)

    @classmethod
    def is_runnable(cls):
        """
        Determine whether or not this plugin can and should be run.

        @return: True or False
        """
        k8s = KubernetesInstallInfo()
        if k8s.apt.core or k8s.snaps.core:
            return True

        return False
