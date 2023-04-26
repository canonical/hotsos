from hotsos.core.plugintools import summary_entry_offset as idx
from hotsos.core.plugins.storage.ceph import CephChecksBase
from hotsos.core.utils import sorted_dict


class CephSummary(CephChecksBase):

    @idx(0)
    def __summary_release(self):
        return {'name': self.release_name,
                'days-to-eol': self.days_to_eol}

    @idx(1)
    def __summary_services(self):
        """Get string info for running services."""
        if self.systemd.services:
            return self.systemd.summary
        elif self.pebble.services:
            return self.pebble.summary

    @idx(2)
    def __summary_dpkg(self):
        # require at least one core package to be installed to include
        # this in the report.
        if self.apt.core:
            return self.apt.all_formatted

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
    def __summary_mgr_modules(self):
        if self.cluster.mgr_modules:
            return self.cluster.mgr_modules

    @idx(9)
    def __summary_local_osds(self):
        if self.local_osds:
            osds = {}
            for osd in self.local_osds:
                osds.update(osd.to_dict())

            return sorted_dict(osds)

    @idx(10)
    def __summary_crush_rules(self):
        if self.cluster.crush_map.rules:
            return self.cluster.crush_map.rules

    @idx(11)
    def __summary_large_omap_pgs(self):
        if self.cluster.large_omap_pgs:
            return self.cluster.large_omap_pgs
