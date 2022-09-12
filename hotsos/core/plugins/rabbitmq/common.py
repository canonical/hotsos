from hotsos.core import plugintools
from hotsos.core.host_helpers import APTPackageHelper, SystemdHelper
from hotsos.core.plugins.rabbitmq.report import RabbitMQReport

RMQ_SERVICES_EXPRS = [
    r"beam.smp",
    r"epmd",
    r"rabbitmq-server",
]
RMQ_PACKAGES = [
    r"rabbitmq-server",
]


class RabbitMQBase(object):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.report = RabbitMQReport()


class RabbitMQChecksBase(RabbitMQBase, plugintools.PluginPartBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.apt = APTPackageHelper(core_pkgs=RMQ_PACKAGES)
        self.systemd = SystemdHelper(service_exprs=RMQ_SERVICES_EXPRS)

    @property
    def plugin_runnable(self):
        if self.apt.core:
            return True

        return False
