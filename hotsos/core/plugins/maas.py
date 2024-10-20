from dataclasses import dataclass, field

from hotsos.core.host_helpers import (
    APTPackageHelper,
    InstallInfoBase,
    SnapPackageHelper,
    SystemdHelper,
)
from hotsos.core.plugintools import PluginPartBase

MAAS_CORE_APT = ['maas']
MAAS_APT_DEPS = ['isc-dhcp', 'bind9', 'postgres']
MAAS_CORE_SNAPS = MAAS_CORE_APT

SERVICE_EXPRS = [s + '[A-Za-z0-9-]*' for s in MAAS_CORE_APT + MAAS_APT_DEPS]


@dataclass
class MAASInstallInfo(InstallInfoBase):
    """ MAAS installation information. """
    apt: APTPackageHelper = field(default_factory=lambda:
                                  APTPackageHelper(core_pkgs=MAAS_CORE_APT,
                                                   other_pkgs=MAAS_APT_DEPS))
    snaps: SnapPackageHelper = field(default_factory=lambda:
                                     SnapPackageHelper(
                                         core_snaps=MAAS_CORE_SNAPS))
    systemd: SystemdHelper = field(default_factory=lambda:
                                   SystemdHelper(service_exprs=SERVICE_EXPRS,
                                                 ps_allow_relative=False))


class MAASChecks(PluginPartBase):
    """ MAAS checks. """
    plugin_name = 'maas'
    plugin_root_index = 13

    def __init__(self, *args, **kwargs):
        super().__init__()
        MAASInstallInfo().mixin(self)

    @classmethod
    def is_runnable(cls):
        """
        Determine whether or not this plugin can and should be run.

        @return: True or False
        """
        maas = MAASInstallInfo()
        if maas.apt.core or maas.snaps.core:
            return True

        return False
