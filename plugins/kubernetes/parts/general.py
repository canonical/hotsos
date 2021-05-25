#!/usr/bin/python3
import os

from common import (
    checks,
    constants,
    plugin_yaml,
)
from kubernetes_common import (
    KubernetesChecksBase,
    SNAPS_DEPS,
    SNAPS_K8S,
)

KUBERNETES_INFO = {}


class KubernetesPackageChecks(checks.SnapPackageChecksBase):
    def __call__(self):
        # require at least one core package to be installed to include
        # this in the report.
        if self.core:
            KUBERNETES_INFO["snaps"] = self.all


class KubernetesServiceChecks(KubernetesChecksBase):
    def get_running_services_info(self):
        """Get string info for running services."""
        if self.services:
            KUBERNETES_INFO["services"] = self.get_service_info_str()

    def __call__(self):
        super().__call__()
        self.get_running_services_info()


class KubernetesResourceChecks(object):

    def get_pod_info(self):
        pod_info = []
        pods_path = os.path.join(constants.DATA_ROOT,
                                 "var/log/pods")
        if os.path.exists(pods_path):
            for pod in os.listdir(pods_path):
                pod_info.append(pod)

        if pod_info:
            KUBERNETES_INFO["pods"] = pod_info

    def get_container_info(self):
        container_info = []
        containers_path = os.path.join(constants.DATA_ROOT,
                                       "var/log/containers")
        if os.path.exists(containers_path):
            for container in os.listdir(containers_path):
                container_info.append(container)

        if container_info:
            KUBERNETES_INFO["containers"] = container_info

    def __call__(self):
        self.get_pod_info()
        self.get_container_info()


def get_kubernetes_package_checker():
    # Do this way to make it easier to write unit tests.
    return KubernetesPackageChecks(core_snaps=SNAPS_K8S,
                                   other_snaps=SNAPS_DEPS)


def get_kubernetes_service_checker():
    # Do this way to make it easier to write unit tests.
    return KubernetesServiceChecks()


def get_kubernetes_resource_checker():
    return KubernetesResourceChecks()


if __name__ == "__main__":
    get_kubernetes_service_checker()()
    get_kubernetes_package_checker()()
    get_kubernetes_resource_checker()()
    if KUBERNETES_INFO:
        plugin_yaml.save_part(KUBERNETES_INFO, priority=0)
