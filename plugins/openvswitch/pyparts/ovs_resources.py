from core.plugins.openvswitch import OpenvSwitchChecksBase

YAML_PRIORITY = 0


class OpenvSwitchServiceChecks(OpenvSwitchChecksBase):

    def get_running_services_info(self):
        """Get string info for running daemons."""
        if self.svc_check.services:
            self._output['services'] = self.svc_check.get_service_info_str()

    def __call__(self):
        self.get_running_services_info()


class OpenvSwitchPackageChecks(OpenvSwitchChecksBase):

    def __call__(self):
        self._output['dpkg'] = self.apt_check.all_formatted
