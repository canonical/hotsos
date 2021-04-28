#!/usr/bin/python3
from common import plugin_yaml
from common.checks import PackageChecksBase

from openstack_common import OST_PROJECTS, OST_DEP_PKGS


class OpenstackPackageChecks(PackageChecksBase):
    pass


def get_checks():
    return OpenstackPackageChecks(OST_PROJECTS + OST_DEP_PKGS)


if __name__ == "__main__":
    c = get_checks()
    info = c()
    if info:
        plugin_yaml.dump({"dpkg": info})
