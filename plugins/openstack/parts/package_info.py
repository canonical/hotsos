#!/usr/bin/python3
from common import plugin_yaml
from common.checks import PackageChecksBase

from openstack_common import (
    OST_DEP_PKGS,
    OST_PKGS_CORE,
)

OST_PKG_INFO = {}


class OpenstackPackageChecks(PackageChecksBase):
    def __call__(self):
        p = self.packages
        if not p:
            return

        for pkg in p:
            # need at least one core package to be installed to include
            # this in the report.
            name = pkg.split(' ')[0]
            if name in OST_PKGS_CORE:
                OST_PKG_INFO["dpkg"] = p
                break


def get_checks():
    package_exprs = OST_PKGS_CORE + OST_DEP_PKGS
    return OpenstackPackageChecks(package_exprs)


if __name__ == "__main__":
    get_checks()()
    if OST_PKG_INFO:
        plugin_yaml.save_part(OST_PKG_INFO, priority=3)
