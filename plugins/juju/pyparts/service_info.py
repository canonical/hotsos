from core.plugins.juju import JujuServiceChecksBase

YAML_PRIORITY = 0


class JujuServiceInfo(JujuServiceChecksBase):

    def __call__(self):
        if self.services:
            self._output['services'] = self.service_info_str
