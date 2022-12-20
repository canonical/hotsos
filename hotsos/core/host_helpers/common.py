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
        path = HotSOSConfig.plugin_tmp_dir
        if path is None:
            log.warning("plugin '%s' cache root not setup",
                        HotSOSConfig.plugin_name)
            return

        return os.path.join(path, 'cache/host_helpers', self.cache_name)

    @property
    def global_cache_root(self):
        path = HotSOSConfig.global_tmp_dir
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


class HostHelperFactoryBase(abc.ABC):
    """
    Provide a common way to implement factory objects for host helpers.

    The basic idea is that implementations of this class are instantiated and
    then content is generated using attrs as input. This provides a way e.g. to
    defer operations on a set of data that need only be retrieved once.
    """

    @abc.abstractmethod
    def __getattr__(self, name):
        """
        All factory implementations must implement this method to
        allow them to dynamically generate objects from arbitrary input
        provided by calling as an attribute on this object.
        """
