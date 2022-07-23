from hotsos.core.host_helpers import (
    APTPackageChecksBase,
    SnapPackageChecksBase,
    ServiceChecksBase,
)
from hotsos.core.plugintools import PluginPartBase

CORE_APT = ['maas', 'postgres']
APT_DEPS = ['isc-dhcp', 'bind9']
CORE_SNAPS = CORE_APT

SERVICE_EXPRS = [s + '[A-Za-z0-9-]*' for s in CORE_APT + APT_DEPS]


class MAASChecksBase(PluginPartBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.snaps = SnapPackageChecksBase(core_snaps=CORE_SNAPS)
        self.apt = APTPackageChecksBase(core_pkgs=CORE_APT,
                                        other_pkgs=APT_DEPS)
        self.systemd = ServiceChecksBase(service_exprs=SERVICE_EXPRS,
                                         ps_allow_relative=False)

    @property
    def maas_installed(self):
        if self.apt.core or self.snaps.core:
            return True

        return False

    @property
    def plugin_runnable(self):
        return self.maas_installed
