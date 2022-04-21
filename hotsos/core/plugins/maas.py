from hotsos.core import host_helpers
from hotsos.core.plugintools import PluginPartBase

CORE_APT = ['maas', 'postgres']
APT_DEPS = ['isc-dhcp', 'bind9']
CORE_SNAPS = CORE_APT

SERVICE_EXPRS = [s + '[A-Za-z0-9-]*' for s in CORE_APT + APT_DEPS]


class MAASChecksBase(PluginPartBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.snap_check = host_helpers.SnapPackageChecksBase(
                                                         core_snaps=CORE_SNAPS)
        self.apt_check = host_helpers.APTPackageChecksBase(core_pkgs=CORE_APT,
                                                           other_pkgs=APT_DEPS)

    @property
    def maas_installed(self):
        if self.apt_check.core or self.snap_check.core:
            return True

        return False

    @property
    def plugin_runnable(self):
        return self.maas_installed


class MAASServiceChecksBase(MAASChecksBase, host_helpers.ServiceChecksBase):
    pass
