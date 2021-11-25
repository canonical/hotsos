import os

import importlib
import operator

from core.checks import APTPackageChecksBase
from core import constants
from core.cli_helpers import CLIHelper
from core.log import log
from core.utils import mktemp_dump
from core.ystruct import YAMLDefOverrideBase


class CallbackHelper(object):

    def __init__(self):
        self.callbacks = {}

    def callback(self, f):
        def callback_inner(*args, **kwargs):
            return f(*args, **kwargs)

        self.callbacks[f.__name__] = callback_inner
        # we don't need to return but we leave it so that we can unit test
        # these methods.
        return callback_inner


class YAMLDefExpr(YAMLDefOverrideBase):
    KEYS = ['start', 'body', 'end', 'expr', 'hint']

    @property
    def expr(self):
        """
        Subkey e.g for start.expr, body.expr. Expression defs that are just
        a string or use subkey 'expr' will rely on __getattr__.
        """
        return self.content.get('expr', self.content)

    @property
    def hint(self):
        return self.content.get('hint', None)

    def __getattr__(self, name):
        """
        An expression can be provided in multiple ways. The simplest form is
        where the value of the event is a pattern string hence why we override
        this to just return the content if it is not a dict.
        """
        if type(self.content) == dict:
            return super().__getattr__(name)
        else:
            return self.content


class YAMLDefMessage(YAMLDefOverrideBase):
    KEYS = ['message', 'message-format-result-groups']

    @property
    def format_groups(self):
        return self.content

    def __str__(self):
        return self.content


class YAMLDefSettings(YAMLDefOverrideBase):
    KEYS = ['settings']

    def __iter__(self):
        for key, val in self.content.items():
            yield key, val


class YAMLDefReleases(YAMLDefOverrideBase):
    KEYS = ['releases']

    def __iter__(self):
        for key, val in self.content.items():
            yield key, val


class YAMLDefResultsPassthrough(YAMLDefOverrideBase):
    KEYS = ['passthrough-results']

    def __bool__(self):
        """ If returns True, the master results list is passed to callbacks
        so that they may fetch results in their own way. This is required e.g.
        when processing results with analytics.LogEventStats.
        """
        return bool(self.content)


class YAMLDefInput(YAMLDefOverrideBase):
    KEYS = ['input']
    TYPE_COMMAND = 'command'
    TYPE_FILESYSTEM = 'filesystem'

    # NOTE: this must be set by the handler object that is using the overrides.
    #       we need a better way to do this but we can't use __init__ because
    #       this class must be provided uninstantiated.
    EVENT_CHECK_OBJ = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._path = None

    @property
    def meta(self):
        defaults = {'allow-all-logs': True,
                    'args': [],
                    'kwargs': {},
                    'args-callback': None}
        _meta = self.content.get('meta', defaults)
        defaults.update(_meta)
        return defaults

    @property
    def path(self):
        if self.type == self.TYPE_FILESYSTEM:
            path = os.path.join(constants.DATA_ROOT, self.value)
            if constants.USE_ALL_LOGS and self.meta['allow-all-logs']:
                path = "{}*".format(path)

            return path
        elif self.type == self.TYPE_COMMAND:
            if self._path:
                return self._path

            args_callback = self.meta['args-callback']
            if args_callback:
                args, kwargs = getattr(self.EVENT_CHECK_OBJ, args_callback)()
            else:
                args = self.meta['args']
                kwargs = self.meta['kwargs']

            # get command output
            out = getattr(CLIHelper(), self.value)(*args,
                                                   **kwargs)
            # store in temp file to make it searchable
            # NOTE: we dont need to delete this at the the end since they are
            # created in the plugun tmp dir which is wiped at the end of the
            # plugin run.
            self._path = mktemp_dump(''.join(out))
            return self._path


class YAMLDefContext(YAMLDefOverrideBase):
    KEYS = ['context']

    def __getattr__(self, name):
        name = name.replace('_', '-')
        return self._load()[name]

    def _load(self):
        ctxt = {}
        for key, val in self.content.items():
            mod = val.rpartition('.')[0]
            property = val.rpartition('.')[2]
            class_name = mod.rpartition('.')[2]
            mod = mod.rpartition('.')[0]
            cls = getattr(importlib.import_module(mod), class_name)
            ctxt[key] = getattr(cls(), property)

        return ctxt


class YAMLDefRequires(YAMLDefOverrideBase):
    KEYS = ['requires']

    @property
    def passes(self):
        if self.type == 'apt':
            pkg = self.value
            result = APTPackageChecksBase(core_pkgs=[pkg]).is_installed(pkg)
            log.debug('config_check requirement:apt %s (result=%s)', pkg,
                      result)
            return result
        elif self.type == 'property':
            mod = self.source.rpartition('.')[0]
            property = self.source.rpartition('.')[2]
            class_name = mod.rpartition('.')[2]
            mod = mod.rpartition('.')[0]
            cls = getattr(importlib.import_module(mod), class_name)
            result = getattr(cls(), property) is self.value
            log.debug('config_check requirement:property %s is %s (result=%s)',
                      self.source, self.value, result)
            return result
        else:
            self.debug("unsupported yaml requires type=%s", self.type)

        return False


class YAMLDefIssueType(YAMLDefOverrideBase):
    KEYS = ['raises']

    @property
    def issue(self):
        mod = self.content.rpartition('.')[0]
        class_name = self.content.rpartition('.')[2]
        return getattr(importlib.import_module(mod), class_name)


class YAMLDefConfig(YAMLDefOverrideBase):
    KEYS = ['config']

    def actual(self, key, section=None):
        mod = self.handler.rpartition('.')[0]
        cls = self.handler.rpartition('.')[2]
        obj = getattr(importlib.import_module(mod), cls)
        if hasattr(self, 'path'):
            self.cfg = obj(self.path)
        else:
            self.cfg = obj()

        if section:
            actual = self.cfg.get(key, section=section)
        else:
            actual = self.cfg.get(key)

        return actual

    def check(self, actual, value, op, allow_unset=False):
        if value is not None and actual is None:
            if allow_unset:
                return True
            else:
                return False

        # Apply the type from the yaml to that of the config
        if value is not None and type(value) != type(actual):
            actual = type(value)(actual)

        if getattr(operator, op)(actual, value):
            return True

        return False


class ChecksBase(object):

    def __init__(self, *args, yaml_defs_group=None, searchobj=None, **kwargs):
        """
        @param _yaml_defs_group: optional key used to identify our yaml
                                 definitions if indeed we have any. This is
                                 given meaning by the implementing class.
        @param searchobj: optional FileSearcher object used for searches. If
                          multiple implementations of this class are used in
                          the same part it is recommended to provide a search
                          object that is shared across them to provide
                          concurrent execution.

        """
        super().__init__(*args, **kwargs)
        self.searchobj = searchobj
        self._yaml_defs_group = yaml_defs_group

    def load(self):
        raise NotImplementedError

    def run(self, results=None):
        raise NotImplementedError

    def run_checks(self):
        self.load()
        if self.searchobj:
            ret = self.run(self.searchobj.search())
        else:
            ret = self.run()

        return ret


class AutoChecksBase(ChecksBase):

    def __call__(self):
        return self.run_checks()


class ManualChecksBase(ChecksBase):

    def __call__(self):
        return self.run_checks()
