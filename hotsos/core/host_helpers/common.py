import abc
import os

from hotsos.core.config import HotSOSConfig
from hotsos.core.log import log


class HostHelpersBase(abc.ABC):

    def __init__(self, *args, **kwargs):
        self.setup_caches()
        super().__init__(*args, **kwargs)

    @abc.abstractproperty
    def cache_name(self):
        """
        Name of subdirectory within cache used to store data for this object.
        """

    @property
    def plugin_cache_root(self):
        path = HotSOSConfig.PLUGIN_TMP_DIR
        if path is None:
            log.warning("plugin '%s' cache root not setup",
                        HotSOSConfig.PLUGIN_NAME)
            return

        return os.path.join(path, 'cache/host_helpers', self.cache_name)

    @property
    def global_cache_root(self):
        path = HotSOSConfig.GLOBAL_TMP_DIR
        if path is None:
            log.warning("global cache root not setup")
            return

        return os.path.join(path, 'cache/host_helpers', self.cache_name)

    def setup_caches(self):
        for path in [self.plugin_cache_root, self.global_cache_root]:
            if path and not os.path.isdir(path):
                os.makedirs(path)

    @abc.abstractmethod
    def cache_load(self):
        pass

    @abc.abstractmethod
    def cache_save(self):
        pass
