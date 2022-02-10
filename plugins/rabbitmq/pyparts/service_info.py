from core.plugins.rabbitmq import RabbitMQServiceChecksBase

YAML_PRIORITY = 0


class RabbitMQServiceChecks(RabbitMQServiceChecksBase):

    def __call__(self):
        if not self.plugin_runnable:
            return

        if self.services:
            self._output['services'] = {'systemd': self.service_info,
                                        'ps': self.process_info}

        apt = self.apt_check.all_formatted
        if apt:
            self._output['dpkg'] = apt
