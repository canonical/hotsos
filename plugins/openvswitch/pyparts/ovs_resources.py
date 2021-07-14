from common import checks
from common.plugins.openvswitch import (
    OpenvSwitchChecksBase,
    OPENVSWITCH_SERVICES_EXPRS,
    OVS_PKGS_CORE,
    OVS_PKGS_DEPS,
)

YAML_PRIORITY = 0


class OpenvSwitchServiceChecks(OpenvSwitchChecksBase,
                               checks.ServiceChecksBase):

    def get_running_services_info(self):
        """Get string info for running daemons."""
        if self.services:
            self._output["services"] = self.get_service_info_str()

    def __call__(self):
        super().__call__()
        self.get_running_services_info()


class OpenvswitchPackageChecks(OpenvSwitchChecksBase,
                               checks.APTPackageChecksBase):

    def __call__(self):
        # require at least one core package to be installed to include
        # this in the report.
        if self.core:
            self._output["dpkg"] = self.all


def get_package_checks():
    return OpenvswitchPackageChecks(core_pkgs=OVS_PKGS_CORE,
                                    other_pkgs=OVS_PKGS_DEPS)


def get_service_checker():
    # Do this way to make it easier to write unit tests.
    return OpenvSwitchServiceChecks(OPENVSWITCH_SERVICES_EXPRS)
