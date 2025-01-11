import abc
import datetime
import json
import os
import pathlib
import pickle
import tempfile
from functools import cached_property

from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers.exceptions import (
    CLIExecError,
    SourceNotFound,
)
from hotsos.core.host_helpers.cli.catalog import (
    BinCmd,
    BinFileCmd,
    CmdOutput,
    CommandCatalog,
)
from hotsos.core.host_helpers.common import HostHelpersBase
from hotsos.core.host_helpers.exceptions import CommandNotFound
from hotsos.core.log import log


class NullSource():
    """ Exception raised to indicate that a datasource is not available. """
    def __call__(self, *args, **kwargs):
        return CmdOutput([])


class JournalctlBase():
    """ Base class for journalctl command implementations. """
    @property
    def since_date(self):
        """
        Returns a string datetime to be used with journalctl --since. This time
        reflects the maximum depth of history we will search in the journal.

        The datetime value returned takes into account config from HotSOSConfig
        and has the format "YEAR-MONTH-DAY". It does not specify a time.
        """
        current = CLIHelper().date(format="--iso-8601")
        ts = datetime.datetime.strptime(current, "%Y-%m-%d")
        if HotSOSConfig.use_all_logs:
            days = HotSOSConfig.max_logrotate_depth
        else:
            days = 1

        ts = ts - datetime.timedelta(days=days)
        return ts.strftime("%Y-%m-%d")


class JournalctlBinCmd(BinCmd, JournalctlBase):
    """ Implements binary journalctl command. """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.register_hook("pre-exec", self.format_journalctl_cmd)

    def format_journalctl_cmd(self, **kwargs):
        """ Add optional extras to journalctl command. """
        if kwargs.get("unit"):
            self.cmd = f"{self.cmd} --unit {kwargs.get('unit')}"

        if kwargs.get("date"):
            self.cmd = f"{self.cmd} --since {kwargs.get('date')}"
        else:
            self.cmd = f"{self.cmd} --since {self.since_date}"


class JournalctlBinFileCmd(BinFileCmd, JournalctlBase):
    """ Implements file-based journalctl command. """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.register_hook("pre-exec", self.preformat_sos_journalctl)

    def preformat_sos_journalctl(self, **kwargs):
        self.path = f"journalctl -oshort-iso -D {self.path}"
        if kwargs.get("unit"):
            self.path = f"{self.path} --unit {kwargs.get('unit')}"

        if kwargs.get("date"):
            self.path = f"{self.path} --since {kwargs.get('date')}"
        else:
            self.path = f"{self.path} --since {self.since_date}"


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


class CLICacheWrapper():
    """ Wrapper for cli cache. """
    def __init__(self, cache_load_f, cache_save_f):
        self.load_f = cache_load_f
        self.save_f = cache_save_f

    def load(self, key):
        return self.load_f(key)

    def save(self, key, value):
        return self.save_f(key, value)


class CLIHelperBase(HostHelpersBase):
    """ Base class for clihelper implementations. """
    def __init__(self):
        super().__init__()
        self.cli_cache = CLICacheWrapper(self.cache_load, self.cache_save)

    @property
    def cache_root(self):
        """ Cache at plugin level rather than globally. """
        return HotSOSConfig.plugin_tmp_dir

    @property
    def cache_type(self):
        return 'cli'

    @property
    def cache_name(self):
        return "commands"

    def cache_load(self, key):
        return self.cache.get(key)

    def cache_save(self, key, value):
        return self.cache.set(key, value)

    @cached_property
    def command_catalog(self):
        catalog = CommandCatalog()
        catalog.update({'journalctl':
                        [JournalctlBinCmd('journalctl -oshort-iso'),
                         JournalctlBinFileCmd('var/log/journal')]})
        return catalog

    @abc.abstractmethod
    def __getattr__(self, cmdname):
        """ This is how commands are run. The command is looked up in the
        catalog and it's runner object is returned. The caller is expetced to
        call() the returned object to execute the command.

        @param cmdname: name of command we want to execute. This must match a
        name used to register a handler in the catalog.
        @return: SourceRunner object.
        """


class CLIHelper(CLIHelperBase):
    """
    This is used when we want to have command output as the return value when
    a command is executed.
    """

    def __getattr__(self, cmdname):
        try:
            return SourceRunner(cmdname, self.command_catalog[cmdname],
                                self.cli_cache)
        except KeyError as exc:
            raise CommandNotFound(cmdname, exc) from exc


class CLIHelperFile(CLIHelperBase):
    """
    This is used when we want the return value of a command to be a path to a
    file containing the return value of executing that command.

    This will do one of two things; if the command output originates from a
    file e.g. a sosreport command output file, it will return the path to that
    file. If the command is executed as a binary, its output is written to a
    temporary file and the path to that file is returned.
    """

    def __init__(self, *args, delete_temp=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.delete_temp = delete_temp
        self._tmp_file_mtime = None

    def __enter__(self):
        return self

    def __exit__(self, *args, **kwargs):
        do_delete = (self.delete_temp or
                     self._tmp_file_mtime ==
                     os.path.getmtime(self.output_file))
        if do_delete:
            os.remove(self.output_file)

        # We want exceptions to be raised
        return False

    @cached_property
    def output_file(self):
        path = tempfile.mktemp(dir=HotSOSConfig.plugin_tmp_dir)
        pathlib.Path(path).touch()
        self._tmp_file_mtime = os.path.getmtime(path)
        return path

    def __getattr__(self, cmdname):
        try:
            ret = SourceRunner(cmdname, self.command_catalog[cmdname],
                               self.cli_cache, output_file=self.output_file)
            return ret
        except KeyError as exc:
            raise CommandNotFound(cmdname, exc) from exc

        return None
