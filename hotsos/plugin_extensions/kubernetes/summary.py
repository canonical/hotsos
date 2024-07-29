from hotsos.core.plugins.kubernetes import KubernetesChecks
from hotsos.core.plugintools import (
    summary_entry,
    get_min_available_entry_index,
    DefaultSummaryEntryIndexes,
)


class KubernetesSummary(KubernetesChecks):
    """ Implementation of Kubernetes summary. """
    summary_part_index = 0

    # REMINDER: common entries are implemented in the SummaryBase base class
    #           and only application plugin specific customisations are
    #           implemented here. We use the get_min_available_entry_index() to
    #           ensure that additional entries don't clobber existing ones but
    #           conversely can also replace them by re-using their indices.

    @summary_entry('dpkg', DefaultSummaryEntryIndexes.DPKG)
    def summary_dpkg(self):
        """
        Override the default entry to include all discovered packages.
        """
        return self.apt.all_formatted or None

    @summary_entry('pods', get_min_available_entry_index())
    def summary_pods(self):
        return self.pods or None

    @summary_entry('containers', get_min_available_entry_index() + 1)
    def summary_containers(self):
        return self.containers or None

    @summary_entry('flannel', get_min_available_entry_index() + 2)
    def summary_flannel(self):
        info = {}
        for port in self.flannel_ports:
            info[port.name] = port.encap_info
            if port.addresses:
                info[port.name]['addr'] = port.addresses[0]

        return info or None
