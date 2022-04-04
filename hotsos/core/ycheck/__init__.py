import builtins
import os

import abc
import importlib
import operator
import yaml

from datetime import (
    datetime,
    timedelta,
)

from hotsos.core.searchtools import (
    FileSearcher,
    SearchDef,
)
from hotsos.core.checks import (
    APTPackageChecksBase,
    DPKGVersionCompare,
    ServiceChecksBase,
    SnapPackageChecksBase,
)
from hotsos.core.config import HotSOSConfig
from hotsos.core.cli_helpers import CLIHelper
from hotsos.core.log import log
from hotsos.core.utils import mktemp_dump
from hotsos.core.ystruct import YAMLDefOverrideBase, YAMLDefSection


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


YPropertiesCatalog = []


def add_to_property_catalog(c):
    """
    Add property implementation to the global catalog.
    """
    YPropertiesCatalog.append(c)


class YDefsSection(YAMLDefSection):
    def __init__(self, name, content, extra_overrides=None):
        """
        @param name: name of defs group
        @param content: defs tree of type dict
        @param extra_overrides: optional extra overrides
        """
        overrides = [] + YPropertiesCatalog
        if extra_overrides:
            overrides += extra_overrides

        super().__init__(name, content, override_handlers=overrides)


class PropertyCacheRefResolver(object):
    """
    This class is used to resolve string references to property cache entries.
    """
    def __init__(self, refstr, property=None, checks=None):
        self.refstr = refstr
        if not self.is_valid_cache_ref(refstr):
            msg = ("{} is not a valid property cache reference".format(refstr))
            raise Exception(msg)

        self.property = property
        self.checks = checks
        if self.reftype == 'checks' and checks is None:
            msg = ("{} is a checks cache reference but checks dict not "
                   "provided".format(refstr))
            raise Exception(msg)

    @property
    def reftype(self):
        """
        These depict the type of property or propertycollection that can be
        referenced.

        Supported formats:
            @checks.<check_name>.<property_name>.<property_cache_key>[:func]
            @<property_name>.<property_cache_key>[:func]
        """
        if self.refstr.startswith('@checks.'):
            # This is an implementation of YPropertyChecks
            return "checks"
        else:
            # This is any implementation of YPropertyOverrideBase
            return "property"

    @property
    def _ref_body(self):
        """
        Strip the prefix from the reference string.
        """
        if self.reftype == 'checks':
            prefix = "@checks.{}.".format(self.check_name)
        else:
            prefix = "@{}.".format(self.property.property_name)

        return self.refstr.partition(prefix)[2]

    @classmethod
    def is_valid_cache_ref(cls, refstr):
        """
        Returns True if refstr is a valid property cache reference.

        The criteria for a valid reference is that it must be a string whose
        first character is @.
        """
        if type(refstr) != str:
            return False

        if not refstr.startswith('@'):
            return False

        return True

    @property
    def check_name(self):
        if self.reftype != 'checks':
            raise Exception("ref does not have type 'checks'")

        return self.refstr.partition('@checks.')[2].partition('.')[0]

    @property
    def property_name(self):
        if self.reftype == 'checks':
            return self._ref_body.partition('.')[0]

        return self.property.property_name

    @property
    def property_cache_key(self):
        """ Key for PropertyCache. """
        if self.reftype == 'checks':
            _key = self._ref_body.partition('.')[2]
        else:
            _key = self._ref_body

        # strip func if exists
        return _key.partition(':')[0]

    @property
    def property_cache_value_renderer_function(self):
        """
        This is an optional function name that can be provided as the last
        item in the reference string seperated by a colon.
        """
        if self.reftype == 'checks':
            _key = self._ref_body.partition('.')[2]
        else:
            _key = self._ref_body

        return _key.partition(':')[2]

    def apply_renderer_function(self, value):
        """
        The last section of a ref string can be a colon followed by a function
        name which itself can be one of two things; any method supported by
        builtins or "comma_join".
        """
        func = self.property_cache_value_renderer_function
        if func:
            if func == "comma_join":
                # needless to say this will only work with lists, dicts etc.
                return ', '.join(value)

            return getattr(builtins, func)(value)

        return value

    def resolve(self):
        if self.property is None:
            if not self.checks:
                raise Exception("property required in order to resolve cache "
                                "ref")

            check_cache = self.checks[self.check_name].cache
            property_cache = getattr(check_cache, self.property_name)
        else:
            property_cache = self.property.cache

        val = getattr(property_cache, self.property_cache_key)
        if val is None:
            return

        return self.apply_renderer_function(val)


class PropertyCache(object):

    def __init__(self):
        self._data = {}

    def merge(self, cache):
        if type(cache) != PropertyCache:
            log.error("attempt to merge cache failed - provided cache is not "
                      "a %s", type(self))
            return

        self._data.update(cache.cache)

    def set(self, key, data):
        log.debug("%s: caching key=%s with value=%s", id(self), key, data)
        _current = self._data.get(key)
        if _current and type(_current) == dict and type(data) == dict:
            self._data[key].update(data)
        else:
            self._data[key] = data

    @property
    def cache(self):
        return self._data

    def __getattr__(self, key):
        log.debug("%s: fetching key=%s (exists=%s)", id(self), key,
                  key in self.cache)
        if key not in self.cache:
            return

        return self.cache[key]


class YPropertyBase(object):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._cache = PropertyCache()

    @property
    def cache(self):
        return self._cache

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


class YPropertyOverrideBase(abc.ABC, YAMLDefOverrideBase, YPropertyBase):

    @abc.abstractproperty
    def property_name(self):
        """
        Every property override must implement this. This name must be unique
        across all properties and will be used to link the property in a
        PropertyCacheRefResolver.
        """


class YPropertyCollectionBase(YPropertyOverrideBase):

    @abc.abstractproperty
    def property_name(self):
        """
        Every property override must implement this. This name must be unique
        across all properties and will be used to link the property in a
        PropertyCacheRefResolver.
        """


@add_to_property_catalog
class YPropertyPriority(YPropertyOverrideBase):
    KEYS = ['priority']

    @property
    def property_name(self):
        return 'priority'

    @property
    def value(self):
        return int(self.content or 1)


@add_to_property_catalog
class YPropertyCheckParameters(YPropertyOverrideBase):
    KEYS = ['check-parameters']

    @property
    def property_name(self):
        return 'check-parameters'

    @property
    def search_period_hours(self):
        """
        If min is provided this is used to determine the period within which
        min applies. If period is unset, the period is infinite i.e. across all
        available data.

        Supported values:
          <int> hours

        """
        return int(self.content.get('search-period-hours', 0))

    @property
    def search_result_age_hours(self):
        """
        Result muct have aoccured within search-result-age-hours from current
        time (in the case of a sosreport would time sosreport was created).
        """
        return int(self.content.get('search-result-age-hours', 0))

    @property
    def min_results(self):
        """
        Minimum search matches required for result to be True (default is 1)
        """
        return int(self.content.get('min-results', 1))


class YPropertyCheck(YPropertyBase):

    def __init__(self, name, expr, input, requires, check_paramaters, *args,
                 **kwargs):
        super().__init__(*args, **kwargs)
        self.name = name
        self.expr = expr
        self.input = input
        self.requires = requires
        self.check_paramaters = check_paramaters

    @classmethod
    def get_datetime_from_result(cls, result):
        """
        This attempts to create a datetime object from a timestamp (usually
        from a log file) extracted from a search result. If it is not able
        to do so it will return None. The normal expectation is that two search
        result groups be available at index 1 and 2 but if only 1 is valid it
        will be used a fallback.
        """
        ts = result.get(1)
        if result.get(2):
            ts = "{} {}".format(ts, result.get(2))

        ts_formats = ["%Y-%m-%d %H:%M:%S.%f", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"]
        for format in ts_formats:
            try:
                return datetime.strptime(ts, format)
            except ValueError:
                continue

        ts = result.get(1)
        for format in ts_formats:
            try:
                return datetime.strptime(ts, format)
            except ValueError:
                continue

        log.warning("failed to parse timestamp string 1='%s' 2='%s' - "
                    "returning None", result.get(1), result.get(2))

    @classmethod
    def filter_by_age(cls, results, result_age_hours):
        if not result_age_hours:
            log.debug("result age filter not specified - skipping")
            return results

        current = CLIHelper().date(format='+%Y-%m-%d %H:%M:%S')
        if not current:
            log.warning("date() returned unexpected value '%s' - skipping "
                        "filter by age", current)
            return results

        current = datetime.strptime(current, "%Y-%m-%d %H:%M:%S")
        log.debug("applying search filter (result_age_hours=%s, "
                  "current='%s')", result_age_hours, current)

        _results = []
        for r in results:
            ts = cls.get_datetime_from_result(r)
            if ts and ts >= current - timedelta(hours=result_age_hours):
                _results.append(r)

        return _results

    @classmethod
    def filter_by_period(cls, results, period_hours, min_results):
        if not period_hours:
            log.debug("period filter not specified - skipping")
            return results

        log.debug("applying search filter (period_hours=%s, min_results=%s)",
                  period_hours, min_results)

        _results = []
        for r in results:
            ts = cls.get_datetime_from_result(r)
            if ts:
                _results.append((ts, r))

        results = []
        last = None
        prev = None
        count = 0

        for r in sorted(_results, key=lambda i: i[0], reverse=True):
            if last is None:
                last = r[0]
            elif r[0] < last - timedelta(hours=period_hours):
                last = prev
                prev = None
                # pop first element since it is now invalidated
                count -= 1
                results = results[1:]
            elif prev is None:
                prev = r[0]

            results.append(r)
            count += 1
            if count >= min_results:
                # we already have enough results so return
                break

        if len(results) < min_results:
            return []

        return [r[1] for r in results]

    @property
    def _result(self):
        if self.expr:
            if self.cache.expr:
                results = self.cache.expr.results
                log.debug("check %s - using cached result=%s", self.name,
                          results)
            else:
                s = FileSearcher()
                s.add_search_term(SearchDef(self.expr.value, tag='all'),
                                  self.input.path)
                results = s.search()
                self.expr.cache.set('results', results)

                # The following aggregates results by group/index and stores in
                # the property cache to make them accessible via
                # PropertyCacheRefResolver.
                results_by_idx = {}
                for item in results:
                    for _result in item[1]:
                        for idx, value in enumerate(_result):
                            if idx not in results_by_idx:
                                results_by_idx[idx] = set()

                            results_by_idx[idx].add(value)

                for idx in results_by_idx:
                    self.expr.cache.set('results_group_{}'.format(idx),
                                        list(results_by_idx[idx]))

                self.cache.set('expr', self.expr.cache)

            if not results:
                log.debug("check %s search has no matches so result=False",
                          self.name)
                return False

            results = results.find_by_tag('all')
            parameters = self.check_paramaters
            if parameters:
                result_age_hours = parameters.search_result_age_hours
                results = self.filter_by_age(results, result_age_hours)
                if results:
                    period_hours = parameters.search_period_hours
                    results = self.filter_by_period(results, period_hours,
                                                    parameters.min_results)

                count = len(results)
                if count >= parameters.min_results:
                    return True
                else:
                    log.debug("check %s does not have enough matches (%s) to "
                              "satisfy min of %s", self.name, count,
                              parameters.min_results)
                    return False
            else:
                log.debug("no check paramaters provided")
                return len(results) > 0

        elif self.requires:
            if self.cache.requires:
                result = self.cache.requires.passes
                log.debug("check %s - using cached result=%s", self.name,
                          result)
            else:
                result = self.requires.passes
                self.cache.set('requires', self.requires.cache)

            return result
        else:
            raise Exception("no supported properties found in check {}".format(
                            self.name))

    @property
    def result(self):
        log.debug("executing check %s", self.name)
        result = self._result
        log.debug("check %s result=%s", self.name, result)
        return result


@add_to_property_catalog
class YPropertyChecks(YPropertyCollectionBase):
    KEYS = ['checks']

    @property
    def property_name(self):
        return 'checks'

    def __iter__(self):
        section = YDefsSection(self.property_name, self.content)
        for c in section.leaf_sections:
            yield YPropertyCheck(c.name, c.expr, c.input, c.requires,
                                 c.check_parameters)


class YPropertyConclusion(object):

    def __init__(self, name, priority, decision=None, raises=None):
        self.name = name
        self.priority = priority
        self.decision = decision
        self.raises = raises
        self.issue_message = None
        self.issue_type = None

    def get_check_result(self, name, checks):
        result = None
        if name in checks:
            result = checks[name].result
        else:
            raise Exception("conclusion '{}' has unknown check '{}' in "
                            "decision set".format(self.name, name))

        return result

    def _run_conclusion(self, checks):
        if self.decision.is_singleton:
            return self.get_check_result(self.decision.content, checks)
        else:
            for op, checknames in self.decision:
                results = [self.get_check_result(c, checks) for c in
                           checknames]
                if op == 'and':
                    return all(results)
                elif op == 'or':
                    return any(results)
                else:
                    log.debug("decision has unsupported operator '%s'", op)

        return False

    def reached(self, checks):
        """ Return true if a conclusion has been reached. """
        result = self._run_conclusion(checks)
        message = self.raises.message_with_format_dict_applied(checks=checks)
        self.issue_message = message
        self.issue_type = self.raises.type
        return result


@add_to_property_catalog
class YPropertyConclusions(YPropertyCollectionBase):
    KEYS = ['conclusions']

    @property
    def property_name(self):
        return 'conclusions'

    def __iter__(self):
        section = YDefsSection(self.property_name, self.content)
        for c in section.leaf_sections:
            yield YPropertyConclusion(c.name, c.priority, c.decision, c.raises)


@add_to_property_catalog
class YPropertyDecision(YPropertyOverrideBase):
    KEYS = ['decision']

    @property
    def property_name(self):
        return 'decision'

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


@add_to_property_catalog
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
    def property_name(self):
        return 'expr'

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


@add_to_property_catalog
class YPropertyRaises(YPropertyOverrideBase):
    KEYS = ['raises']

    @property
    def property_name(self):
        return 'raises'

    @property
    def message(self):
        """ Optional """
        return self.content.get('message')

    def message_with_format_dict_applied(self, property=None, checks=None):
        """
        If a format-dict is provided this will resolve any cache references
        then format the message. Returns formatted message.

        Either property or checks must be provided (but not both).

        @params property: optional YPropertyOverride object.
        @params checks: optional dict of YPropertyChecks objects.
        """
        fdict = self.format_dict
        if not fdict:
            return self.message

        for key, value in fdict.items():
            if PropertyCacheRefResolver.is_valid_cache_ref(value):
                rvalue = PropertyCacheRefResolver(value, property=property,
                                                  checks=checks).resolve()
                log.debug("updating format-dict key=%s with cached %s",
                          key, value)
                fdict[key] = rvalue

        message = self.message
        if message is not None:
            message = str(message).format(**fdict)

        return message

    def message_with_format_list_applied(self, searchresult):
        """
        If format-groups have been provided this will extract their
        corresponding values from searchresult and use them to format the
        message. Returns formatted message.

        @param searchresult: a searchtools.SearchResult object.
        """
        if not self.format_groups:
            return self.message

        format_list = []
        for idx in self.format_groups:
            format_list.append(searchresult.get(idx))

        message = self.message
        if message is not None:
            message = str(message).format(*format_list)

        return message

    @property
    def format_dict(self):
        """
        Optional dict of key/val pairs used to format the message string.

        Keys that start with @ are used as references to properties allowing
        us to extract cached values.
        """
        _format_dict = self.content.get('format-dict')
        if not _format_dict:
            return {}

        fdict = {}
        for k, v in _format_dict.items():
            if PropertyCacheRefResolver.is_valid_cache_ref(v):
                # save string for later parsing/extraction
                fdict[k] = v
            else:
                fdict[k] = self.get_import(v)

        return fdict

    @property
    def format_groups(self):
        """ Optional """
        return self.content.get('search-result-format-groups')

    @property
    def type(self):
        """ This is a string import path to an implementation of
        core.issues.IssueTypeBase and will be used to raise an
        issue using message as argument. """
        return self.get_cls(self.content['type'])


@add_to_property_catalog
class YPropertyInput(YPropertyOverrideBase):
    KEYS = ['input']
    TYPE_COMMAND = 'command'
    TYPE_FILESYSTEM = 'filesystem'

    @property
    def property_name(self):
        return 'input'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.cmd_tmp_path = None

    @property
    def options(self):
        defaults = {'disable-all-logs': False,
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
            path = os.path.join(HotSOSConfig.DATA_ROOT, self.fs_path)
            if (HotSOSConfig.USE_ALL_LOGS and not
                    self.options['disable-all-logs']):
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
            out = getattr(CLIHelper(), self.command)(*args, **kwargs)
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


class YRequirementTypeBase(abc.ABC, YPropertyBase):

    def __init__(self, settings, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.settings = settings

    def ops_to_str(self, ops):
        """
        Convert an ops list of tuples to a string. This is typically used when
        printing in a msg or storing in the cache.
        """
        if not ops:
            return ""

        _result = []
        for op in ops:
            item = str(op[0])
            if len(op) > 1:
                item = "{} {}".format(item, op[1])

            _result.append(item)

        return ' -> '.join(_result)

    def apply_op(self, op, input=None, expected=None, force_expected=False):
        log.debug("op=%s, input=%s, expected=%s, force_expected=%s", op,
                  input, expected, force_expected)
        if expected is not None or force_expected:
            return getattr(operator, op)(input, expected)

        return getattr(operator, op)(input)

    def apply_ops(self, ops, input=None, normalise_value_types=False):
        """
        Takes a list of operations and processes each one where each takes as
        input the output of the previous.

        @param ops: list of tuples of operations and optional args.
        @param input: the value that is used as input to the first operation.
        @param normalise_value_types: if an operation has an expected value and
                                      and this is True, the type of the input
                                      will be cast to that of the expectced
                                      value.
        """
        log.debug("ops=%s, input=%s", ops, input)
        if type(ops) != list:
            raise Exception("Expected list of ops but got {}".
                            format(ops))

        for op in ops:
            expected = None
            force_expected = False
            if len(op) > 1:
                # if an expected value was provided we must use it regardless
                # of what it is.
                force_expected = True
                expected = op[1]

                if expected is not None and normalise_value_types:
                    input = type(expected)(input)

            input = self.apply_op(op[0], input=input, expected=expected,
                                  force_expected=force_expected)

        return input

    @abc.abstractmethod
    def handler(self):
        """
        Handler implementation for this type.
        """

    @property
    def passes(self):
        """ Assert whether the requirement is met.

        Returns True if met otherwise False.
        """
        try:
            return self.handler()
        except Exception:
            # display traceback here before it gets swallowed up.
            log.exception("requires.passes raised the following")
            raise


class YRequirementTypeAPT(YRequirementTypeBase):

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

    def handler(self):
        # Value can be a package name or dict that provides more
        # information about the package.
        if type(self.settings) != dict:
            packages = {self.settings: None}
        else:
            packages = self.settings

        versions_actual = []
        for pkg, versions in packages.items():
            apt_info = APTPackageChecksBase([pkg])
            result = apt_info.is_installed(pkg)
            if result and versions:
                pkg_ver = apt_info.get_version(pkg)
                versions_actual.append(pkg_ver)
                result = self._package_version_within_ranges(pkg_ver,
                                                             versions)
                log.debug("package %s=%s within version ranges %s "
                          "(result=%s)", pkg, pkg_ver, versions, result)

            # bail at first failure
            if not result:
                break

        self.cache.set('package', ', '.join(packages.keys()))
        self.cache.set('version', ', '.join(versions_actual))
        log.debug('requirement check: apt %s (result=%s)', pkg, result)
        return result


class YRequirementTypeSnap(YRequirementTypeBase):

    def handler(self):
        pkg = self.settings
        result = pkg in SnapPackageChecksBase(core_snaps=[pkg]).all
        log.debug('requirement check: snap %s (result=%s)', pkg, result)
        self.cache.set('package', pkg)
        return result


class YRequirementTypeSystemd(YRequirementTypeBase):

    def handler(self):
        if type(self.settings) != dict:
            services = {self.settings: None}
            op = None
        else:
            services = self.settings
            op = self.settings.get('op', 'eq')

        actual = None
        ops_all = []
        for svc, state in services.items():
            svcinfo = ServiceChecksBase([svc]).services
            self.cache.set('ops', op)
            if svc not in svcinfo:
                result = False
                break

            actual = svcinfo[svc]
            self.cache.set('state_actual', actual)
            if state is None:
                result = True
            else:
                ops = [[op, state]]
                ops_all.extend(ops)
                result = self.apply_ops(ops, input=actual)
                if not result:
                    # bail on first fail
                    break

        self.cache.set('ops', self.ops_to_str(ops_all))
        self.cache.set('service', ', '.join(services.keys()))
        log.debug('requirement check: systemd %s (result=%s)',
                  list(services.keys()), result)
        return result


class YRequirementTypeProperty(YRequirementTypeBase):

    def handler(self):
        if type(self.settings) != dict:
            path = self.settings
            # default is get bool (True/False) for value
            ops = [['truth']]
        else:
            path = self.settings['path']
            ops = self.settings.get('ops')

        actual = self.get_property(path)
        result = self.apply_ops(ops, input=actual)
        log.debug('requirement check: property %s %s (result=%s)',
                  path, self.ops_to_str(ops), result)
        self.cache.set('ops', self.ops_to_str(ops))
        self.cache.set('value_actual', actual)
        return result


class YRequirementTypeConfig(YRequirementTypeBase):

    def handler(self):
        invert_result = self.settings.get('invert-result', False)
        handler = self.settings['handler']
        obj = self.get_cls(handler)
        path = self.settings.get('path')
        if path:
            path = os.path.join(HotSOSConfig.DATA_ROOT, path)
            cfg = obj(path)
        else:
            cfg = obj()

        results = []
        for key, assertion in self.settings['assertions'].items():
            ops = assertion.get('ops')
            section = assertion.get('section')
            if section:
                actual = cfg.get(key, section=section)
            else:
                actual = cfg.get(key)

            log.debug("requirement check: config %s %s (actual=%s)", key,
                      self.ops_to_str(ops), actual)

            if ops:
                if actual is None:
                    result = assertion.get('allow-unset', False)
                else:
                    result = self.apply_ops(ops, input=actual,
                                            normalise_value_types=True)
            else:
                result = self.apply_ops([['ne', None]], input=actual)

            # This is a bit iffy since it only gives us the final config
            # assertion checked.
            self.cache.set('key', key)
            self.cache.set('ops', self.ops_to_str(ops))
            self.cache.set('value_actual', actual)

            # return on first fail
            if not result and not invert_result:
                return False

            results.append(result)

        if invert_result:
            return not all(results)

        return all(results)


@add_to_property_catalog
class YPropertyRequires(YPropertyOverrideBase):
    KEYS = ['requires']
    # these must be logical operators
    VALID_GROUP_KEYS = ['and', 'or', 'not']
    FINAL_RESULT_OP = 'and'
    REQ_TYPES = {'apt': YRequirementTypeAPT,
                 'snap': YRequirementTypeSnap,
                 'config': YRequirementTypeConfig,
                 'systemd': YRequirementTypeSystemd,
                 'property': YRequirementTypeProperty}

    @property
    def property_name(self):
        return 'requires'

    def process_requirement(self, item, cache=False):
        """ Process a single requirement and return its boolean result.

        @param requirement: a YRequirementObj object.
        @param cache: if set to True the cached info from the requirement will
        be saved locally. This can only be done for a single requirement.
        """
        # need at least one
        if any(item.values()):
            requirement = None
            for name, handler in self.REQ_TYPES.items():
                if item.get(name):
                    requirement = handler(item[name])
                    break

            result = requirement.passes
            # Caching a requires comprising of more than one requirement e.g.
            # lists or groups is not supported since there is no easy way to
            # make then uniquely identifiable so this should only be used when
            # processing single requirements. Note that top-level attributes
            # like the passes result will still be cached.
            if cache:
                self.cache.merge(requirement.cache)

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
                result = self.process_requirement(entry)
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
                result = self.process_requirement(item)
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
        if type(self.content) == dict:
            if not self._is_groups(self.content):
                log.debug("single requirement provided")
                item = {k: self.content.get(k) for k in self.REQ_TYPES}
                results = {self.FINAL_RESULT_OP:
                           [self.process_requirement(item, cache=True)]}
            else:
                log.debug("requirement groups provided")
                results = self.process_requirement_group(self.content)

        elif type(self.content) == list:
            log.debug("list of requirements provided")
            results = self.process_multi_requirements_list(self.content)

        result = self.finalise_result(results)
        self.cache.set('passes', result)
        return result


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
        path = os.path.join(HotSOSConfig.PLUGIN_YAML_DEFS, self.ytype,
                            HotSOSConfig.PLUGIN_NAME)
        if os.path.isdir(path):
            return self._get_defs_recursive(path)

    @property
    def plugin_defs_legacy(self):
        path = os.path.join(HotSOSConfig.PLUGIN_YAML_DEFS,
                            '{}.yaml'.format(self.ytype))
        if not os.path.exists(path):
            return {}

        log.debug("using legacy defs path %s", path)
        with open(path) as fd:
            defs = yaml.safe_load(fd.read()) or {}

        return defs.get(HotSOSConfig.PLUGIN_NAME, {})

    def load_plugin_defs(self):
        log.debug('loading %s definitions for plugin=%s', self.ytype,
                  HotSOSConfig.PLUGIN_NAME,)

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
