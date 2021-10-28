from core.checks import ConfigChecksBase
from core.plugins.openstack import (
    OpenstackConfig,
    OpenstackPackageChecksBase
)


class OpenstackConfigChecks(ConfigChecksBase, OpenstackPackageChecksBase):

    def dpdk_enabled(self):
        return self.apt_check.is_installed("openvswitch-switch-dpdk")

    def _get_config_handler(self, path):
        return OpenstackConfig(path)

    def __call__(self):
        # Only run if we think Openstack is installed.
        if not self.openstack_installed:
            return

        self.run_config_checks()
