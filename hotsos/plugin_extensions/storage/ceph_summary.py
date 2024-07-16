from hotsos.core.plugins.storage.ceph.common import CephChecks
from hotsos.core.utils import sorted_dict
from hotsos.core.plugintools import summary_entry


class CephSummary(CephChecks):
    """ Implementation of Ceph summary. """
    summary_part_index = 0

    @summary_entry('release', 0)
    def summary_release(self):
        return {'name': self.release_name,
                'days-to-eol': self.days_to_eol}

    @summary_entry('services', 1)
    def summary_services(self):
        """Get string info for running services."""
        if self.systemd.services:
            return self.systemd.summary

        if self.pebble.services:
            return self.pebble.summary

        return None

    @summary_entry('dpkg', 2)
    def summary_dpkg(self):
        # require at least one core package to be installed to include
        # this in the report.
        if self.apt.core:
            return self.apt.all_formatted

        return None

    @summary_entry('snaps', 2)
    def summary_snaps(self):
        if self.snaps.core:
            return self.snaps.all_formatted

        return None

    @summary_entry('status', 3)
    def summary_status(self):
        return self.cluster.health_status or None

    @summary_entry('network', 4)
    def summary_network(self):
        """ Identify ports used by Ceph daemons, include them in output
        for informational purposes.
        """
        net_info = {}
        for config, port in self.bind_interfaces.items():
            net_info[config] = port.to_dict()

        if net_info:
            return net_info

        return None

    @summary_entry('osd-pgs-near-limit', 5)
    def summary_osd_pgs_near_limit(self):
        if self.cluster.osds_pgs_above_max:
            return self.cluster.osds_pgs_above_max

        return None

    @summary_entry('osd-pgs-suboptimal', 6)
    def summary_osd_pgs_suboptimal(self):
        if self.cluster.osds_pgs_suboptimal:
            return self.cluster.osds_pgs_suboptimal

        return None

    @summary_entry('versions', 7)
    def summary_versions(self):
        versions = self.cluster.ceph_daemon_versions_unique()
        return versions or None

    @summary_entry('mgr-modules', 8)
    def summary_mgr_modules(self):
        return self.cluster.mgr_modules or None

    @summary_entry('local-osds', 9)
    def summary_local_osds(self):
        if self.local_osds:
            osds = {}
            for osd in self.local_osds:
                osds.update(osd.to_dict())

            return sorted_dict(osds)

        return None

    @summary_entry('crush-rules', 10)
    def summary_crush_rules(self):
        return self.cluster.crush_map.rules or None

    @summary_entry('large-omap-pgs', 11)
    def summary_large_omap_pgs(self):
        return self.cluster.large_omap_pgs or None
