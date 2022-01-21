from core.plugins import maas

YAML_PRIORITY = 0


class MAASInstallChecks(maas.MAASChecksBase):

    def __call__(self):
        if self.apt_check.core:
            self._output['dpkg'] = self.apt_check.all_formatted

        if self.snap_check.core:
            self._output["snaps"] = self.snap_check.all_formatted


class MAASServiceChecks(maas.MAASServiceChecksBase):

    def __init__(self):
        service_exprs = maas.SERVICE_EXPRS
        super().__init__(service_exprs=service_exprs, hint_range=(0, 3),
                         ps_allow_relative=False)

    def get_running_services_info(self):
        if self.services:
            self._output['services'] = {'systemd': self.service_info,
                                        'ps': self.process_info}

    def __call__(self):
        if not self.maas_installed:
            return

        self.get_running_services_info()
