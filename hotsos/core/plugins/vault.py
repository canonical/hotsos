from hotsos.core import host_helpers
from hotsos.core.plugintools import PluginPartBase

CORE_SNAPS = ['vault']
SERVICE_EXPRS = [s + '[A-Za-z0-9-]*' for s in CORE_SNAPS]


class VaultChecksBase(PluginPartBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.snap_check = host_helpers.SnapPackageChecksBase(
                                                         core_snaps=CORE_SNAPS)

    @property
    def vault_installed(self):
        if self.snap_check.core:
            return True

        return False

    @property
    def plugin_runnable(self):
        return self.vault_installed


class VaultServiceChecksBase(VaultChecksBase, host_helpers.ServiceChecksBase):
    pass
