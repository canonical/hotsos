from core.checks import APTPackageChecksBase
from core.plugins.storage.ceph import (
    CephServiceChecksBase,
    CEPH_PKGS_CORE,
    CEPH_PKGS_OTHER,
)

YAML_PRIORITY = 0


class CephPackageChecks(CephServiceChecksBase, APTPackageChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(core_pkgs=CEPH_PKGS_CORE, other_pkgs=CEPH_PKGS_OTHER)

    @property
    def output(self):
        if self._output:
            return {"ceph": self._output}

    def __call__(self):
        # require at least one core package to be installed to include
        # this in the report.
        if self.core:
            self._output["dpkg"] = self.all_formatted


class CephServiceChecks(CephServiceChecksBase):

    def get_running_services_info(self):
        """Get string info for running services."""
        if self.services:
            self._output['services'] = {'systemd': self.service_info,
                                        'ps': self.process_info}

    def get_config_network_info(self):
        """ Identify ports used by Ceph daemons, include them in output
        for informational purposes.
        """
        net_info = {}
        for config, port in self.bind_interfaces.items():
            net_info[config] = port.to_dict()

        if net_info:
            self._output['network'] = net_info

    def __call__(self):
        self._output['release'] = self.release_name
        if self.health_status:
            self._output['status'] = self.health_status

        self.get_running_services_info()
        self.get_config_network_info()
