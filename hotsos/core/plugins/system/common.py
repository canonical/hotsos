from hotsos.core.plugins.system.system import SystemBase
from hotsos.core import plugintools


class SystemChecks(SystemBase, plugintools.PluginPartBase):
    """ System checks. """
    plugin_name = 'system'
    plugin_root_index = 1

    @property
    def plugin_runnable(self):
        # Always run
        return True
