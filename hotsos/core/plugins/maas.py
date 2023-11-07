from functools import cached_property

from hotsos.core.host_helpers import (
    APTPackageHelper,
    SnapPackageHelper,
    SystemdHelper,
)
from hotsos.core.plugintools import PluginPartBase

CORE_APT = ['maas']
APT_DEPS = ['isc-dhcp', 'bind9', 'postgres']
CORE_SNAPS = CORE_APT

SERVICE_EXPRS = [s + '[A-Za-z0-9-]*' for s in CORE_APT + APT_DEPS]


class MAASChecksBase(PluginPartBase):
    plugin_name = 'maas'
    plugin_root_index = 13

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.snaps = SnapPackageHelper(core_snaps=CORE_SNAPS)
        self.apt = APTPackageHelper(core_pkgs=CORE_APT, other_pkgs=APT_DEPS)
        self.systemd = SystemdHelper(service_exprs=SERVICE_EXPRS,
                                     ps_allow_relative=False)

    @cached_property
    def maas_installed(self):
        if self.apt.core or self.snaps.core:
            return True

        return False

    @property
    def plugin_runnable(self):
        return self.maas_installed
