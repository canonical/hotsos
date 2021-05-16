#!/usr/bin/python3
from common import (
    checks,
    plugin_yaml,
)
from ovs_common import (
    OPENVSWITCH_SERVICES_EXPRS,
    OVS_PKGS,
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


class OpenvswitchPackageChecks(checks.PackageChecksBase):
    def __call__(self):
        p = self.packages
        if p:
            OVS_INFO["dpkg"] = p


def get_package_checks():
    return OpenvswitchPackageChecks(OVS_PKGS)


def get_service_checker():
    # Do this way to make it easier to write unit tests.
    return OpenvSwitchServiceChecks(OPENVSWITCH_SERVICES_EXPRS)


if __name__ == "__main__":
    get_package_checks()()
    get_service_checker()()
    if OVS_INFO:
        plugin_yaml.save_part(OVS_INFO, priority=0)
