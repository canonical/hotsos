import abc
import datetime
import glob
import json
import os
import pathlib
import pickle
import re
import subprocess
import tempfile
from functools import cached_property

from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers.common import HostHelpersBase
from hotsos.core.log import log

CLI_COMMON_EXCEPTIONS = (OSError, subprocess.CalledProcessError,
                         subprocess.TimeoutExpired,
                         json.JSONDecodeError)


class CLIExecError(Exception):

    def __init__(self, return_value=None):
        """
        @param return_value: default return value that a command
                             should return if execution fails.
        """
        self.return_value = return_value


def catch_exceptions(*exc_types):
    def catch_exceptions_inner1(f):
        def catch_exceptions_inner2(*args, **kwargs):
            try:
                return f(*args, **kwargs)
            except exc_types as exc:
                msg = f"{type(exc)}: {exc}"
                if isinstance(exc, subprocess.TimeoutExpired):
                    log.info(msg)
                else:
                    log.debug(msg)

                if isinstance(exc, json.JSONDecodeError):
                    raise CLIExecError(return_value={}) from exc

                raise CLIExecError(return_value=[]) from exc

        return catch_exceptions_inner2

    return catch_exceptions_inner1


class SourceNotFound(Exception):
    def __init__(self, path):
        self.path = path

    def __repr__(self):
        return f"source path '{self.path}' not found"


class CommandNotFound(Exception):
    def __init__(self, cmd, msg):
        self.msg = f"command '{cmd}' not found in catalog: '{msg}'"

    def __str__(self):
        return self.msg


class NullSource():
    def __call__(self, *args, **kwargs):
        return CmdOutput([])


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


class CmdOutput():
    def __init__(self, value, source=None):
        self.value = value
        self.source = source


class CmdBase():
    """ Base class for all command source types. """

    def __init__(self):
        self.hooks = {}
        self.reset()

    def reset(self):
        """
        Used to reset an object after it has been called. In other words, each
        time a command object is called it may alter its initial state e.g. via
        hooks but this state should not persist to the next call so this is
        used to restore state.
        """
        raise NotImplementedError

    @classmethod
    def safe_readlines(cls, path):
        with open(path, 'r', errors="surrogateescape") as fd:
            return fd.readlines()

    def register_hook(self, name, f):
        """
        Implementations of this class can register hooks to
        be run when the __call__ method is executed. Currently
        supported hooks include:

            * pre-exec - run before __call__ method.
            * post-exec - run after __call__ method and take its output as
                          input.
        """
        self.hooks[name] = f


class BinCmd(CmdBase):
    TYPE = "BIN"

    def __init__(self, cmd, json_decode=False, singleline=False):
        """
        @param cmd: command in string format (not list)
        """
        self.cmd = self.original_cmd = cmd
        self.original_cmd_extras = []
        self.original_json_decode = json_decode
        self.original_singleline = singleline
        super().__init__()

    def reset(self):
        self.cmd = self.original_cmd
        self.original_cmd_extras = []
        self.json_decode = self.original_json_decode
        self.singleline = self.original_singleline

    @catch_exceptions(*CLI_COMMON_EXCEPTIONS)
    @reset_command
    @run_post_exec_hooks
    @run_pre_exec_hooks
    def __call__(self, *args, skip_json_decode=False, **kwargs):
        cmd = self.cmd
        if args:
            cmd = cmd.format(*args)

        if kwargs:
            cmd = cmd.format(**kwargs)

        _cmd = cmd.split() + self.original_cmd_extras
        out = subprocess.run(_cmd, timeout=HotSOSConfig.command_timeout,
                             capture_output=True, check=False)
        output = out.stdout
        if out.stderr:
            output += out.stderr

        if out.returncode != 0:
            log.info("command '%s' exited with non-zero code '%s'", cmd,
                     out.returncode)

        try:
            output = output.decode('UTF-8')
        except UnicodeDecodeError:
            log.exception("failed to decode command output for '%s'", cmd)
            output = ''

        if self.json_decode and not skip_json_decode:
            return CmdOutput(json.loads(output))

        if self.singleline:
            return CmdOutput(output.strip())

        return CmdOutput(output.splitlines(keepends=True))


class FileCmd(CmdBase):
    TYPE = "FILE"

    def __init__(self, path, json_decode=False,
                 singleline=False, decode_error_handling=None):
        self.path = self.original_path = os.path.join(HotSOSConfig.data_root,
                                                      path)
        self.original_json_decode = json_decode
        self.original_singleline = singleline
        self.original_decode_error_handling = decode_error_handling
        super().__init__()

    def reset(self):
        self.path = self.original_path
        self.json_decode = self.original_json_decode
        self.singleline = self.original_singleline
        self.decode_error_handling = self.original_decode_error_handling

    @catch_exceptions(*CLI_COMMON_EXCEPTIONS)
    @reset_command
    @run_post_exec_hooks
    @run_pre_exec_hooks
    def __call__(self, *args, skip_load_contents=False, **kwargs):
        if args:
            self.path = self.path.format(*args)

        if kwargs:
            self.path = self.path.format(**kwargs)

        if not os.path.exists(self.path):
            raise SourceNotFound(self.path)

        if skip_load_contents:
            CmdOutput(None, self.path)

        # NOTE: any post-exec hooks must be aware that their input will be
        # defined by the following.
        if self.json_decode:
            with open(self.path) as fd:
                output = json.load(fd)
        else:
            output = []
            ln = 0
            with open(self.path, 'rb') as fd:
                for line in fd:
                    ln += 1
                    try:
                        decode_kwargs = {}
                        if self.decode_error_handling:
                            decode_kwargs['errors'] = \
                                                     self.decode_error_handling

                        _out = line.decode(**decode_kwargs)
                        output.append(_out)
                    except UnicodeDecodeError:
                        # maintain line count but store empty line.
                        # we could in the future consider other decode options
                        # as a fallback.
                        output.append('')
                        log.exception("failed to decode line %s "
                                      "(decode_error_handling=%s)", ln,
                                      self.decode_error_handling)

                    if self.singleline:
                        break

            if self.singleline:
                return CmdOutput(output[0].strip(), self.path)

        return CmdOutput(output, self.path)


class BinFileCmd(FileCmd):
    """ This is used when we are executing an actual binary/command against a
    file. """

    @catch_exceptions(*CLI_COMMON_EXCEPTIONS)
    @reset_command
    @run_post_exec_hooks
    @run_pre_exec_hooks
    def __call__(self, *args, **kwargs):
        if not os.path.exists(self.original_path):
            raise SourceNotFound(self.original_path)

        if args:
            self.path = self.path.format(*args)

        if kwargs:
            self.path = self.path.format(**kwargs)

        # If this file is part of a sosreport we want to make sure it is run
        # in the same timezone context as the sosreport host.
        env = {}
        try:
            env['TZ'] = DateFileCmd('sos_commands/date/date',
                                    singleline=True)(format="+%Z").value
        except SourceNotFound:
            pass

        # Now split into a command and run
        output = subprocess.check_output(self.path.split(),
                                         timeout=HotSOSConfig.command_timeout,
                                         stderr=subprocess.STDOUT, env=env)

        output = output.decode('UTF-8')
        return CmdOutput(output.splitlines(keepends=True))


class JournalctlBase():

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


class OVSAppCtlBinCmd(BinCmd):

    def __call__(self, *args, **kwargs):
        # Set defaults for optional args
        for key in ['flags', 'args']:
            if key not in kwargs:
                kwargs[key] = ''

        return super().__call__(*args, **kwargs)


class OVSAppCtlFileCmd(FileCmd):

    def __call__(self, *args, **kwargs):
        for key in ['flags', 'args']:
            if key in kwargs:
                kwargs[key] = f'_{kwargs[key]}'
            else:
                kwargs[key] = ''

        if 'args' in kwargs and kwargs['command'].startswith('dpctl/'):
            # e.g. this would be for dpctl datapath
            kwargs['args'] = kwargs['args'].replace('@', '_')

        kwargs['command'] = kwargs['command'].replace('/', '.')
        try:
            out = super().__call__(*args, **kwargs)
        except SourceNotFound:
            log.debug("%s: source not found: %s", self.__class__.__name__,
                      self.path)
            raise

        return out


class OVSOFCtlCmdBase():
    OFPROTOCOL_VERSIONS = ['OpenFlow15', 'OpenFlow14', 'OpenFlow13',
                           'OpenFlow12', 'OpenFlow11', 'OpenFlow10']


class OVSOFCtlBinCmd(OVSOFCtlCmdBase, BinCmd):

    def __call__(self, *args, **kwargs):
        """
        First try without specifying protocol version. If error is raised
        try with different versions until we get a result.
        """
        self.cmd = f"ovs-ofctl {self.cmd}"
        try:
            return super().__call__(*args, **kwargs)
        except CLIExecError:
            log.debug("%s: command with no protocol version failed",
                      self.__class__.__name__)

        # If the command raised an exception it will have been caught by the
        # catch_exceptions decorator and [] returned. We have no way of knowing
        # if that was the actual return or an exception was raised so we just
        # go ahead and retry with specific OF versions until we get a result.
        for ver in self.OFPROTOCOL_VERSIONS:
            log.debug("%s: trying again with protocol version %s",
                      self.__class__.__name__, ver)
            self.reset()
            self.cmd = f"ovs-ofctl -O {ver} {self.cmd}"
            try:
                return super().__call__(*args, **kwargs)
            except CLIExecError:
                log.debug("%s: command with protocol version %s failed",
                          self.__class__.__name__, ver)

        return CmdOutput([])


class OVSOFCtlFileCmd(OVSOFCtlCmdBase, FileCmd):

    def __call__(self, *args, **kwargs):
        """
        We do this in reverse order to bin command since it won't actually
        raise an error.
        """
        for ver in self.OFPROTOCOL_VERSIONS:
            log.debug("%s: trying again with protocol version %s",
                      self.__class__.__name__, ver)
            self.reset()
            try:
                kwargs['ofversion'] = f'_-O_{ver}'
                out = super().__call__(*args, **kwargs)
                if out.value and 'version negotiation failed' in out.value[0]:
                    continue

                return out
            except SourceNotFound:
                pass

        try:
            kwargs['ofversion'] = ''
            return super().__call__(*args, **kwargs)
        except SourceNotFound:
            log.debug("%s: command with no protocol version failed",
                      self.__class__.__name__)

        return None


class DateBinCmd(BinCmd):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.register_hook("pre-exec", self.format_date_cmd)

    def format_date_cmd(self, **kwargs):
        """ Add formatting to date command. """
        no_format = kwargs.get('no_format', False)
        fmt = kwargs.get('format')
        if not no_format and fmt is None:
            fmt = '+%s'

        self.cmd = f'{self.cmd} --utc'
        if fmt:
            # this can't get split() so add to the end of the command list
            self.original_cmd_extras = [fmt]


class DateFileCmd(FileCmd):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.register_hook("post-exec", self.format_date)

    def format_date(self, output, **kwargs):
        """ Apply some post-processing to the date output.

        @param output: CmdOutput object
        """
        no_format = kwargs.get('no_format', False)
        fmt = kwargs.get('format')
        if not no_format and fmt is None:
            fmt = '+%s'

        ret = re.match(r"^(\S+ \S*\s*[0-9]+ [0-9:]+)\s*"
                       r"([A-Z]*|[+-]?[0-9]*)?"
                       r"\s*([0-9]+)$",
                       output.value)

        if ret is None:
            log.error("%s has invalid date string '%s'", self.path,
                      output.value)
            return CmdOutput('', self.path)

        tz = ret[2]
        # NOTE: date command doesn't recognise HKT for some reason so we
        # convert to a format that is recognised.
        if tz == 'HKT':
            tz = 'UTC+8'

        # Include tz if available and then convert to utc
        date = f"{ret[1]} {tz} {ret[3]}"
        cmd = ["date", "--utc", f"--date={date}"]
        if fmt:
            cmd.append(fmt)

        output = subprocess.check_output(cmd,
                                         timeout=HotSOSConfig.command_timeout)
        # date sometimes adds multiple whitespaces between fields so collapse
        # them.
        output = re.compile(r"\s+").sub(' ', output.decode('UTF-8'))
        ret = output.splitlines(keepends=True)[0]
        # always singleline so always strip trailing newline
        return CmdOutput(ret.strip(), self.path)


class CephJSONFileCmd(FileCmd):
    """
    Some ceph commands that use --format json have some extra text added to the
    end of the file (typically from stderr) which causes it to be invalid json
    so we have to strip that final line before decoding the contents.
    """
    def __init__(self, *args, first_line_filter=None, last_line_filter=None,
                 **kwargs):
        super().__init__(*args, **kwargs)
        if first_line_filter or last_line_filter:
            self.register_hook('pre-exec', self.format_json_contents)
            self.register_hook('post-exec', self.cleanup)
            self.orig_path = None
            self.first_line_filter = first_line_filter
            self.last_line_filter = last_line_filter

    def format_json_contents(self, *_args, **_kwargs):
        if not os.path.exists(self.path):
            raise SourceNotFound(self.path)

        with open(self.path) as f:
            lines = f.readlines()

        if self.first_line_filter:
            line_filter = self.first_line_filter
        else:
            line_filter = self.last_line_filter

        if lines and lines[-1].startswith(line_filter):
            lines = lines[:-1]
            with tempfile.NamedTemporaryFile(mode='w+t', delete=False) as tmp:
                tmp.write(''.join(lines))
                tmp.close()
                self.orig_path = self.path
                self.path = tmp.name

    def cleanup(self, output, **_kwargs):
        """
        @param output: CmdOutput object
        """
        if self.orig_path:
            os.unlink(self.path)
            self.path = self.orig_path
            self.orig_path = None

        return output


class SourceRunner():

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

            with open(self.output_file, 'w') as fd:
                if isinstance(out.value, list):
                    fd.write(''.join(out.value))
                elif isinstance(out.value, dict):
                    fd.write(json.dumps(out.value))
                else:
                    fd.write(out.value)

                return self.output_file

        return out.value


class CLICacheWrapper():

    def __init__(self, cache_load_f, cache_save_f):
        self.load_f = cache_load_f
        self.save_f = cache_save_f

    def load(self, key):
        return self.load_f(key)

    def save(self, key, value):
        return self.save_f(key, value)


class CLIHelperBase(HostHelpersBase):

    def __init__(self):
        self._command_catalog = None
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

    @property
    def command_catalog(self):
        if self._command_catalog:
            return self._command_catalog

        self._command_catalog = {
            'apt_config_dump':
                [BinCmd('apt-config dump'),
                 FileCmd('sos_commands/apt/apt-config_dump')],
            'apparmor_status':
                [BinCmd('apparmor_status'),
                 FileCmd('sos_commands/apparmor/apparmor_status')],
            'ceph_daemon_osd_config_show':
                [BinCmd('ceph daemon osd.{osd_id} config show',
                        json_decode=True),
                 # requires sosreport 4.3 or above
                 FileCmd('sos_commands/ceph_osd/'
                         'ceph_daemon_osd.{osd_id}_config_show',
                         json_decode=True)],
            'ceph_daemon_osd_dump_mempools':
                [BinCmd('ceph daemon osd.{osd_id} dump mempools',
                        json_decode=True),
                 # requires sosreport 4.3 or above
                 FileCmd('sos_commands/ceph_osd/'
                         'ceph_daemon_osd.{osd_id}_dump_mempools',
                         json_decode=True)],
            'ceph_health_detail_json_decoded':
                [BinCmd('ceph health detail --format json-pretty',
                        json_decode=True),
                 # sosreport < 4.2
                 FileCmd('sos_commands/ceph/json_output/'
                         'ceph_health_detail_--format_json-pretty',
                         json_decode=True),
                 # sosreport >= 4.2
                 FileCmd('sos_commands/ceph_mon/json_output/'
                         'ceph_health_detail_--format_json-pretty',
                         json_decode=True)],
            'ceph_mon_dump_json_decoded':
                [BinCmd('ceph mon dump --format json-pretty',
                        json_decode=True),
                 # sosreport < 4.2
                 CephJSONFileCmd('sos_commands/ceph/json_output/'
                                 'ceph_mon_dump_--format_json-pretty',
                                 json_decode=True,
                                 first_line_filter='dumped monmap epoch',
                                 last_line_filter='dumped monmap epoch'),
                 # sosreport >= 4.2
                 CephJSONFileCmd('sos_commands/ceph_mon/json_output/'
                                 'ceph_mon_dump_--format_json-pretty',
                                 json_decode=True,
                                 first_line_filter='dumped monmap epoch',
                                 last_line_filter='dumped monmap epoch')],
            'ceph_osd_dump_json_decoded':
                [BinCmd('ceph osd dump --format json-pretty',
                        json_decode=True),
                 # sosreport < 4.2
                 FileCmd('sos_commands/ceph/json_output/'
                         'ceph_osd_dump_--format_json-pretty',
                         json_decode=True),
                 # sosreport >= 4.2
                 FileCmd('sos_commands/ceph_mon/json_output/'
                         'ceph_osd_dump_--format_json-pretty',
                         json_decode=True)],
            'ceph_df_json_decoded':
                [BinCmd('ceph df --format json-pretty',
                        json_decode=True),
                 # sosreport < 4.2
                 FileCmd('sos_commands/ceph/json_output/'
                         'ceph_df_--format_json-pretty',
                         json_decode=True),
                 # sosreport >= 4.2
                 FileCmd('sos_commands/ceph_mon/json_output/'
                         'ceph_df_--format_json-pretty',
                         json_decode=True)],
            'ceph_osd_df_tree_json_decoded':
                [BinCmd('ceph osd df tree --format json-pretty',
                        json_decode=True),
                 # sosreport < 4.2
                 FileCmd('sos_commands/ceph/json_output/'
                         'ceph_osd_df_tree_--format_json-pretty',
                         json_decode=True),
                 # sosreport >= 4.2
                 FileCmd('sos_commands/ceph_mon/json_output/'
                         'ceph_osd_df_tree_--format_json-pretty',
                         json_decode=True)],
            'ceph_osd_crush_dump_json_decoded':
                [BinCmd('ceph osd crush dump', json_decode=True),
                 # sosreport < 4.2
                 FileCmd('sos_commands/ceph/ceph_osd_crush_dump',
                         json_decode=True),
                 # sosreport >= 4.2
                 FileCmd('sos_commands/ceph_mon/ceph_osd_crush_dump',
                         json_decode=True),
                 ],
            'ceph_pg_dump_json_decoded':
                [BinCmd('ceph pg dump --format json-pretty',
                        json_decode=True),
                 # sosreport < 4.2
                 CephJSONFileCmd('sos_commands/ceph/json_output/'
                                 'ceph_pg_dump_--format_json-pretty',
                                 json_decode=True,
                                 first_line_filter='dumped all',
                                 last_line_filter='dumped all'),
                 # sosreport >= 4.2
                 CephJSONFileCmd('sos_commands/ceph_mon/json_output/'
                                 'ceph_pg_dump_--format_json-pretty',
                                 json_decode=True,
                                 first_line_filter='dumped all',
                                 last_line_filter='dumped all')],
            'ceph_status_json_decoded':
                [BinCmd('ceph status --format json-pretty', json_decode=True),
                 # sosreport < 4.2
                 FileCmd('sos_commands/ceph/json_output/'
                         'ceph_status_--format_json-pretty',
                         json_decode=True),
                 # sosreport >= 4.2
                 FileCmd('sos_commands/ceph_mon/'
                         'json_output/ceph_status_--format_json-pretty',
                         json_decode=True),
                 ],
            'ceph_versions':
                [BinCmd('ceph versions'),
                 # sosreport < 4.2
                 FileCmd('sos_commands/ceph/ceph_versions'),
                 # sosreport >= 4.2
                 FileCmd('sos_commands/ceph_mon/ceph_versions'),
                 ],
            'ceph_volume_lvm_list':
                [BinCmd('ceph-volume lvm list'),
                 # sosreport < 4.2
                 FileCmd('sos_commands/ceph/ceph-volume_lvm_list'),
                 # sosreport >= 4.2
                 FileCmd('sos_commands/ceph_osd/ceph-volume_lvm_list'),
                 ],
            'ceph_report_json_decoded':
                [BinCmd('ceph report', json_decode=True),
                 # sosreport < 4.2
                 CephJSONFileCmd('sos_commands/ceph/ceph_report',
                                 json_decode=True,
                                 first_line_filter='report',
                                 last_line_filter='report'),
                 # sosreport >= 4.2
                 CephJSONFileCmd('sos_commands/ceph_mon/ceph_report',
                                 json_decode=True,
                                 first_line_filter='report',
                                 last_line_filter='report'),
                 ],
            'ceph_mgr_module_ls':
                [BinCmd('ceph mgr module ls', json_decode=True),
                 # sosreport < 4.2
                 CephJSONFileCmd('sos_commands/ceph/ceph_mgr_module_ls',
                                 json_decode=True),
                 # sosreport >= 4.2
                 CephJSONFileCmd('sos_commands/ceph_mon/ceph_mgr_module_ls',
                                 json_decode=True),
                 ],
            'date':
                [DateBinCmd('date', singleline=True),
                 DateFileCmd('sos_commands/date/date', singleline=True),
                 # this is for legacy sosreport versions
                 DateFileCmd('sos_commands/general/date', singleline=True)],
            'df':
                [BinCmd('df'),
                 FileCmd('df')],
            'dmesg':
                [BinCmd('dmesg'),
                 FileCmd('sos_commands/kernel/dmesg')],
            'docker_images':
                [BinCmd('docker images'),
                 FileCmd('sos_commands/docker/docker_images')],
            'docker_ps':
                [BinCmd('docker ps'),
                 FileCmd('sos_commands/docker/docker_ps')],
            'dpkg_l':
                [BinCmd('dpkg -l'),
                 FileCmd('sos_commands/dpkg/dpkg_-l',
                         decode_error_handling='surrogateecape')],
            'ethtool':
                [BinCmd('ethtool {interface}'),
                 FileCmd('sos_commands/networking/ethtool_{interface}')],
            'hostname':
                [BinCmd('hostname', singleline=True),
                 FileCmd('hostname', singleline=True)],
            'hostnamectl':
                [BinCmd('hostnamectl'),
                 FileCmd('sos_commands/host/hostnamectl_status')],
            'ip_netns':
                [BinCmd('ip netns'),
                 FileCmd('sos_commands/networking/ip_netns')],
            'ip_addr':
                [BinCmd('ip -d address'),
                 FileCmd('sos_commands/networking/ip_-d_address')],
            'ip_link':
                [BinCmd('ip -s -d link'),
                 FileCmd('sos_commands/networking/ip_-s_-d_link')],
            'journalctl':
                [JournalctlBinCmd('journalctl -oshort-iso'),
                 JournalctlBinFileCmd('var/log/journal')],
            'ls_lanR_sys_block':
                [BinCmd('ls -lanR /sys/block/'),
                 FileCmd('sos_commands/block/ls_-lanR_.sys.block')],
            'lscpu':
                [BinCmd('lscpu'),
                 FileCmd('sos_commands/processor/lscpu')],
            'lsof_Mnlc':
                [BinCmd('lsof +M -n -l -c ""'),
                 FileCmd('sos_commands/process/lsof_M_-n_-l_-c')],
            'lxd_buginfo':
                [BinCmd('lxd.buginfo'),
                 FileCmd('sos_commands/lxd/lxd.buginfo')],
            'numactl':
                [BinCmd('numactl --hardware'),
                 FileCmd('sos_commands/numa/numactl_--hardware')],
            'ns_ip_addr':
                [BinCmd('ip netns exec {namespace} ip address show'),
                 FileCmd('sos_commands/networking/'
                         'ip_netns_exec_{namespace}_ip_address_show'),
                 FileCmd('sos_commands/networking/namespaces/{namespace}/'
                         'ip_netns_exec_{namespace}_ip_-d_address_show')],
            'ovn_nbctl_show':
                [BinCmd('ovn-nbctl --no-leader-only show'),
                 FileCmd('sos_commands/ovn_central/'
                         'ovn-nbctl_--no-leader-only_show'),
                 # sosreport < 4.5
                 FileCmd('sos_commands/ovn_central/ovn-nbctl_show')],
            'ovn_sbctl_show':
                [BinCmd('ovn-sbctl --no-leader-only show'),
                 FileCmd('sos_commands/ovn_central/'
                         'ovn-sbctl_--no-leader-only_show'),
                 # sosreport < 4.5
                 FileCmd('sos_commands/ovn_central/ovn-sbctl_show')],
            'ovs_vsctl_get':
                [BinCmd('ovs-vsctl get {table} {record} {column}',
                        singleline=True),
                 FileCmd('sos_commands/openvswitch/ovs-vsctl_-t_5_get_'
                         '{table}_{record}_{column}', singleline=True)],
            'ovs_vsctl_list':
                [BinCmd('ovs-vsctl list {table}'),
                 FileCmd('sos_commands/openvswitch/'
                         'ovs-vsctl_-t_5_list_{table}')],
            'ovs_vsctl_list_br':
                [BinCmd('ovs-vsctl list-br'),
                 FileCmd('sos_commands/openvswitch/ovs-vsctl_-t_5_list-br')],
            'ovs_appctl':
                [OVSAppCtlBinCmd('ovs-appctl {command} {flags} {args}'),
                 OVSAppCtlFileCmd('sos_commands/openvswitch/ovs-appctl_'
                                  '{command}{flags}{args}')],
            'ovs_ofctl':
                [OVSOFCtlBinCmd('{command} {args}'),
                 OVSOFCtlFileCmd('sos_commands/openvswitch/'
                                 'ovs-ofctl{ofversion}_{command}_{args}')],
            'pacemaker_crm_status':
                [BinCmd('crm status'),
                 FileCmd('sos_commands/pacemaker/crm_status')],
            'pebble_services':
                [BinCmd('pebble services'),
                 # This is how operator charms run it
                 BinCmd('/charm/bin/pebble services'),
                 # The following does not exist in sosreport yet but adding
                 # since it is useful for testing and will hopefully be
                 # supported in sos at some point.
                 FileCmd('sos_commands/pebble/pebble_services')],
            'ps':
                [BinCmd('ps auxwww'),
                 FileCmd('ps')],
            'ps_axo_flags':
                [BinCmd('ps axo flags,state,uid,pid,ppid,pgid,sid,cls,'
                        'pri,addr,sz,wchan:20,lstart,tty,time,cmd'),
                 # Older sosrepot uses 'wchan' option while newer ones use
                 # 'wchan:20' - thus the glob is to cover both
                 FileCmd(get_ps_axo_flags_available() or "")],
            'pro_status':
                [BinCmd('ua status'),
                 FileCmd('sos_commands/ubuntu/ua_status')],
            'rabbitmqctl_report':
                [BinCmd('rabbitmqctl report'),
                 FileCmd('sos_commands/rabbitmq/rabbitmqctl_report')],
            'snap_list_all':
                [BinCmd('snap list --all'),
                 FileCmd('sos_commands/snap/snap_list_--all'),
                 # sos legacy
                 FileCmd('sos_commands/snappy/snap_list_--all')],
            'sysctl_all':
                [BinCmd('sysctl -a'),
                 FileCmd('sos_commands/kernel/sysctl_-a')],
            'systemctl_status_all':
                [BinCmd('systemctl status --all'),
                 FileCmd('sos_commands/systemd/systemctl_status_--all',
                         decode_error_handling='backslashreplace')],
            'systemctl_list_units':
                [BinCmd('systemctl list-units'),
                 FileCmd('sos_commands/systemd/systemctl_list-units')],
            'systemctl_list_unit_files':
                [BinCmd('systemctl list-unit-files'),
                 FileCmd('sos_commands/systemd/systemctl_list-unit-files')],
            'udevadm_info_dev':
                [BinCmd('udevadm info /dev/{device}'),
                 FileCmd('sos_commands/block/udevadm_info_.dev.{device}')],
            'udevadm_info_exportdb':
                [BinCmd('udevadm info --export-db'),
                 FileCmd('sos_commands/devices/udevadm_info_--export-db')],
            'uname':
                [BinCmd('uname -a', singleline=True),
                 FileCmd('sos_commands/kernel/uname_-a', singleline=True)],
            'uptime':
                [BinCmd('uptime', singleline=True),
                 FileCmd('uptime', singleline=True)],
        }
        return self._command_catalog

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
