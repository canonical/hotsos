#!/usr/bin/python3
from common import plugin_yaml
from common.checks import PackageChecksBase

from openstack_common import (
    OST_PROJECTS,
    OST_DEP_PKGS,
    OST_PKG_ALIASES,
)

OST_PKG_INFO = {}


class OpenstackPackageChecks(PackageChecksBase):
    def __call__(self):
        p = self.packages
        if p:
            OST_PKG_INFO["dpkg"] = p


def get_checks():
    package_exprs = OST_PROJECTS + OST_PKG_ALIASES + OST_DEP_PKGS
    return OpenstackPackageChecks(package_exprs)


if __name__ == "__main__":
    get_checks()()
    if OST_PKG_INFO:
        plugin_yaml.save_part(OST_PKG_INFO, priority=3)
