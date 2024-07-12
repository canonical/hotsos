from hotsos.core.plugins.kubernetes import KubernetesChecks
from hotsos.core.plugintools import summary_entry


class KubernetesSummary(KubernetesChecks):
    """ Implementation of Kubernetes summary. """
    summary_part_index = 0

    @summary_entry('services', 1)
    def summary_services(self):
        if self.systemd.services:
            return self.systemd.summary
        if self.pebble.services:
            return self.pebble.summary

        return None

    @summary_entry('snaps', 2)
    def summary_snaps(self):
        return self.snaps.all_formatted or None

    @summary_entry('dpkg', 3)
    def summary_dpkg(self):
        return self.apt.all_formatted or None

    @summary_entry('pods', 4)
    def summary_pods(self):
        return self.pods or None

    @summary_entry('containers', 5)
    def summary_containers(self):
        return self.containers or None

    @summary_entry('flannel', 6)
    def summary_flannel(self):
        info = {}
        for port in self.flannel_ports:
            info[port.name] = port.encap_info
            if port.addresses:
                info[port.name]['addr'] = port.addresses[0]

        return info or None
