from dataclasses import dataclass, field

from hotsos.core.host_helpers import (
    InstallInfoBase,
    SnapPackageHelper,
    SystemdHelper,
)
from hotsos.core.plugintools import PluginPartBase

SNAP_LIST = ['microceph', 'microovn', 'microcloud']
CORE_SNAPS = [rf"(?:snap\.)?{p}" for p in SNAP_LIST]
DEP_SNAPS = ['lxd']
SERVICE_EXPRS = [rf"{s}\S*" for s in CORE_SNAPS]


@dataclass
class MicroCloudInstallInfo(InstallInfoBase):
    """ MicroCloud installation information. """
    snaps: SnapPackageHelper = field(default_factory=lambda:
                                     SnapPackageHelper(core_snaps=CORE_SNAPS,
                                                       other_snaps=DEP_SNAPS))
    systemd: SystemdHelper = field(default_factory=lambda:
                                   SystemdHelper(service_exprs=SERVICE_EXPRS))


class MicroCloudChecks(PluginPartBase):
    """ MicroCloud Checks. """
    plugin_name = 'microcloud'
    plugin_root_index = 15

    def __init__(self, *args, **kwargs):
        super().__init__()
        MicroCloudInstallInfo().mixin(self)

    @classmethod
    def is_runnable(cls):
        """
        Determine whether or not this plugin can and should be run.

        @return: True or False
        """
        if MicroCloudInstallInfo().snaps.core:
            return True

        return False
