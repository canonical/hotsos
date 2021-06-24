#!/usr/bin/python3
import re
import sys

from common import cli_helpers
from kubernetes_common import KubernetesChecksBase

YAML_PRIORITY = 1


class KubernetesNetworkChecks(KubernetesChecksBase):

    def get_network_info(self):
        ip_addr_output = cli_helpers.get_ip_addr()
        if not ip_addr_output:
            sys.exit(0)

        cni_type = "flannel"
        iface = None
        for i, line in enumerate(ip_addr_output):
            if cni_type in line:
                if cni_type not in self._output:
                    self._output[cni_type] = {}

                ret = re.compile(r".+({}\.[0-9]+):".format(cni_type)
                                 ).match(line)
                if ret:
                    iface = ret[1]
                    self._output[cni_type][iface] = {}
                    continue

            if iface:
                ret = re.compile(r".+\s+([0-9\.]+/[0-9]+).+\s+{}$".
                                 format(iface)).match(line)
                if iface in ip_addr_output[i - 3] and ret:
                    self._output[cni_type][iface]["addr"] = ret[1]
                    iface = None

            ret = re.compile(r"^\s+vxlan id .+\s+(\S+)\s+dev\s+([0-9a-z]+).+"
                             ).match(line)

            if cni_type in self._output and ret:
                iface_info = "{}@{}".format(ret[1], ret[2])
                self._output[cni_type][iface]["vxlan"] = iface_info

    def __call__(self):
        super().__call__()
        self.get_network_info()
