from hotsos.core.plugins.system.system import SystemBase
from hotsos.core import plugintools


class SystemChecks(SystemBase, plugintools.PluginPartBase):
    """ System checks. """
    plugin_name = 'system'
    plugin_root_index = 1

    @classmethod
    def is_runnable(cls):
        """
        Determine whether or not this plugin can and should be run.

        @return: True or False
        """
        # Always run
        return True
