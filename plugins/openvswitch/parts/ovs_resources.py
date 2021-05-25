#!/usr/bin/python3
from common import (
    checks,
    plugin_yaml,
)
from ovs_common import (
    OPENVSWITCH_SERVICES_EXPRS,
    OVS_PKGS_CORE,
    OVS_PKGS_DEPS,
)

OVS_INFO = {}


class OpenvSwitchServiceChecks(checks.ServiceChecksBase):
    def get_running_services_info(self):
        """Get string info for running daemons."""
        if self.services:
            OVS_INFO["services"] = self.get_service_info_str()

    def __call__(self):
        super().__call__()
        self.get_running_services_info()


class OpenvswitchPackageChecks(checks.APTPackageChecksBase):
    def __call__(self):
        # require at least one core package to be installed to include
        # this in the report.
        if self.core:
            OVS_INFO["dpkg"] = self.all


def get_package_checks():
    return OpenvswitchPackageChecks(core_pkgs=OVS_PKGS_CORE,
                                    other_pkgs=OVS_PKGS_DEPS)


def get_service_checker():
    # Do this way to make it easier to write unit tests.
    return OpenvSwitchServiceChecks(OPENVSWITCH_SERVICES_EXPRS)


if __name__ == "__main__":
    get_package_checks()()
    get_service_checker()()
    if OVS_INFO:
        plugin_yaml.save_part(OVS_INFO, priority=0)
