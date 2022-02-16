from core.plugins import vault

YAML_PRIORITY = 0


class VaultInstallChecks(vault.VaultChecksBase):

    def __call__(self):
        if self.snap_check.core:
            self._output["snaps"] = self.snap_check.all_formatted


class VaultServiceChecks(vault.VaultServiceChecksBase):

    def __init__(self):
        service_exprs = vault.SERVICE_EXPRS
        super().__init__(service_exprs=service_exprs)

    def get_running_services_info(self):
        if self.services:
            self._output['services'] = {'systemd': self.service_info,
                                        'ps': self.process_info}

    def __call__(self):
        if not self.vault_installed:
            return

        self.get_running_services_info()
