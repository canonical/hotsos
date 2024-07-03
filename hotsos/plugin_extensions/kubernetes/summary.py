from hotsos.core.plugins.kubernetes import KubernetesChecksBase


class KubernetesSummary(KubernetesChecksBase):
    summary_part_index = 0

    def __1_summary_services(self):
        if self.systemd.services:
            return self.systemd.summary
        if self.pebble.services:
            return self.pebble.summary

        return None

    def __2_summary_snaps(self):
        return self.snaps.all_formatted or None

    def __3_summary_dpkg(self):
        return self.apt.all_formatted or None

    def __4_summary_pods(self):
        return self.pods or None

    def __5_summary_containers(self):
        return self.containers or None

    def __6_summary_flannel(self):
        info = {}
        for port in self.flannel_ports:
            info[port.name] = port.encap_info
            if port.addresses:
                info[port.name]['addr'] = port.addresses[0]

        return info or None
