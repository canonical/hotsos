from hotsos.core import plugintools


class StorageBase(plugintools.PluginPartBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
