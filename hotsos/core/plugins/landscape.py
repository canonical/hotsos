from dataclasses import dataclass, field

from hotsos.core.plugintools import PluginPartBase
from hotsos.core.host_helpers import (
    APTPackageHelper,
    InstallInfoBase,
    SystemdHelper,
)

CORE_APT = ['landscape']
SERVICE_EXPRS = [s + '[A-Za-z0-9-]*' for s in CORE_APT]


@dataclass
class LandscapeInstallInfo(InstallInfoBase):
    """ Landscape installation information. """
    apt: APTPackageHelper = field(default_factory=lambda:
                                  APTPackageHelper(core_pkgs=CORE_APT))
    systemd: SystemdHelper = field(default_factory=lambda:
                                   SystemdHelper(service_exprs=SERVICE_EXPRS))


class LandscapeChecks(PluginPartBase):
    """ Base class for all Landscape checks. """
    plugin_name = 'landscape'
    plugin_root_index = 14

    def __init__(self, *args, **kwargs):
        super().__init__()
        LandscapeInstallInfo().mixin(self)

    @classmethod
    def is_runnable(cls):
        """
        Determine whether or not this plugin can and should be run.

        @return: True or False
        """
        if LandscapeInstallInfo().apt.core:
            return True

        return False
