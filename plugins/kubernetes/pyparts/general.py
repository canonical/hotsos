from core import (
    checks,
    plugintools,
)
from core.plugins.kubernetes import (
    KubernetesChecksBase,
    SNAPS_DEPS,
    SNAPS_K8S,
)

YAML_PRIORITY = 0


class KubernetesPackageChecks(plugintools.PluginPartBase,
                              checks.SnapPackageChecksBase):

    def __init__(self):
        super().__init__(core_snaps=SNAPS_K8S, other_snaps=SNAPS_DEPS)

    def __call__(self):
        # require at least one core package to be installed to include
        # this in the report.
        if self.core:
            self._output["snaps"] = self.all_formatted


class KubernetesServiceChecks(KubernetesChecksBase):

    def get_running_services_info(self):
        """Get string info for running services."""
        if self.services:
            self._output["services"] = self.get_service_info_str()

    def __call__(self):
        self.get_running_services_info()


class KubernetesResourceChecks(KubernetesChecksBase):
    def __call__(self):
        if self.pods:
            self._output['pods'] = self.pods

        if self.pods:
            self._output['containers'] = self.containers
