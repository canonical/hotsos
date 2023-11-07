from hotsos.core.plugins.kubernetes import KubernetesChecksBase


class KubernetesSummary(KubernetesChecksBase):
    summary_part_index = 0

    def __1_summary_services(self):
        if self.systemd.services:
            return self.systemd.summary
        if self.pebble.services:
            return self.pebble.summary

    def __2_summary_snaps(self):
        snaps = self.snaps.all_formatted
        if snaps:
            return snaps

    def __3_summary_dpkg(self):
        dpkg = self.apt.all_formatted
        if dpkg:
            return dpkg

    def __4_summary_pods(self):
        if self.pods:
            return self.pods

    def __5_summary_containers(self):
        if self.containers:
            return self.containers

    def __6_summary_flannel(self):
        info = {}
        for port in self.flannel_ports:
            info[port.name] = port.encap_info
            if port.addresses:
                info[port.name]['addr'] = port.addresses[0]

        if info:
            return info
