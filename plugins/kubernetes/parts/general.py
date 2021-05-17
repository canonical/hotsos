#!/usr/bin/python3
import os
import re

from common import (
    constants,
    cli_helpers,
    plugin_yaml,
)
from common.checks import PackageChecksBase
from kubernetes_common import (
    KubernetesChecksBase,
    SNAPS_DEPS,
    SNAPS_K8S,
)

KUBERNETES_INFO = {}


class KubernetesPackageChecks(PackageChecksBase):

    @classmethod
    def get_snap_info_from_line(cls, line, snap):
        """Returns snap name and version if found in line.

        @return: tuple of (name, version) or None
        """
        ret = re.compile(r"^({})\s+([\S]+)\s+.+".format(snap)).match(line)
        if ret:
            return (ret[1], ret[2])

        return None

    def get_snaps(self):
        """Get list of relevant snaps and their versions."""
        # TODO: generalise this method and move into the base class
        snap_list_all = cli_helpers.get_snap_list_all()
        if not snap_list_all:
            return

        snap_info_core = {}
        snap_info_deps = {}
        for line in snap_list_all:
            for snap in SNAPS_K8S:
                info = self.get_snap_info_from_line(line, snap)
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
                info = self.get_snap_info_from_line(line, snap)
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

    def __call__(self):
        # no apt packages checked currently, just snaps
        self.get_snaps()


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
    return KubernetesPackageChecks(None)


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
