from core.plugins.rabbitmq import RabbitMQChecksBase

YAML_PRIORITY = 0


class RabbitMQPackageChecks(RabbitMQChecksBase):

    def __call__(self):
        self._output['dpkg'] = self.apt_check.all_formatted
