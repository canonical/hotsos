from core.plugins.kubernetes import KubernetesChecksBase

YAML_PRIORITY = 1


class KubernetesNetworkChecks(KubernetesChecksBase):

    def get_network_info(self):
        for port in self.flannel_ports:
            if 'flannel' not in self._output:
                self._output['flannel'] = {}

            self._output['flannel'][port.name] = port.encap_info
            if port.addresses:
                self._output['flannel'][port.name]['addr'] = port.addresses[0]

    def __call__(self):
        self.get_network_info()
