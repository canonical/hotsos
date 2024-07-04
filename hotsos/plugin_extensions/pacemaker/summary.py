from hotsos.core.plugins.pacemaker import PacemakerChecksBase


class PacemakerSummary(PacemakerChecksBase):
    summary_part_index = 0

    def __0_summary_services(self):
        if self.systemd.services:
            return self.systemd.summary

        return None

    def __1_summary_dpkg(self):
        return self.apt.all_formatted or None

    def __2_summary_nodes(self):
        nodes = {}
        if self.online_nodes:
            nodes["online"] = self.online_nodes
        if self.offline_nodes:
            nodes["offline"] = self.offline_nodes

        return nodes or None
