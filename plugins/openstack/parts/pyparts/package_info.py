#!/usr/bin/python3
from common import plugintools
from common.checks import APTPackageChecksBase

from openstack_common import (
    OST_DEP_PKGS,
    OST_PKGS_CORE,
)

YAML_PRIORITY = 3


class OpenstackPackageChecks(plugintools.PluginPartBase,
                             APTPackageChecksBase):

    def __call__(self):
        # require at least one core package to be installed to include
        # this in the report.
        if self.core:
            self._output["dpkg"] = self.all


def get_package_checker():
    return OpenstackPackageChecks(core_pkgs=OST_PKGS_CORE,
                                  other_pkgs=OST_DEP_PKGS)
