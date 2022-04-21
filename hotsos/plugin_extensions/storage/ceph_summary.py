from hotsos.core.plugintools import summary_entry_offset as idx
from hotsos.core.host_helpers import APTPackageChecksBase
from hotsos.core.plugins.storage.ceph import (
    CephServiceChecksBase,
    CEPH_PKGS_CORE,
    CEPH_PKGS_OTHER,
)
from hotsos.core.utils import sorted_dict


class CephSummary(CephServiceChecksBase, APTPackageChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(core_pkgs=CEPH_PKGS_CORE, other_pkgs=CEPH_PKGS_OTHER)

    @idx(0)
    def __summary_release(self):
        return self.release_name

    @idx(1)
    def __summary_services(self):
        """Get string info for running services."""
        if self.services:
            return {'systemd': self.service_info,
                    'ps': self.process_info}

    @idx(2)
    def __summary_dpkg(self):
        # require at least one core package to be installed to include
        # this in the report.
        if self.core:
            return self.all_formatted

    @idx(3)
    def __summary_status(self):
        if self.cluster.health_status:
            return self.cluster.health_status

    @idx(4)
    def __summary_network(self):
        """ Identify ports used by Ceph daemons, include them in output
        for informational purposes.
        """
        net_info = {}
        for config, port in self.bind_interfaces.items():
            net_info[config] = port.to_dict()

        if net_info:
            return net_info

    @idx(5)
    def __summary_osd_pgs_near_limit(self):
        if self.cluster.osds_pgs_above_max:
            return self.cluster.osds_pgs_above_max

    @idx(6)
    def __summary_osd_pgs_suboptimal(self):
        if self.cluster.osds_pgs_suboptimal:
            return self.cluster.osds_pgs_suboptimal

    @idx(7)
    def __summary_versions(self):
        versions = self.cluster.ceph_daemon_versions_unique()
        if versions:
            return versions

    @idx(8)
    def __summary_local_osds(self):
        if self.local_osds:
            osds = {}
            for osd in self.local_osds:
                osds.update(osd.to_dict())

            return sorted_dict(osds)

    @idx(9)
    def __summary_crush_rules(self):
        if self.cluster.crush_map.rules:
            return self.cluster.crush_map.rules

    @idx(10)
    def __summary_large_omap_pgs(self):
        if self.cluster.large_omap_pgs:
            return self.cluster.large_omap_pgs
