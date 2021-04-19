#!/usr/bin/python3
import os
import re

from common import (
    checks,
    constants,
    helpers,
    plugin_yaml,
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
            ]

# Snaps that only exist in a K8s deployment
SNAPS_K8S = [r'charm[\S]+',
             r'conjure-up',
             r'cdk-addons',
             r'helm',
             r'kubernetes-[\S]+',
             r'kube-proxy',
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
KUBERNETES_INFO = {}


class KubernetesServiceChecks(checks.ServiceChecksBase):
    def get_running_services_info(self):
        """Get string info for running services."""
        if self.services:
            KUBERNETES_INFO["services"] = self.get_service_info_str()

    def __call__(self):
        super().__call__()
        self.get_running_services_info()


def get_kubernetes_service_checker():
    # Do this way to make it easier to write unit tests.
    KUBERNETES_SERVICES_EXPRS = SERVICES
    return KubernetesServiceChecks(KUBERNETES_SERVICES_EXPRS,
                                   hint_range=(0, 3))


def _get_snap_info(line, snap):
    """Returns snap name and version if found in line.

    @return: tuple of (name, version) or None
    """
    ret = re.compile(r"^({})\s+([\S]+)\s+.+".format(snap)).match(line)
    if ret:
        return (ret[1], ret[2])

    return None


def get_snap_info():
    snap_list_all = helpers.get_snap_list_all()
    if not snap_list_all:
        return

    snap_info_core = {}
    snap_info_deps = {}
    for line in snap_list_all:
        for snap in SNAPS_K8S:
            info = _get_snap_info(line, snap)
            if not info:
                continue

            name, version = info
            # only show latest version installed
            if name in snap_info_core:
                if version > snap_info_core[name]:
                    snap_info_core[name] = version
            else:
                snap_info_core[name] = version

        for snap in SNAPS_DEPS:
            info = _get_snap_info(line, snap)
            if not info:
                continue

            name, version = info
            # only show latest version installed
            if name in snap_info_deps:
                if version > snap_info_deps[name]:
                    snap_info_deps[name] = version
            else:
                snap_info_deps[name] = version

    if snap_info_core:
        snap_info_core.update(snap_info_deps)
        KUBERNETES_INFO["snaps"] = snap_info_core


def get_pod_info():
    pod_info = []
    pods_path = os.path.join(constants.DATA_ROOT, "var/log/pods")
    if os.path.exists(pods_path):
        for pod in os.listdir(pods_path):
            pod_info.append(pod)

    if pod_info:
        KUBERNETES_INFO["pods"] = pod_info


def get_container_info():
    container_info = []
    containers_path = os.path.join(constants.DATA_ROOT, "var/log/containers")
    if os.path.exists(containers_path):
        for container in os.listdir(containers_path):
            container_info.append(container)

    if container_info:
        KUBERNETES_INFO["containers"] = container_info


if __name__ == "__main__":
    get_kubernetes_service_checker()()
    get_snap_info()
    get_pod_info()
    get_container_info()
    if KUBERNETES_INFO:
        plugin_yaml.dump(KUBERNETES_INFO)
