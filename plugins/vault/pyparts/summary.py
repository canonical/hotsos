from core.plugintools import summary_entry_offset as idx
from core.plugins import vault

YAML_OFFSET = 0


class VaultSummary(vault.VaultServiceChecksBase):

    def __init__(self):
        service_exprs = vault.SERVICE_EXPRS
        super().__init__(service_exprs=service_exprs)

    @idx(0)
    def __summary_services(self):
        if self.services:
            return {'systemd': self.service_info,
                    'ps': self.process_info}

    @idx(1)
    def __summary_snaps(self):
        if self.snap_check.core:
            return self.snap_check.all_formatted
