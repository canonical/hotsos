import abc

from searchkit.utils import MPCache

from hotsos.core.config import HotSOSConfig


class HostHelpersBase(abc.ABC):

    def __init__(self, *args, **kwargs):
        self.cache = MPCache(self.cache_name,
                             'host_helpers_{}'.format(self.cache_type),
                             self.cache_root)
        super().__init__(*args, **kwargs)

    @property
    def cache_root(self):
        """
        By default caches are global to all plugins but this can be overridden
        if we want otherwise.
        """
        return HotSOSConfig.global_tmp_dir

    @abc.abstractproperty
    def cache_name(self):
        """ Unique name for cache used by instance of this object. """

    @abc.abstractproperty
    def cache_type(self):
        """
        Unique name for the type of cache used by instance of this object.
        """

    @abc.abstractmethod
    def cache_load(self):
        """ Load cache contents. """

    @abc.abstractmethod
    def cache_save(self):
        """ Save contents to cache. """
