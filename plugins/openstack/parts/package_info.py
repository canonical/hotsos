#!/usr/bin/python3
from common import plugin_yaml
from common.checks import APTPackageChecksBase

from openstack_common import (
    OST_DEP_PKGS,
    OST_PKGS_CORE,
)

OST_PKG_INFO = {}


class OpenstackPackageChecks(APTPackageChecksBase):
    def __call__(self):
        # require at least one core package to be installed to include
        # this in the report.
        if self.core:
            OST_PKG_INFO["dpkg"] = self.all


def get_checks():
    return OpenstackPackageChecks(core_pkgs=OST_PKGS_CORE,
                                  other_pkgs=OST_DEP_PKGS)


if __name__ == "__main__":
    get_checks()()
    if OST_PKG_INFO:
        plugin_yaml.save_part(OST_PKG_INFO, priority=3)
