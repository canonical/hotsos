import os

import importlib
import operator
import yaml

from core.checks import (
    APTPackageChecksBase,
    DPKGVersionCompare,
    ServiceChecksBase,
    SnapPackageChecksBase,
)
from core import constants
from core.cli_helpers import CLIHelper
from core.log import log
from core.utils import mktemp_dump
from core.ystruct import YAMLDefOverrideBase, YAMLDefSection


class CallbackHelper(object):

    def __init__(self):
        self.callbacks = {}

    def callback(self, *event_names):
        def callback_inner(f):
            def callback_inner2(*args, **kwargs):
                return f(*args, **kwargs)

            if event_names:
                for name in event_names:
                    # convert event name to valid method name
                    name = name.replace('-', '_')
                    self.callbacks[name] = callback_inner2
            else:
                self.callbacks[f.__name__] = callback_inner2

            return callback_inner2

        # we don't need to return but we leave it so that we can unit test
        # these methods.
        return callback_inner


YOverridesCollection = []


def ydef_override(c):
    YOverridesCollection.append(c)
    return c


class YDefsSection(YAMLDefSection):
    def __init__(self, name, content, extra_overrides=None):
        """
        @param name: name of defs group
        @param content: defs tree of type dict
        @param extra_overrides: optional extra overrides
        """
        overrides = [] + YOverridesCollection
        if extra_overrides:
            overrides += extra_overrides

        super().__init__(name, content, override_handlers=overrides)


class YPropertyOverrideBase(YAMLDefOverrideBase):

    def get_cls(self, import_str):
        log.debug("instantiating class %s", import_str)
        mod = import_str.rpartition('.')[0]
        class_name = import_str.rpartition('.')[2]
        return getattr(importlib.import_module(mod), class_name)

    def get_property(self, import_str):
        log.debug("calling property %s", import_str)
        mod = import_str.rpartition('.')[0]
        property = import_str.rpartition('.')[2]
        class_name = mod.rpartition('.')[2]
        mod = mod.rpartition('.')[0]
        cls = getattr(importlib.import_module(mod), class_name)
        try:
            ret = getattr(cls(), property)
        except Exception:
            if constants.DEBUG_MODE:
                log.exception("failed to import and call property %s",
                              import_str)

            raise

        return ret

    def get_method(self, import_str):
        log.debug("calling method %s", import_str)
        mod = import_str.rpartition('.')[0]
        property = import_str.rpartition('.')[2]
        class_name = mod.rpartition('.')[2]
        mod = mod.rpartition('.')[0]
        cls = getattr(importlib.import_module(mod), class_name)
        try:
            ret = getattr(cls(), property)()
        except Exception:
            if constants.DEBUG_MODE:
                log.exception("failed to import and call method %s",
                              import_str)

            raise

        return ret

    def get_attribute(self, import_str):
        log.debug("fetching attribute %s", import_str)
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
class YPropertyChecks(YPropertyOverrideBase):
    KEYS = ['checks']


@ydef_override
class YPropertyConclusions(YPropertyOverrideBase):
    KEYS = ['conclusions']


@ydef_override
class YPropertyPriority(YPropertyOverrideBase):
    KEYS = ['priority']

    def __int__(self):
        return int(self.content)


@ydef_override
class YPropertyDecision(YPropertyOverrideBase):
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
class YPropertyExpr(YPropertyOverrideBase):
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
class YPropertyRaises(YPropertyOverrideBase):
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
class YPropertySettings(YPropertyOverrideBase):
    KEYS = ['settings']

    def __iter__(self):
        for key, val in self.content.items():
            yield key, val


@ydef_override
class YPropertyInput(YPropertyOverrideBase):
    KEYS = ['input']
    TYPE_COMMAND = 'command'
    TYPE_FILESYSTEM = 'filesystem'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cmd_tmp_path = None

    @property
    def options(self):
        defaults = {'allow-all-logs': True,
                    'args': [],
                    'kwargs': {},
                    'args-callback': None}
        _options = self.content.get('options', defaults)
        defaults.update(_options)
        return defaults

    @property
    def command(self):
        return self.content.get('command')

    @property
    def fs_path(self):
        return self.content.get('path')

    @property
    def path(self):
        if self.fs_path:
            path = os.path.join(constants.DATA_ROOT, self.fs_path)
            if constants.USE_ALL_LOGS and self.options['allow-all-logs']:
                path = "{}*".format(path)

            return path
        elif self.command:
            if self.cmd_tmp_path:
                return self.cmd_tmp_path

            args_callback = self.options['args-callback']
            if args_callback:
                args, kwargs = self.get_method(args_callback)
            else:
                args = self.options['args']
                kwargs = self.options['kwargs']

            # get command output
            out = getattr(CLIHelper(), self.command)(*args,
                                                     **kwargs)
            # store in temp file to make it searchable
            # NOTE: we dont need to delete this at the the end since they are
            # created in the plugun tmp dir which is wiped at the end of the
            # plugin run.
            if type(out) == list:
                out = ''.join(out)
            elif type(out) == dict:
                out = str(out)

            self.cmd_tmp_path = mktemp_dump(out)
            return self.cmd_tmp_path
        else:
            log.debug("no input provided")


class YRequirementObj(YPropertyOverrideBase):
    def __init__(self, apt, snap, systemd, property, value, py_op):
        self.apt = apt
        self.snap = snap
        self.systemd = systemd
        self.property = property
        self.value = value
        self.py_op = getattr(operator, py_op or 'eq')
        self._cache = {}

    @property
    def cache(self):
        return self._cache

    @property
    def is_valid(self):
        # need at least one
        return any([self.systemd, self.snap, self.apt, self.property])

    def _package_version_within_ranges(self, pkg_version, versions):
        for item in sorted(versions, key=lambda i: i['max'],
                           reverse=True):
            v_max = str(item['max'])
            v_min = str(item['min'])
            lte_max = pkg_version <= DPKGVersionCompare(v_max)
            if v_min:
                lt_broken = pkg_version < DPKGVersionCompare(v_min)
            else:
                lt_broken = None

            if lt_broken:
                continue

            if lte_max:
                return True
            else:
                return False

        return False

    @property
    def passes(self):
        """ Assert whether the requirement is met.

        Returns True if met otherwise False.
        """
        if self.apt:
            versions = []
            # Value can be a package name or dict that provides more
            # information about the package.
            if type(self.apt) == dict:
                # NOTE: we only support one package for now but done this way
                # to make extensible.
                for _name, _versions in self.apt.items():
                    self._cache['apt.pkg'] = _name
                    pkg = _name
                    versions = _versions
            else:
                pkg = self.apt

            apt_info = APTPackageChecksBase([pkg])
            result = apt_info.is_installed(pkg)
            if result:
                if versions:
                    pkg_ver = apt_info.get_version(pkg)
                    self._cache['apt.pkg_version'] = pkg_ver
                    result = self._package_version_within_ranges(pkg_ver,
                                                                 versions)
                    log.debug("package %s=%s within version ranges %s "
                              "(result=%s)", pkg, pkg_ver, versions, result)

            log.debug('requirement check: apt %s (result=%s)', pkg, result)
            return result
        elif self.snap:
            pkg = self.snap
            result = pkg in SnapPackageChecksBase(core_snaps=[pkg]).all
            log.debug('requirement check: snap %s (result=%s)', pkg, result)
            return result
        elif self.systemd:
            service = self.systemd
            svcs = ServiceChecksBase([service]).services
            result = service in svcs
            if result and self.value is not None:
                result = self.py_op(svcs[service], self.value)

            log.debug('requirement check: systemd %s (result=%s)', service,
                      result)
            return result
        elif self.property:
            result = self.py_op(self.get_property(self.property), self.value)
            log.debug('requirement check: property %s %s %s (result=%s)',
                      self.property, self.py_op, self.value, result)
            return result

        log.debug('unknown requirement check')
        return False


@ydef_override
class YPropertyRequires(YPropertyOverrideBase):
    KEYS = ['requires']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache = {}

    @property
    def cache(self):
        return self._cache

    @property
    def apt(self):
        return self.content.get('apt', None)

    @property
    def snap(self):
        return self.content.get('snap', None)

    @property
    def systemd(self):
        return self.content.get('systemd', None)

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

    def _has_groups(self):
        if set(self.content.keys()).intersection(['and', 'or', 'not']):
            return True

        return False

    @property
    def passes(self):
        """
        Content can either be a single requirement or a list of requirements.

        Returns True if any requirement is met.
        """
        if not self._has_groups():
            log.debug("single requirement provided")
            requirement = YRequirementObj(self.apt, self.snap,
                                          self.systemd,
                                          self._property,
                                          self.value,
                                          self.content.get('op'))
            if requirement.is_valid:
                # NOTE: only currently support caching for single requirement
                result = requirement.passes
                self._cache = requirement.cache
                return result
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
                    requirement = YRequirementObj(entry.get('apt'),
                                                  entry.get('snap'),
                                                  entry.get('systemd'),
                                                  entry.get('property'),
                                                  entry.get('value', True),
                                                  entry.get('op'))
                    if requirement.is_valid:
                        results[op].append(requirement.passes)
                    else:
                        log.debug("invalid requirement: %s - fail", entry)
                        results[op].append(False)

            # Now apply op to respective groups then AND all for the final
            # result.
            final_results = []
            for op in results:
                if op == 'and':
                    final_results.append(all(results[op]))
                elif op == 'or':
                    final_results.append(any(results[op]))
                elif op == 'not':
                    # this is a NOR
                    final_results.append(not any(results[op]))
                else:
                    log.debug("unknown operator '%s' found in requirement", op)

            result = all(final_results)
            log.debug("requirement group result=%s", result)
            return result


@ydef_override
class YPropertyConfig(YPropertyOverrideBase):
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
