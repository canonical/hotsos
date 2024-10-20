import os
from dataclasses import dataclass, field
from functools import cached_property

from hotsos.core.host_helpers import (
    InstallInfoBase,
    PebbleHelper,
    SystemdHelper,
)
from hotsos.core.plugins.juju.resources import JujuBase
from hotsos.core import plugintools

SVC_VALID_SUFFIX = r'[0-9a-zA-Z-_]*'
JUJU_SVC_EXPRS = [rf'mongod{SVC_VALID_SUFFIX}',
                  rf'jujud{SVC_VALID_SUFFIX}',
                  # catch juju-db but filter out processes with juju-db in
                  # their args list.
                  rf'(?:^|[^\s])juju-db{SVC_VALID_SUFFIX}']


@dataclass
class JujuInstallInfo(InstallInfoBase):
    """ Juju installation information. """
    pebble: PebbleHelper = field(default_factory=lambda:
                                 PebbleHelper(service_exprs=JUJU_SVC_EXPRS))
    systemd: SystemdHelper = field(default_factory=lambda:
                                   SystemdHelper(service_exprs=JUJU_SVC_EXPRS))


class JujuChecks(plugintools.PluginPartBase, JujuBase):
    """ Juju checks. """
    plugin_name = 'juju'
    plugin_root_index = 12

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        JujuInstallInfo().mixin(self)

    @cached_property
    def systemd_processes(self):
        """
        Return a list of running processes related to the Juju service. This
        is needed for Juju scenarios.
        """
        return self.systemd.processes

    @property
    def version(self):
        if self.machine:
            return self.machine.version

        return "unknown"

    @classmethod
    def is_runnable(cls):
        """
        Determine whether or not this plugin can and should be run.

        @return: True or False
        """
        return os.path.exists(cls.get_juju_lib_path())
