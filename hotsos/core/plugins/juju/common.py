import os

from hotsos.core.host_helpers import PebbleHelper, SystemdHelper
from hotsos.core.plugins.juju.resources import JujuBase
from hotsos.core import plugintools

SVC_VALID_SUFFIX = r'[0-9a-zA-Z-_]*'
JUJU_SVC_EXPRS = [rf'mongod{SVC_VALID_SUFFIX}',
                  rf'jujud{SVC_VALID_SUFFIX}',
                  # catch juju-db but filter out processes with juju-db in
                  # their args list.
                  rf'(?:^|[^\s])juju-db{SVC_VALID_SUFFIX}']


class JujuChecksBase(plugintools.PluginPartBase, JujuBase):
    plugin_name = 'juju'
    plugin_root_index = 12

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pebble = PebbleHelper(service_exprs=JUJU_SVC_EXPRS)
        self.systemd = SystemdHelper(service_exprs=JUJU_SVC_EXPRS)
        # this is needed for juju scenarios
        self.systemd_processes = self.systemd.processes

    @property
    def plugin_runnable(self):
        return os.path.exists(self.juju_lib_path)
