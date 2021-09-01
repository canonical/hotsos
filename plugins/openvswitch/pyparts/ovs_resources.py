from core import checks
from core.plugins.openvswitch import (
    OpenvSwitchChecksBase,
    OPENVSWITCH_SERVICES_EXPRS,
    OVS_PKGS_CORE,
    OVS_PKGS_DEPS,
)

YAML_PRIORITY = 0


class OpenvSwitchServiceChecks(OpenvSwitchChecksBase,
                               checks.ServiceChecksBase):

    def __init__(self):
        super().__init__(service_exprs=OPENVSWITCH_SERVICES_EXPRS)

    def get_running_services_info(self):
        """Get string info for running daemons."""
        if self.services:
            self._output["services"] = self.get_service_info_str()

    def __call__(self):
        self.get_running_services_info()


class OpenvSwitchPackageChecks(OpenvSwitchChecksBase,
                               checks.APTPackageChecksBase):

    def __init__(self):
        super().__init__(core_pkgs=OVS_PKGS_CORE, other_pkgs=OVS_PKGS_DEPS)

    def __call__(self):
        # require at least one core package to be installed to include
        # this in the report.
        if self.core:
            self._output["dpkg"] = self.all
