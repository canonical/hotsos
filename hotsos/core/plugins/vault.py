from hotsos.core.plugintools import PluginPartBase
from hotsos.core.host_helpers import ServiceChecksBase, SnapPackageChecksBase

CORE_SNAPS = ['vault']
SERVICE_EXPRS = [s + '[A-Za-z0-9-]*' for s in CORE_SNAPS]


class VaultChecksBase(PluginPartBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.snaps = SnapPackageChecksBase(core_snaps=CORE_SNAPS)
        self.systemd = ServiceChecksBase(service_exprs=SERVICE_EXPRS)

    @property
    def vault_installed(self):
        if self.snaps.core:
            return True

        return False

    @property
    def plugin_runnable(self):
        return self.vault_installed
