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


class YPropertyBase(object):

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


class YPropertyOverrideBase(YAMLDefOverrideBase, YPropertyBase):
    pass


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


class YRequirementObj(YPropertyBase):
    def __init__(self, apt, snap, systemd, property, config, value, py_op):
        self.apt = apt
        self.snap = snap
        self.systemd = systemd
        self.property = property
        self.config = config
        self.value = value
        self.py_op = getattr(operator, py_op)
        self._cache = {}

    @property
    def cache(self):
        return self._cache

    @property
    def is_valid(self):
        # need at least one
        return any([self.systemd, self.snap, self.apt, self.property,
                    self.config])

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

    def _apt_handler(self):
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
            self._cache['apt.pkg'] = pkg

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

    def _snap_handler(self):
        pkg = self.snap
        result = pkg in SnapPackageChecksBase(core_snaps=[pkg]).all
        log.debug('requirement check: snap %s (result=%s)', pkg, result)
        self._cache['snap.pkg'] = pkg
        return result

    def _systemd_handler(self):
        service = self.systemd
        svcs = ServiceChecksBase([service]).services
        result = service in svcs
        if result and self.value is not None:
            result = self.py_op(svcs[service], self.value)

        log.debug('requirement check: systemd %s (result=%s)', service,
                  result)
        self._cache['systemd.service'] = service
        self._cache['systemd.state'] = self.value
        self._cache['systemd.op'] = self.py_op
        return result

    def _property_handler(self):
        actual = self.get_property(self.property)
        result = self.py_op(actual, self.value)
        log.debug('requirement check: property %s %s %s (result=%s)',
                  self.property, self.py_op, self.value, result)
        self._cache['property.actual'] = actual
        self._cache['property.value'] = self.value
        self._cache['property.op'] = self.py_op
        return result

    def _config_handler(self):
        handler = self.config['handler']
        obj = self.get_cls(handler)
        path = self.config.get('path')
        if path:
            path = os.path.join(constants.DATA_ROOT, path)
            cfg = obj(path)
        else:
            cfg = obj()

        for key, assertion in self.config['assertions'].items():
            value = assertion.get('value')
            op = assertion.get('op', 'eq')
            section = assertion.get('section')
            if section:
                actual = cfg.get(key, section=section)
            else:
                actual = cfg.get(key)

            log.debug("requirement check: config %s %s %s (actual=%s)", key,
                      op, value, actual)
            result = False
            if value is not None:
                if actual is None:
                    result = assertion.get('allow-unset', False)
                else:
                    if type(value) != type(actual):
                        # Apply the type from the yaml to that of the
                        # config.
                        actual = type(value)(actual)

                    result = getattr(operator, op)(actual, value)
            elif actual is None:
                result = True

            # return on first fail
            if not result:
                self._cache['config.key'] = key
                self._cache['config.value'] = value
                self._cache['config.op'] = op
                self._cache['config.actual'] = actual
                return False

        return True

    @property
    def passes(self):
        """ Assert whether the requirement is met.

        Returns True if met otherwise False.
        """
        try:
            if self.apt:
                return self._apt_handler()
            elif self.snap:
                return self._snap_handler()
            elif self.systemd:
                return self._systemd_handler()
            elif self.property:
                return self._property_handler()
            elif self.config:
                return self._config_handler()
        except Exception:
            if constants.DEBUG_MODE:
                # display traceback here before it gets swallowed up.
                log.exception("requires.passes raised the following")

            raise

        log.debug('unknown requirement check - passes=False')
        return False


@ydef_override
class YPropertyRequires(YPropertyOverrideBase):
    KEYS = ['requires']
    # these must be logical operators
    VALID_GROUP_KEYS = ['and', 'or', 'not']
    FINAL_RESULT_OP = 'and'
    DEFAULT_STD_OP = 'eq'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache = {}

    @property
    def cache(self):
        return self._cache

    @property
    def depends_on(self):
        if not type(self.content) == dict:
            return

        return self.content.get('depends-on', None)

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
    def config(self):
        return self.content.get('config', None)

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
        return self.content.get('op', self.DEFAULT_STD_OP)

    def process_requirement(self, requirement, cache=False):
        """ Process a single requirement and return its boolean result.

        @param requirement: a YRequirementObj object.
        @param cache: if set to True the cached info from the requirement will
        be saved locally. This can only be done for a single requirement.
        """
        if requirement.is_valid:
            result = requirement.passes
            if cache:
                # NOTE: only currently support caching for single requirement
                self._cache = requirement.cache

            return result

        log.debug("invalid requirement: %s - fail", self.content)
        return False

    def _is_groups(self, item):
        """ Return True if the dictionary item contains groups keys.

        Note that the dictionary must *only* contain group keys.
        """
        if set(list(item.keys())).intersection(self.VALID_GROUP_KEYS):
            return True

        return False

    def process_requirement_group(self, item):
        """
        Process a requirements group (dict) which can contain one or more
        groups each named by the boolean operator to apply to the results of
        the list of requirements that it contains.

        @param item: dict of YRequirementObj objects keyed by bool opt.
        """
        results = {}
        for group_op, group_items in item.items():
            if group_op not in results:
                results[group_op] = []

            log.debug("op=%s has %s requirement(s)", group_op,
                      len(group_items))
            for entry in group_items:
                r_op = entry.get('op', self.DEFAULT_STD_OP)
                requirement = YRequirementObj(entry.get('apt'),
                                              entry.get('snap'),
                                              entry.get('systemd'),
                                              entry.get('property'),
                                              entry.get('config'),
                                              entry.get('value', True), r_op)
                result = self.process_requirement(requirement)
                if group_op not in results:
                    results[group_op] = []

                results[group_op].append(result)

        return results

    def process_multi_requirements_list(self, items):
        """
        If requirements are provided as a list, each item can be a requirement
        or a group of requirements.

        @param item: list of YRequirementObj objects or groups of objects.
        """
        log.debug("requirements provided as groups")
        results = {}
        for item in items:
            if self._is_groups(item):
                group_results = self.process_requirement_group(item)
                for group_op, grp_op_results in group_results.items():
                    if group_op not in results:
                        results[group_op] = []

                    results[group_op] += grp_op_results
            else:
                r_op = item.get('op', self.DEFAULT_STD_OP)
                requirement = YRequirementObj(item.get('apt'),
                                              item.get('snap'),
                                              item.get('systemd'),
                                              item.get('property'),
                                              item.get('config'),
                                              item.get('value', True),
                                              item.get('op', r_op))
                result = self.process_requirement(requirement)
                # final results always get anded.
                op = self.FINAL_RESULT_OP
                if op not in results:
                    results[op] = []

                results[op].append(result)

        return results

    def finalise_result(self, results):
        """
        Apply group ops to respective groups then AND all for the final result.
        """
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
        log.debug("final result=%s", result)
        return result

    @property
    def passes(self):
        """
        Content can either be a single requirement, dict of requirement groups
        or list of requirements. List may contain individual requirements or
        groups.
        """
        if self.depends_on:
            log.debug("depends-on provided")
            entry = self.depends_on
            requirement = YRequirementObj(entry.get('apt'),
                                          entry.get('snap'),
                                          entry.get('systemd'),
                                          entry.get('property'),
                                          entry.get('config'),
                                          entry.get('value', True),
                                          entry.get('op', self.DEFAULT_STD_OP))
            if not self.process_requirement(requirement):
                log.debug("depends-on is False - skipping requirenent check "
                          "and returning passes=True")
                return True

            log.debug("depends-on passed - continuing")
            del self.content['depends-on']

        if type(self.content) == dict:
            if not self._is_groups(self.content):
                log.debug("single requirement provided")
                requirement = YRequirementObj(self.apt, self.snap,
                                              self.systemd, self._property,
                                              self.config, self.value,
                                              self.op)
                results = {self.FINAL_RESULT_OP:
                           [self.process_requirement(requirement, cache=True)]}
            else:
                log.debug("requirement groups provided")
                results = self.process_requirement_group(self.content)

        elif type(self.content) == list:
            log.debug("list of requirements provided")
            results = self.process_multi_requirements_list(self.content)

        return self.finalise_result(results)


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
        self.__final_checks_results = None

    def load(self):
        raise NotImplementedError

    def run(self, results=None):
        raise NotImplementedError

    def run_checks(self):
        if self.__final_checks_results:
            return self.__final_checks_results

        self.load()
        if self.searchobj:
            ret = self.run(self.searchobj.search())
        else:
            ret = self.run()

        self.__final_checks_results = ret
        return ret

    def __call__(self):
        return self.run_checks()
