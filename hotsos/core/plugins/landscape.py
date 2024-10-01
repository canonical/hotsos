from functools import cached_property

from hotsos.core.plugintools import PluginPartBase
from hotsos.core.host_helpers import (
    APTPackageHelper,
    SystemdHelper,
)

CORE_APT = ['landscape']
SERVICE_EXPRS = [s + '[A-Za-z0-9-]*' for s in CORE_APT]


class LandscapeChecks(PluginPartBase):
    """ Base class for all Landscape checks. """
    plugin_name = 'landscape'
    plugin_root_index = 14

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apt = APTPackageHelper(core_pkgs=CORE_APT)
        self.systemd = SystemdHelper(service_exprs=SERVICE_EXPRS)

    @cached_property
    def is_installed(self):
        if self.apt.core:
            return True

        return False

    @property
    def plugin_runnable(self):
        return self.is_installed
