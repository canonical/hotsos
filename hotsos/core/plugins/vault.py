from hotsos.core.plugintools import PluginPartBase
from hotsos.core.host_helpers import (
    PebbleHelper,
    SnapPackageHelper,
    SystemdHelper,
)
from hotsos.core.utils import cached_property

CORE_SNAPS = ['vault']
SERVICE_EXPRS = [s + '[A-Za-z0-9-]*' for s in CORE_SNAPS]


class VaultChecksBase(PluginPartBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.snaps = SnapPackageHelper(core_snaps=CORE_SNAPS)
        self.systemd = SystemdHelper(service_exprs=SERVICE_EXPRS)
        self.pebble = PebbleHelper(service_exprs=SERVICE_EXPRS)

    @cached_property
    def vault_installed(self):
        if self.snaps.core:
            return True

        return False

    @property
    def plugin_runnable(self):
        return self.vault_installed
