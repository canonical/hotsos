from hotsos.core.plugins.storage.ceph.common import CephChecks
from hotsos.core.utils import sorted_dict
from hotsos.core.plugintools import (
    summary_entry,
    get_min_available_entry_index,
)


class CephSummary(CephChecks):
    """ Implementation of Ceph summary. """
    summary_part_index = 0

    # REMINDER: Common entries are implemented in
    #           plugintools.ApplicationSummaryBase. Only customisations are
    #           implemented here. See
    #           plugintools.get_min_available_entry_index() for an explanation
    #           on how entry indices are managed.

    @summary_entry('status', get_min_available_entry_index())
    def summary_status(self):
        return self.cluster.health_status or None

    @summary_entry('network', get_min_available_entry_index() + 1)
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

    @summary_entry('osd-pgs-near-limit', get_min_available_entry_index() + 2)
    def summary_osd_pgs_near_limit(self):
        if self.cluster.osds_pgs_above_max:
            return self.cluster.osds_pgs_above_max

        return None

    @summary_entry('osd-pgs-suboptimal', get_min_available_entry_index() + 3)
    def summary_osd_pgs_suboptimal(self):
        if self.cluster.osds_pgs_suboptimal:
            return self.cluster.osds_pgs_suboptimal

        return None

    @summary_entry('versions',  get_min_available_entry_index() + 4)
    def summary_versions(self):
        versions = self.cluster.ceph_daemon_versions_unique()
        return versions or None

    @summary_entry('mgr-modules',  get_min_available_entry_index() + 5)
    def summary_mgr_modules(self):
        return self.cluster.mgr_modules or None

    @summary_entry('local-osds', get_min_available_entry_index() + 6)
    def summary_local_osds(self):
        if self.local_osds:
            osds = {}
            for osd in self.local_osds:
                osds.update(osd.to_dict())

            return sorted_dict(osds)

        return None

    @summary_entry('crush-rules', get_min_available_entry_index() + 7)
    def summary_crush_rules(self):
        return self.cluster.crush_map.rules or None

    @summary_entry('large-omap-pgs', get_min_available_entry_index() + 8)
    def summary_large_omap_pgs(self):
        return self.cluster.large_omap_pgs or None
