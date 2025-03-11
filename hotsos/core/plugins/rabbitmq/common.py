import abc
from dataclasses import dataclass, field

from hotsos.core import plugintools
from hotsos.core.host_helpers import (
    APTPackageHelper,
    InstallInfoBase,
    PebbleHelper,
    SystemdHelper,
)
from hotsos.core.plugins.rabbitmq.report import RabbitMQReport
from hotsos.core.utils import sorted_dict
from hotsos.core.ycheck.events import EventCallbackBase, EventHandlerBase

RMQ_SERVICES_EXPRS = [
    r"beam.smp",
    r"epmd",
    r"rabbitmq-server",
]
RMQ_PACKAGES = [
    r"rabbitmq-server",
]


@dataclass
class RabbitMQInstallInfo(InstallInfoBase):
    """ RabbitMQ installation information. """
    apt: APTPackageHelper = field(default_factory=lambda:
                                  APTPackageHelper(core_pkgs=RMQ_PACKAGES))
    pebble: PebbleHelper = field(default_factory=lambda:
                                 PebbleHelper(
                                            service_exprs=RMQ_SERVICES_EXPRS))
    systemd: SystemdHelper = field(default_factory=lambda:
                                   SystemdHelper(
                                            service_exprs=RMQ_SERVICES_EXPRS))


class RabbitMQChecks(plugintools.PluginPartBase):
    """ Rabbitmq checks. """
    plugin_name = 'rabbitmq'
    plugin_root_index = 7

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        RabbitMQInstallInfo().mixin(self)

    @property
    def report(self):
        return RabbitMQReport()

    @classmethod
    def is_runnable(cls):
        """
        Determine whether or not this plugin can and should be run.

        @return: True or False
        """
        if RabbitMQInstallInfo().apt.core:
            return True

        return False


class RabbitMQEventCallbackBase(EventCallbackBase):
    """ Base class for RabbitMQ events callbacks. """

    @abc.abstractmethod
    def __call__(self):
        """ Callback method. """


class RabbitMQEventHandlerBase(RabbitMQChecks, EventHandlerBase):
    """ Base class for RabbitMQ event handlers. """
    @property
    def summary(self):
        # mainline all results into summary root
        ret = self.run()
        if ret:
            return sorted_dict(ret)

        return None
