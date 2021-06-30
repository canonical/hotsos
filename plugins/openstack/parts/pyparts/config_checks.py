#!/usr/bin/python3
from common.checks import ConfigChecksBase
from openstack_common import (
    OpenstackConfig,
    OpenstackPackageChecksBase
)


class OpenstackConfigChecks(ConfigChecksBase, OpenstackPackageChecksBase):

    def dpdk_enabled(self):
        return self.is_installed("openvswitch-switch-dpdk")

    def _get_config_handler(self, path):
        return OpenstackConfig(path)

    def __call__(self):
        # Only run if core openstack is installed.
        if not self.core:
            return

        super().__call__()
