#!/usr/bin/python3
import re
import sys

from common import (
    helpers,
    plugin_yaml,
)
from kubernetes_common import (
    KubernetesChecksBase,
)


NETWORK_INFO = {}


class KubernetesNetworkChecks(KubernetesChecksBase):

    def get_network_info(self):
        ip_addr_output = helpers.get_ip_addr()
        if not ip_addr_output:
            sys.exit(0)

        cni_type = "flannel"
        iface = None
        for i, line in enumerate(ip_addr_output):
            if cni_type in line:
                if cni_type not in NETWORK_INFO:
                    NETWORK_INFO[cni_type] = {}

                ret = re.compile(r".+({}\.[0-9]+):".format(cni_type)
                                 ).match(line)
                if ret:
                    iface = ret[1]
                    NETWORK_INFO[cni_type][iface] = {}
                    continue

            if iface:
                ret = re.compile(r".+\s+([0-9\.]+/[0-9]+).+\s+{}$".
                                 format(iface)).match(line)
                if iface in ip_addr_output[i - 3] and ret:
                    NETWORK_INFO[cni_type][iface]["addr"] = ret[1]
                    iface = None

            ret = re.compile(r"^\s+vxlan id .+\s+(\S+)\s+dev\s+([0-9a-z]+).+"
                             ).match(line)

            if cni_type in NETWORK_INFO and ret:
                iface_info = "{}@{}".format(ret[1], ret[2])
                NETWORK_INFO[cni_type][iface]["vxlan"] = iface_info

    def __call__(self):
        super().__call__()
        self.get_network_info()


def get_kubernetes_network_checks():
    # do this way to facilitate unit tests
    return KubernetesNetworkChecks()


if __name__ == "__main__":
    get_kubernetes_network_checks()()
    if NETWORK_INFO:
        plugin_yaml.dump({"network": NETWORK_INFO})
