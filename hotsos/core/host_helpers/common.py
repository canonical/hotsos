import abc
import glob
import json
import os
import pickle
import re
from functools import cached_property
from dataclasses import dataclass

from searchkit.utils import MPCache
from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers.exceptions import (
    CLIExecError,
    SourceNotFound,
)
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


class NullSource():
    """ Exception raised to indicate that a datasource is not available. """
    def __call__(self, *args, **kwargs):
        return CmdOutput([])


@dataclass(frozen=True)
class CmdOutput():
    """ Representation of the output of a command. """

    # Output value.
    value: str
    # Optional command source path.
    source: str = None


class SourceRunner():
    """ Manager to control how we execute commands.

    Ensures that we try data sources in a consistent order.
    """
    def __init__(self, cmdkey, sources, cache, output_file=None):
        """
        @param cmdkey: unique key identifying this command.
        @param sources: list of command source implementations.
        @param cache: CLICacheWrapper object.
        """
        self.cmdkey = cmdkey
        self.sources = sources
        self.cache = cache
        self.output_file = output_file
        # Command output can differ between CLIHelper and CLIHelperFile so we
        # need to cache them separately.
        if output_file:
            self.cache_cmdkey = f"{cmdkey}.file"
        else:
            self.cache_cmdkey = cmdkey

    def bsource(self, *args, **kwargs):
        # binary sources only apply if data_root is system root
        bin_out = None
        for bsource in [s for s in self.sources if s.TYPE == "BIN"]:
            cache = False
            # NOTE: we currently only support caching commands with no
            #       args.
            if not any([args, kwargs]):
                cache = True
                out = self.cache.load(self.cache_cmdkey)
                if out is not None:
                    return out

            try:
                if self.output_file:
                    # don't decode if we are going to be saving to a file
                    kwargs['skip_json_decode'] = True

                bin_out = bsource(*args, **kwargs)
                if cache and bin_out is not None:
                    try:
                        self.cache.save(self.cache_cmdkey, bin_out)
                    except pickle.PicklingError as exc:
                        log.info("unable to cache command '%s' output: %s",
                                 self.cmdkey, exc)

                # if command executed but returned nothing that still counts
                # as success.
                break
            except CLIExecError as exc:
                bin_out = CmdOutput(exc.return_value)

        return bin_out

    def fsource(self, *args, **kwargs):
        for fsource in [s for s in self.sources if s.TYPE == "FILE"]:
            try:
                skip_load_contents = False
                if self.output_file:
                    skip_load_contents = True

                return fsource(*args, **kwargs,
                               skip_load_contents=skip_load_contents)
            except CLIExecError as exc:
                return CmdOutput(exc.return_value)
            except SourceNotFound:
                pass

        return None

    def _execute(self, *args, **kwargs):
        # always try file sources first
        ret = self.fsource(*args, **kwargs)
        if ret is not None:
            return ret

        if HotSOSConfig.data_root != '/':
            return NullSource()()

        return self.bsource(*args, **kwargs)

    def __call__(self, *args, **kwargs):
        """
        Execute the command using the appropriate source runner. These can be
        binary or file-based depending on whether data root points to / or a
        sosreport. File-based are attempted first.

        A command can have more than one source implementation so we must
        ensure they all have a chance to run.
        """
        out = self._execute(*args, **kwargs)
        if self.output_file:
            if out.source is not None:
                return out.source

            with open(self.output_file, 'w', encoding='utf-8') as fd:
                if isinstance(out.value, list):
                    fd.write(''.join(out.value))
                elif isinstance(out.value, dict):
                    fd.write(json.dumps(out.value))
                else:
                    fd.write(out.value)

                return self.output_file

        return out.value


def run_pre_exec_hooks(f):
    """ pre-exec hooks are run before running __call__ method.

    These hooks are not expected to return anything and are used to manipulate
    the instance variables used by the main __call__ method.
    """
    def run_pre_exec_hooks_inner(self, *args, **kwargs):
        hook = self.hooks.get("pre-exec")
        if hook:
            # no return expected
            hook(*args, **kwargs)

        return f(self, *args, **kwargs)

    return run_pre_exec_hooks_inner


def run_post_exec_hooks(f):
    """ post-exec hooks are run after running __call__ method and take its
    output as input.
    """
    def run_post_exec_hooks_inner(self, *args, **kwargs):
        out = f(self, *args, **kwargs)
        hook = self.hooks.get("post-exec")
        if hook:
            out = hook(out, *args, **kwargs)

        return out

    return run_post_exec_hooks_inner


def reset_command(f):
    """
    This should be run by all commands as their last action after all/any hooks
    have run.
    """
    def reset_command_inner(self, *args, **kwargs):
        out = f(self, *args, **kwargs)
        self.reset()
        return out

    return reset_command_inner


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
