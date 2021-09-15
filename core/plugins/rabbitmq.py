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


class RabbitMQChecksBase(RabbitMQBase, plugintools.PluginPartBase,
                         checks.ServiceChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(service_exprs=RMQ_SERVICES_EXPRS,
                         *args, hint_range=(0, 3), **kwargs)
        self.apt_check = checks.APTPackageChecksBase(core_pkgs=RMQ_PACKAGES)

    @property
    def plugin_runnable(self):
        if self.apt_check.core:
            return True

        return False


class RabbitMQEventChecksBase(RabbitMQBase, checks.EventChecksBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apt_check = checks.APTPackageChecksBase(core_pkgs=RMQ_PACKAGES)

    @property
    def plugin_runnable(self):
        if self.apt_check.core:
            return True

        return False
