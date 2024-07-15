import json
import subprocess

from hotsos.core.log import log

CLI_COMMON_EXCEPTIONS = (OSError, subprocess.CalledProcessError,
                         subprocess.TimeoutExpired,
                         json.JSONDecodeError)


class CLIExecError(Exception):
    """ Exception raised when execution of a command files. """
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
    """ Exception raised when a file-based command is not found. """
    def __init__(self, path):
        self.path = path

    def __repr__(self):
        return f"source path '{self.path}' not found"


class CommandNotFound(Exception):
    """ Exception raised when command is not found. """
    def __init__(self, cmd, msg):
        self.msg = f"command '{cmd}' not found in catalog: '{msg}'"

    def __str__(self):
        return self.msg
