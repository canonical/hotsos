import os

import importlib
import operator
import yaml

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


class YAMLDefOverrideBaseX(YAMLDefOverrideBase):

    def get_cls(self, import_str):
        mod = import_str.rpartition('.')[0]
        class_name = import_str.rpartition('.')[2]
        return getattr(importlib.import_module(mod), class_name)

    def get_property(self, import_str):
        mod = import_str.rpartition('.')[0]
        property = import_str.rpartition('.')[2]
        class_name = mod.rpartition('.')[2]
        mod = mod.rpartition('.')[0]
        cls = getattr(importlib.import_module(mod), class_name)
        try:
            ret = getattr(cls(), property)
        except Exception:
            log.debug("failed to get property %s", import_str)
            raise

        return ret


class YAMLDefChecks(YAMLDefOverrideBaseX):
    KEYS = ['checks']


class YAMLDefConclusions(YAMLDefOverrideBaseX):
    KEYS = ['conclusions']


class YAMLDefPriority(YAMLDefOverrideBaseX):
    KEYS = ['priority']

    def __int__(self):
        return int(self.content)


class YAMLDefDecision(YAMLDefOverrideBaseX):
    KEYS = ['decision']

    @property
    def is_singleton(self):
        """
        A decision can be based off a single check or combinations of checks.
        If the value is a string and not a dict then it is assumed to be a
        single check with no boolean logic applied.
        """
        return type(self.content) is str

    def __iter__(self):
        for _bool, val in self.content.items():
            yield _bool, val


class YAMLDefExpr(YAMLDefOverrideBaseX):
    """
    An expression can be a string or a list of strings and can be provided
    as a single value or dict (with keys start, body, end etc) e.g.

    expr: 'myexpr'

    or

    expr:
      - 'myexpr1'
      - 'myexpr2'

    or

    start: 'myexpr1'
    end: 'myexpr2'

    or

    start:
        expr: 'myexpr1'
        hint: 'my'
    end: 'myexpr2'
    """
    KEYS = ['start', 'body', 'end', 'expr', 'hint']

    @property
    def expr(self):
        """
        Subkey e.g for start.expr, body.expr. Expression defs that are just
        a string or use subkey 'expr' will rely on __getattr__.
        """
        return self.content.get('expr', self.content)

    def __getattr__(self, name):
        """
        This is a fallback for when the value is not a key and we just want
        to return the contents e.g. a string or list.

        If the value is a string or list you can use a non-existant key e.g.
        'value' to retreive it.
        """
        if type(self.content) == dict:
            return super().__getattr__(name)
        else:
            return self.content


class YAMLDefIssue(YAMLDefOverrideBaseX):
    KEYS = ['issue']

    @property
    def format_dict(self):
        _format_dict = self.content.get('format-dict')
        if not _format_dict:
            return {}

        return {k: self.get_property(v) for k, v in _format_dict.items()}

    @property
    def type(self):
        """ Imports and returns class object. """
        return self.get_cls(self.content['type'])


class YAMLDefMessage(YAMLDefOverrideBaseX):
    KEYS = ['message', 'message-format-result-groups']

    @property
    def format_groups(self):
        return self.content

    def __str__(self):
        return self.content


class YAMLDefSettings(YAMLDefOverrideBaseX):
    KEYS = ['settings']

    def __iter__(self):
        for key, val in self.content.items():
            yield key, val


class YAMLDefReleases(YAMLDefOverrideBaseX):
    KEYS = ['releases']

    def __iter__(self):
        for key, val in self.content.items():
            yield key, val


class YAMLDefResultsPassthrough(YAMLDefOverrideBaseX):
    KEYS = ['passthrough-results']

    def __bool__(self):
        """ If returns True, the master results list is passed to callbacks
        so that they may fetch results in their own way. This is required e.g.
        when processing results with analytics.LogEventStats.
        """
        return bool(self.content)


class YAMLDefInput(YAMLDefOverrideBaseX):
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


class YAMLDefContext(YAMLDefOverrideBaseX):
    KEYS = ['context']

    def __getattr__(self, name):
        name = name.replace('_', '-')
        return self._load()[name]

    def _load(self):
        ctxt = {}
        for key, val in self.content.items():
            ctxt[key] = self.get_property(val)

        return ctxt


class YAMLDefRequires(YAMLDefOverrideBaseX):
    KEYS = ['requires']

    @property
    def value(self):
        """
        An optional value to match against. If no value is provided this will
        return True by default.
        """
        return self.content.get('value', True)

    @property
    def passes(self):
        """ Assert whether the requirement is met.

        Returns True if met otherwise False.
        """
        if self.type == 'apt':
            pkg = self.value
            result = APTPackageChecksBase(core_pkgs=[pkg]).is_installed(pkg)
            log.debug('requirement check: apt %s (result=%s)', pkg,
                      result)
            return result
        elif self.type == 'property':
            result = self.get_property(self.source) == self.value
            log.debug('requirement check: property %s is %s (result=%s)',
                      self.source, self.value, result)
            return result
        else:
            self.debug("unsupported yaml requires type=%s", self.type)

        return False


class YAMLDefIssueType(YAMLDefOverrideBaseX):
    KEYS = ['raises']

    @property
    def issue(self):
        return self.get_cls(self.content)


class YAMLDefConfig(YAMLDefOverrideBaseX):
    KEYS = ['config']

    def actual(self, key, section=None):
        obj = self.get_cls(self.handler)
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


class YDefsLoader(object):
    DEFS_SPECIAL_OVERLAY_NAMES = ['all']

    def __init__(self, ytype):
        self.ytype = ytype

    def _is_def(self, path):
        return path.endswith('.yaml')

    def _get_yname(self, path):
        return os.path.basename(path).partition('.yaml')[0]

    def _get_defs_recursive(self, path):
        """ Recursively find all yaml/files beneath a directory. """
        overlays = {}
        for entry in os.listdir(path):
            _path = os.path.join(path, entry)
            if os.path.isdir(_path) or not self._is_def(entry):
                continue

            if self._get_yname(_path) in self.DEFS_SPECIAL_OVERLAY_NAMES:
                with open(_path) as fd:
                    overlays.update(yaml.safe_load(fd.read()) or {})

        defs = {}
        for entry in os.listdir(path):
            _path = os.path.join(path, entry)
            if os.path.isdir(_path):
                defs[os.path.basename(_path)] = self._get_defs_recursive(_path)
            else:
                if (not self._is_def(entry) or
                        self._get_yname(_path) in
                        self.DEFS_SPECIAL_OVERLAY_NAMES):
                    continue

                with open(_path) as fd:
                    _content = yaml.safe_load(fd.read()) or {}
                    _content.update(overlays)
                    defs[self._get_yname(_path)] = _content

        return defs

    @property
    def plugin_defs(self):
        path = os.path.join(constants.PLUGIN_YAML_DEFS, self.ytype,
                            constants.PLUGIN_NAME)
        if os.path.isdir(path):
            return self._get_defs_recursive(path)

    @property
    def plugin_defs_legacy(self):
        path = os.path.join(constants.PLUGIN_YAML_DEFS,
                            '{}.yaml'.format(self.ytype))
        if not os.path.exists(path):
            return {}

        log.debug("using legacy defs path %s", path)
        with open(path) as fd:
            defs = yaml.safe_load(fd.read()) or {}

        return defs.get(constants.PLUGIN_NAME, {})

    def load_plugin_defs(self):
        log.debug('loading %s definitions for plugin=%s', self.ytype,
                  constants.PLUGIN_NAME,)

        yaml_defs = self.plugin_defs
        if not yaml_defs:
            yaml_defs = self.plugin_defs_legacy

        return yaml_defs


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
