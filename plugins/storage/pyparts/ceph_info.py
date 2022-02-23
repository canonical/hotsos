from core.checks import APTPackageChecksBase
from core.plugins.storage.ceph import (
    CephChecksBase,
    CephServiceChecksBase,
    CEPH_PKGS_CORE,
    CEPH_PKGS_OTHER,
)
from core.utils import sorted_dict

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

    def __call__(self):
        self._output['release'] = self.release_name
        if self.cluster.health_status:
            self._output['status'] = self.cluster.health_status

        self.get_running_services_info()


class CephNetworkInfo(CephServiceChecksBase):

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
        self.get_config_network_info()


class CephClusterInfo(CephChecksBase):

    def get_ceph_pg_imbalance(self):
        if self.cluster.osds_pgs_above_max:
            self._output['osd-pgs-near-limit'] = \
                self.cluster.osds_pgs_above_max

        if self.cluster.osds_pgs_suboptimal:
            self._output['osd-pgs-suboptimal'] = \
                self.cluster.osds_pgs_suboptimal

    def get_ceph_versions(self):
        versions = self.cluster.ceph_daemon_versions_unique()
        if not versions:
            return

        self._output['versions'] = versions

    def __call__(self):
        if self.local_osds:
            osds = {}
            for osd in self.local_osds:
                osds.update(osd.to_dict())

            self._output["local-osds"] = sorted_dict(osds)

        self.get_ceph_versions()
        self.get_ceph_pg_imbalance()
        if self.cluster.crush_map.rules:
            self._output['crush-rules'] = self.cluster.crush_map.rules

        if self.cluster.large_omap_pgs:
            self._output['large-omap-pgs'] = self.cluster.large_omap_pgs
