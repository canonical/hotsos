import json
import os
import re
import subprocess
from dataclasses import dataclass, field, fields

import yaml
from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers.exceptions import (
    catch_exceptions,
    CLI_COMMON_EXCEPTIONS,
    SourceNotFound,
)
from hotsos.core.log import log


@dataclass(frozen=True)
class CmdOutput():
    """ Representation of the output of a command. """

    # Output value.
    value: str
    # Optional command source path.
    source: str = None


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


@dataclass
class CmdBase:
    """ Base class for all command source types.

    Provides a way to save original state and restore to that state.
    """
    def __post_init__(self):
        self.hooks = {}
        # make a copy of field original values.
        for f in fields(self):
            setattr(self, 'original_' + f.name, f.type(getattr(self, f.name)))

    def get_original_attr_value(self, name):
        return getattr(self, 'original_' + name)

    def reset(self):
        """ Reset fields to original values. """
        for f in fields(self):
            setattr(self, f.name, f.type(getattr(self, 'original_' + f.name)))

    @classmethod
    def safe_readlines(cls, path):
        with open(path, 'r', encoding='utf-8', errors="surrogateescape") as fd:
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


@dataclass
class FileCmdBase(CmdBase):
    """
    State used to execute a file-based command i.e. a command whose output is
    already saved in a file.
    """
    path: str
    json_decode: bool = False
    yaml_decode: bool = False
    singleline: bool = False
    decode_error_handling: str = None

    def __post_init__(self):
        self.path = os.path.join(HotSOSConfig.data_root, self.path)
        super().__post_init__()


@dataclass
class BinCmdBase(CmdBase):
    """ State used to execute a binary command. """
    cmd: str
    json_decode: bool = False
    yaml_decode: bool = False
    singleline: bool = False
    cmd_extras: list = field(default_factory=lambda: [])


class BinCmd(BinCmdBase):
    """ Implements binary command execution. """
    TYPE = "BIN"

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

        _cmd = cmd.split() + self.cmd_extras
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

        if self.yaml_decode:
            return CmdOutput(yaml.safe_load(output))

        if self.singleline:
            return CmdOutput(output.strip())

        return CmdOutput(output.splitlines(keepends=True))


class FileCmd(FileCmdBase):
    """ Implements file-based command execution.

    This is used e.g. with sosreports where the output of a command is saved
    to disk.
    """
    TYPE = "FILE"

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
            with open(self.path, encoding='utf-8') as fd:
                output = json.load(fd)
        elif self.yaml_decode:
            with open(self.path, encoding='utf-8') as fd:
                output = yaml.safe_.load(fd)
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
        # NOTE: we check the original path since by this point the 'path'
        # attribute will have been modified to include a binary and other args
        # required to execute it.
        if not os.path.exists(self.get_original_attr_value('path')):
            raise SourceNotFound(self.get_original_attr_value('path'))

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


class DateFileCmd(FileCmd):
    """ Implementation of file-based date command. """
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
