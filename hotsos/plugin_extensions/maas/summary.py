from hotsos.core.plugins.maas import MAASChecks


class MAASSummary(MAASChecks):
    """ Implementation of MAAS summary. """
    summary_part_index = 0

    def __0_summary_services(self):
        if self.systemd.services:
            return self.systemd.summary

        return None

    def __1_summary_dpkg(self):
        if self.apt.core:
            return self.apt.all_formatted

        return None

    def __2_summary_snaps(self):
        if self.snaps.core:
            return self.snaps.all_formatted

        return None
