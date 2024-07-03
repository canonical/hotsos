from hotsos.core import plugintools


class StorageBase(plugintools.PluginPartBase):
    plugin_name = 'storage'
    plugin_root_index = 9

    @property
    def plugin_runnable(self):
        raise NotImplementedError
