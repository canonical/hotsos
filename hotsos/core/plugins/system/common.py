from hotsos.core import plugintools
from hotsos.core.plugins.system.system import SystemBase


class SystemChecksBase(SystemBase, plugintools.PluginPartBase):

    @property
    def plugin_runnable(self):
        # Always run
        return True
