from core.plugins.kubernetes import KubernetesChecksBase

YAML_PRIORITY = 0


class KubernetesPackageChecks(KubernetesChecksBase):

    def __call__(self):
        """ Display relevant snaps installed. """
        snaps = self.snap_check.all_formatted
        if snaps:
            self._output['snaps'] = snaps

        dpkg = self.apt_check.all_formatted
        if dpkg:
            self._output['dpkg'] = dpkg


class KubernetesServiceChecks(KubernetesChecksBase):

    def get_running_services_info(self):
        if self.services:
            self._output['services'] = self.service_info_str

    def __call__(self):
        """ Display relevant services and their status. """
        self.get_running_services_info()


class KubernetesResourceChecks(KubernetesChecksBase):

    def __call__(self):
        """ Display relevant resources. """
        if self.pods:
            self._output['pods'] = self.pods

        if self.containers:
            self._output['containers'] = self.containers
