from dataclasses import dataclass, field

from hotsos.core.plugintools import PluginPartBase
from hotsos.core.host_helpers import (
    InstallInfoBase,
    PebbleHelper,
    SnapPackageHelper,
    SystemdHelper,
)

CORE_SNAPS = ['vault']
SERVICE_EXPRS = [s + '[A-Za-z0-9-]*' for s in CORE_SNAPS]


@dataclass
class VaultInstallInfo(InstallInfoBase):
    """ Vault installation information. """
    pebble: PebbleHelper = field(default_factory=lambda:
                                 PebbleHelper(service_exprs=SERVICE_EXPRS))
    snaps: SnapPackageHelper = field(default_factory=lambda:
                                     SnapPackageHelper(core_snaps=CORE_SNAPS))
    systemd: SystemdHelper = field(default_factory=lambda:
                                   SystemdHelper(service_exprs=SERVICE_EXPRS))


class VaultChecks(PluginPartBase):
    """ Base class for all vault checks. """
    plugin_name = 'vault'
    plugin_root_index = 10

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        VaultInstallInfo().mixin(self)

    @classmethod
    def is_runnable(cls):
        """
        Determine whether or not this plugin can and should be run.

        @return: True or False
        """
        if VaultInstallInfo().snaps.core:
            return True

        return False
