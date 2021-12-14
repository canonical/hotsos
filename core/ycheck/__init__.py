import os

import importlib
import operator
import yaml

from core.checks import APTPackageChecksBase
from core import constants
from core.cli_helpers import CLIHelper
from core.log import log
from core.utils import mktemp_dump
from core.ystruct import YAMLDefOverrideBase, YAMLDefSection


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


YOverridesCollection = []


def ydef_override(c):
    YOverridesCollection.append(c)
    return c


class YDefsSection(YAMLDefSection):
    def __init__(self, name, content, extra_overrides=None,
                 checks_handler=None):
        """
        @param name: name of defs group
        @param content: defs tree of type dict
        @param extra_overrides: optional extra overrides
        @param checks_handler: handler object used by some overrides to locate
                               callback methods.
        """
        overrides = [] + YOverridesCollection
        if extra_overrides:
            overrides += extra_overrides

        if checks_handler:
            for c in overrides:
                if hasattr(c, 'EVENT_CHECK_OBJ'):
                    c.EVENT_CHECK_OBJ = checks_handler

        super().__init__(name, content, override_handlers=overrides)


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
            if constants.DEBUG_MODE:
                log.error("failed to get property %s", import_str)

            raise

        return ret

    def get_attribute(self, import_str):
        mod = import_str.rpartition('.')[0]
        attr = import_str.rpartition('.')[2]
        try:
            ret = getattr(importlib.import_module(mod), attr)
        except Exception as exc:
            if constants.DEBUG_MODE:
                log.exception("failed to get module attribute %s", import_str)

            # ystruct.YAMLDefOverrideBase swallows AttributeError so need to
            # convert to something else.
            if type(exc) == AttributeError:
                raise ImportError from exc

            raise

        return ret

    def get_import(self, import_str):
        """
        First attempt to treat import string as a class property then try
        module attribute.
        """
        try:
            return self.get_property(import_str)
        except Exception:
            pass

        return self.get_attribute(import_str)


@ydef_override
class YAMLDefChecks(YAMLDefOverrideBaseX):
    KEYS = ['checks']


@ydef_override
class YAMLDefConclusions(YAMLDefOverrideBaseX):
    KEYS = ['conclusions']


@ydef_override
class YAMLDefPriority(YAMLDefOverrideBaseX):
    KEYS = ['priority']

    def __int__(self):
        return int(self.content)


@ydef_override
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


@ydef_override
class YAMLDefExpr(YAMLDefOverrideBaseX):
    """
    An expression can be a string or a list of strings and can be provided
    as a single value or dict (with keys start, body, end etc) e.g.

    An optional passthrough-results key is provided and used with events type
    defintions to indicate that search results should be passed to
    their handler as a raw core.searchtools.SearchResultsCollection. This is
    typically so that they can be parsed with core.analytics.LogEventStats.
    Defaults to False.

    params:
      expr|hint:
        <str>
      start|body|end:
        expr: <int>
        hint: <int>

    usage:
      If value is a string:
        str(expr|hint)

      If using keys start|body|end:
        <key>.expr
        <key>.hint

    Note that expressions can be a string or list of strings.
    """
    KEYS = ['start', 'body', 'end', 'expr', 'hint', 'passthrough-results']

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


@ydef_override
class YAMLDefRaises(YAMLDefOverrideBaseX):
    KEYS = ['raises']

    @property
    def message(self):
        """ Optional """
        return self.content.get('message')

    @property
    def format_dict(self):
        """
        Optional dict of key/val pairs used to format the message string.
        """
        _format_dict = self.content.get('format-dict')
        if not _format_dict:
            return {}

        return {k: self.get_import(v) for k, v in _format_dict.items()}

    @property
    def format_groups(self):
        """ Optional """
        return self.content.get('search-result-format-groups')

    @property
    def type(self):
        """ Imports and returns class object. """
        return self.get_cls(self.content['type'])


@ydef_override
class YAMLDefSettings(YAMLDefOverrideBaseX):
    KEYS = ['settings']

    def __iter__(self):
        for key, val in self.content.items():
            yield key, val


@ydef_override
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


@ydef_override
class YAMLDefContext(YAMLDefOverrideBaseX):
    KEYS = ['context']

    def __getattr__(self, name):
        name = name.replace('_', '-')
        return self._load()[name]

    def _load(self):
        ctxt = {}
        for key, val in self.content.items():
            ctxt[key] = self.get_import(val)

        return ctxt


@ydef_override
class YAMLDefRequires(YAMLDefOverrideBaseX):
    KEYS = ['requires']

    @property
    def apt(self):
        return self.content.get('apt', None)

    @property
    def _property(self):
        return self.content.get('property', None)

    @property
    def value(self):
        """
        An optional value to match against. If no value is provided this will
        return True by default.
        """
        return self.content.get('value', True)

    @property
    def op(self):
        """ Operator used for value comparison. Default is eq. """
        return getattr(operator, self.content.get('op', 'eq'))

    def _passes(self, apt, property, value):
        """ Assert whether the requirement is met.

        Returns True if met otherwise False.
        """
        if apt:
            pkg = apt
            result = APTPackageChecksBase(core_pkgs=[pkg]).is_installed(pkg)
            log.debug('requirement check: apt %s (result=%s)', pkg, result)
            return result
        elif property:
            result = self.op(self.get_property(property), value)
            log.debug('requirement check: property %s %s %s (result=%s)',
                      property, self.op.__name__, value, result)
            return result

        log.debug('unknown requirement check')
        return False

    def _has_groups(self):
        if set(self.content.keys()).intersection(['and', 'or']):
            return True

        return False

    def _is_valid_requirement(self, entry):
        apt = entry.get('apt')
        property = entry.get('property')
        if not any([apt, property]):
            return False

        return True

    @property
    def passes(self):
        """
        Content can either be a single requirement or a list of requirements.

        Returns True if any requirement is met.
        """
        if not self._has_groups():
            log.debug("single requirement provided")
            if self._is_valid_requirement(self.content):
                return self._passes(self.apt, self._property, self.value)
            else:
                log.debug("invalid requirement: %s - fail", self.content)
                return False
        else:
            log.debug("requirements provided as groups")
            results = {}
            # list of requirements
            for op, requirements in self.content.items():
                if op not in results:
                    results[op] = []

                log.debug("op=%s has %s requirement(s)", op, len(requirements))
                for entry in requirements:
                    if not self._is_valid_requirement(entry):
                        log.debug("invalid requirement: %s - fail", entry)
                        _result = False
                    else:
                        _result = self._passes(entry.get('apt'),
                                               entry.get('property'),
                                               entry.get('value', True))

                    results[op].append(_result)
                if op == 'or' and any(results[op]):
                    return True
                elif op == 'and' and not all(results[op]):
                    return False

            # Now AND all groups for the final result
            final_results = []
            for op in results:
                if op == 'and':
                    final_results.append(all(results[op]))
                else:
                    final_results.append(any(results[op]))

            return all(final_results)


@ydef_override
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
    def __init__(self, ytype):
        self.ytype = ytype

    def _is_def(self, path):
        return path.endswith('.yaml')

    def _get_yname(self, path):
        return os.path.basename(path).partition('.yaml')[0]

    def _get_defs_recursive(self, path):
        """ Recursively find all yaml/files beneath a directory. """
        defs = {}
        for entry in os.listdir(path):
            _path = os.path.join(path, entry)
            if os.path.isdir(_path):
                defs[os.path.basename(_path)] = self._get_defs_recursive(_path)
            else:
                if not self._is_def(entry):
                    continue

                if self._get_yname(_path) == os.path.basename(path):
                    with open(_path) as fd:
                        defs.update(yaml.safe_load(fd.read()) or {})

                    continue

                with open(_path) as fd:
                    _content = yaml.safe_load(fd.read()) or {}
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
