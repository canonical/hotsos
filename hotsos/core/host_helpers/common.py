import abc
import glob
import os
import re
from functools import cached_property
from dataclasses import dataclass, fields

from searchkit.utils import MPCache
from hotsos.core.config import HotSOSConfig
from hotsos.core.log import log
from hotsos.core.utils import sorted_dict


class NullCache():
    """ A cache that does nothing but maintains the MPCache abi. """

    @staticmethod
    def get(*args, **kwargs):
        log.debug("null cache get() op args=%s kwargs=%s", args, kwargs)

    @staticmethod
    def set(*args, **kwargs):
        log.debug("null cache set() op args=%s kwargs=%s", args, kwargs)


class HostHelpersBase(abc.ABC):
    """ Base class for all hosthelpers. """
    def __init__(self, *args, **kwargs):
        if not self.cache_root or not os.path.exists(self.cache_root):
            log.debug("cache root invalid or does not exist so disabling %s "
                      "cache", self.__class__.__name__)
            self.cache = NullCache()
        else:
            self.cache = MPCache(self.cache_name,
                                 f'host_helpers_{self.cache_type}',
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
    """ Base class for service manager helper implementations. """
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

    @property
    @abc.abstractmethod
    def _service_manager_type(self):
        """ A string name representing the type of service manager e.g.
        'systemd' """

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

        return None

    @property
    @abc.abstractmethod
    def _service_filtered_ps(self):
        """ Return a list ps entries corresponding to services. """

    @cached_property
    def processes(self):
        """
        Identify running processes from ps that are associated with resolved
        services. The search pattern used to identify a service is also
        used to match the process binaryc/cmd name.

        Accounts for different types of process cmd path e.g.

        /snap/<name>/1830/<svc>
        /usr/bin/<svc>

        and filter e.g.

        /var/lib/<svc> and /var/log/<svc>

        Returns a dictionary of process names along with the number of each.
        """
        _proc_info = {}
        for line in self._service_filtered_ps:
            for expr in self._service_exprs:
                cmd = self.get_cmd_from_ps_line(line, expr)
                if not cmd:
                    continue

                if cmd in _proc_info:
                    _proc_info[cmd] += 1
                else:
                    _proc_info[cmd] = 1

        return _proc_info

    @property
    @abc.abstractmethod
    def services(self):
        """ Return a dictionary of identified services and their state. """

    @property
    def _service_info(self):
        """Return a dictionary of services grouped by state. """
        info = {}
        for svc, obj in sorted_dict(self.services).items():
            state = obj.state
            if state not in info:
                info[state] = []

            info[state].append(svc)

        return info

    @property
    def _process_info(self):
        """Return a list of processes associated with services. """
        return [f"{name} ({count})"
                for name, count in sorted_dict(self.processes).items()]

    @property
    def summary(self):
        """
        Output a dict summary of this class i.e. services, their state and any
        processes run by them.
        """
        return {self._service_manager_type: self._service_info,
                'ps': self._process_info}


def get_ps_axo_flags_available():
    path = os.path.join(HotSOSConfig.data_root,
                        "sos_commands/process/ps_axo_flags_state_"
                        "uid_pid_ppid_pgid_sid_cls_pri_addr_sz_wchan*_lstart_"
                        "tty_time_cmd")
    _paths = []
    for path in glob.glob(path):
        _paths.append(path)

    if not _paths:
        return None

    # strip data_root since it will be prepended later
    return _paths[0].partition(HotSOSConfig.data_root)[2]


@dataclass
class InstallInfoBase():
    """
    Provides a common way to define install information such as packages and
    runtime services assocated with a plugin.

    To use this class it should be re-implemented as a dataclass that
    initialises the required attributes. It can then either be inherited or
    mixed in to avoid issues with excessive inheritance.
    """
    apt: None = None
    pebble: None = None
    snaps: None = None
    systemd: None = None

    def mixin(self, _self):
        for attr in fields(self):
            val = getattr(self, attr.name)
            if val is None:
                continue

            setattr(_self, attr.name, val)
