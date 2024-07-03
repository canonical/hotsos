import abc
import os
import re

from searchkit.utils import MPCache
from hotsos.core.config import HotSOSConfig
from hotsos.core.log import log


class NullCache():
    """ A cache that does nothing but maintains the MPCache abi. """

    @staticmethod
    def get(*args, **kwargs):
        log.debug("null cache get() op args=%s kwargs=%s", args, kwargs)

    @staticmethod
    def set(*args, **kwargs):
        log.debug("null cache set() op args=%s kwargs=%s", args, kwargs)


class HostHelpersBase(abc.ABC):

    def __init__(self, *args, **kwargs):
        if not self.cache_root or not os.path.exists(self.cache_root):
            log.debug("cache root invalid or does not exist so disabling %s "
                      "cache", self.__class__.__name__)
            self.cache = NullCache()
        else:
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

    @property
    @abc.abstractmethod
    def cache_name(self):
        """ Unique name for cache used by instance of this object. """

    @property
    @abc.abstractmethod
    def cache_type(self):
        """
        Unique name for the type of cache used by instance of this object.
        """

    @abc.abstractmethod
    def cache_load(self, key):
        """ Load cache contents. """

    @abc.abstractmethod
    def cache_save(self, key, value):
        """ Save contents to cache. """


class ServiceManagerBase(abc.ABC):
    PS_CMD_EXPR_TEMPLATES = {
        'absolute': r".+\S+bin/({})(?:\s+.+|$)",
        'snap': r".+\S+\d+/({})(?:\s+.+|$)",
        'relative': r".+\s({})(?:\s+.+|$)",
    }

    def __init__(self, service_exprs, ps_allow_relative=True):
        """
        @param service_exprs: list of python.re expressions used to match
                              service names.
        @param ps_allow_relative: whether to allow commands to be identified
                                  from ps as run using an relative binary
                                  path e.g. mycmd as opposed to /bin/mycmd.
        """
        self._ps_allow_relative = ps_allow_relative
        self._service_exprs = set(service_exprs)

    def get_cmd_from_ps_line(self, line, expr):
        """
        Match a command in ps output line.

        @param line: line from ps output
        @param expr: regex to match a command. See PS_CMD_EXPR_TEMPLATES.
        @param return: matched command name.
        """
        for expr_type, expr_tmplt in self.PS_CMD_EXPR_TEMPLATES.items():
            if expr_type == 'relative' and not self._ps_allow_relative:
                continue

            ret = re.compile(expr_tmplt.format(expr)).match(line)
            if ret:
                cmd = ret.group(1)
                log.debug("matched command '%s' with expr type '%s'", cmd,
                          expr_type)
                return cmd

    @property
    @abc.abstractmethod
    def services(self):
        """ Return a dictionary of identified services and their state. """

    @property
    @abc.abstractmethod
    def processes(self):
        """
        Return a dictionary of processes associated with identified
        services.
        """

    @property
    @abc.abstractmethod
    def summary(self):
        """ Return a dictionary summary of this class i.e. services,
        their state and associated processes.
        """
