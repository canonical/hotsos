#!/usr/bin/python3
from common import plugin_yaml
from common.checks import PackageChecksBase

from openstack_common import (
    OST_PROJECTS,
    OST_DEP_PKGS,
    OST_PKG_ALIASES,
)


class OpenstackPackageChecks(PackageChecksBase):
    pass


def get_checks():
    package_exprs = OST_PROJECTS + OST_PKG_ALIASES + OST_DEP_PKGS
    return OpenstackPackageChecks(package_exprs)


if __name__ == "__main__":
    c = get_checks()
    info = c()
    if info:
        plugin_yaml.save_part({"dpkg": info}, priority=3)
