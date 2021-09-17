from core import (
    checks,
    plugintools,
)

RMQ_SERVICES_EXPRS = [
    r"beam.smp",
    r"epmd",
    r"rabbitmq-server",
]
RMQ_PACKAGES = [
    r"rabbitmq-server",
]


class RabbitMQBase(object):
    pass


class RabbitMQChecksBase(RabbitMQBase, plugintools.PluginPartBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apt_check = checks.APTPackageChecksBase(core_pkgs=RMQ_PACKAGES)

    @property
    def plugin_runnable(self):
        if self.apt_check.core:
            return True

        return False


class RabbitMQServiceChecksBase(RabbitMQChecksBase, checks.ServiceChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(service_exprs=RMQ_SERVICES_EXPRS,
                         *args, hint_range=(0, 3), **kwargs)


class RabbitMQEventChecksBase(RabbitMQChecksBase, checks.EventChecksBase):

    def __call__(self):
        ret = self.run_checks()
        if ret:
            self._output.update(ret)
