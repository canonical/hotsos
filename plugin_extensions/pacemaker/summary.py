from core.plugintools import summary_entry_offset as idx
from core.plugins.pacemaker import PacemakerChecksBase


class PacemakerSummary(PacemakerChecksBase):

    @idx(0)
    def __summary_services(self):
        if self.svc_check.services:
            return {'systemd': self.svc_check.service_info,
                    'ps': self.svc_check.process_info}

    @idx(1)
    def __summary_dpkg(self):
        apt = self.apt_check.all_formatted
        if apt:
            return apt
