from common.checks import ConfigChecksBase
from common.plugins.openstack import (
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

        self.run_config_checks()
