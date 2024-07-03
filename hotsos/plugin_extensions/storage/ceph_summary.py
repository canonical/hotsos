from hotsos.core.plugins.storage.ceph import CephChecksBase
from hotsos.core.utils import sorted_dict


class CephSummary(CephChecksBase):
    summary_part_index = 0

    def __0_summary_release(self):
        return {'name': self.release_name,
                'days-to-eol': self.days_to_eol}

    def __1_summary_services(self):
        """Get string info for running services."""
        if self.systemd.services:
            return self.systemd.summary

        if self.pebble.services:
            return self.pebble.summary

        return None

    def __2_summary_dpkg(self):
        # require at least one core package to be installed to include
        # this in the report.
        if self.apt.core:
            return self.apt.all_formatted

        return None

    def __2_summary_snaps(self):
        if self.snaps.core:
            return self.snaps.all_formatted

        return None

    def __3_summary_status(self):
        return self.cluster.health_status or None

    def __4_summary_network(self):
        """ Identify ports used by Ceph daemons, include them in output
        for informational purposes.
        """
        net_info = {}
        for config, port in self.bind_interfaces.items():
            net_info[config] = port.to_dict()

        if net_info:
            return net_info

        return None

    def __5_summary_osd_pgs_near_limit(self):
        if self.cluster.osds_pgs_above_max:
            return self.cluster.osds_pgs_above_max

        return None

    def __6_summary_osd_pgs_suboptimal(self):
        if self.cluster.osds_pgs_suboptimal:
            return self.cluster.osds_pgs_suboptimal

        return None

    def __7_summary_versions(self):
        versions = self.cluster.ceph_daemon_versions_unique()
        return versions or None

    def __8_summary_mgr_modules(self):
        return self.cluster.mgr_modules or None

    def __9_summary_local_osds(self):
        if self.local_osds:
            osds = {}
            for osd in self.local_osds:
                osds.update(osd.to_dict())

            return sorted_dict(osds)

        return None

    def __10_summary_crush_rules(self):
        return self.cluster.crush_map.rules or None

    def __11_summary_large_omap_pgs(self):
        return self.cluster.large_omap_pgs or None
