from hotsos.core.plugins.system.system import SystemBase
from hotsos.core import plugintools


class SystemChecksBase(SystemBase, plugintools.PluginPartBase):

    @property
    def plugin_runnable(self):
        # Always run
        return True
