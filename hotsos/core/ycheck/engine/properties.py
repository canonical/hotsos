import os

import abc
import operator

from datetime import (
    datetime,
    timedelta,
)

from hotsos.core.searchtools import (
    FileSearcher,
    SearchDef,
)
from hotsos.core.host_helpers import (
    APTPackageChecksBase,
    CLIHelper,
    DPKGVersionCompare,
    ServiceChecksBase,
    SnapPackageChecksBase,
)
from hotsos.core.issues import IssueContext
from hotsos.core.config import HotSOSConfig
from hotsos.core.log import log
from hotsos.core.utils import mktemp_dump
from hotsos.core.ystruct import YAMLDefSection
from hotsos.core.ycheck.engine.properties_common import (
    cached_yproperty_attr,
    PropertyCacheRefResolver,
    YPropertyBase,
    YPropertyOverrideBase,
    YPropertyCollectionBase,
    LogicalCollectionMap,
    LogicalCollectionHandler,
)


YPropertiesCatalog = []


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


def add_to_property_catalog(c):
    """
    Add property implementation to the global catalog.
    """
    YPropertiesCatalog.append(c)


@add_to_property_catalog
class YPropertyPriority(YPropertyOverrideBase):
    KEYS = ['priority']

    @property
    def property_name(self):
        return 'priority'

    @cached_yproperty_attr
    def value(self):
        return int(self.content or 1)


@add_to_property_catalog
class YPropertyCheckParameters(YPropertyOverrideBase):
    KEYS = ['check-parameters']

    @property
    def property_name(self):
        return 'check-parameters'

    @cached_yproperty_attr
    def search_period_hours(self):
        """
        If min is provided this is used to determine the period within which
        min applies. If period is unset, the period is infinite i.e. across all
        available data.

        Supported values:
          <int> hours

        """
        return int(self.content.get('search-period-hours', 0))

    @cached_yproperty_attr
    def search_result_age_hours(self):
        """
        Result muct have aoccured within search-result-age-hours from current
        time (in the case of a sosreport would time sosreport was created).
        """
        return int(self.content.get('search-result-age-hours', 0))

    @cached_yproperty_attr
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

    def _result(self):
        if self.expr:
            if self.cache.expr:
                results = self.cache.expr.results
                log.debug("check %s - using cached result=%s", self.name,
                          results)
            else:
                s = FileSearcher()
                s.add_search_term(SearchDef(self.expr.value, tag=self.name),
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

            results = results.find_by_tag(self.name)
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
        result = self._result()
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
        self.issue = None
        # Use this to add any context to the issue. This context
        # will be retrievable as machine readable output.
        self.context = IssueContext()

    def get_check_result(self, name, checks):
        result = None
        if name in checks:
            result = checks[name].result
        else:
            raise Exception("conclusion '{}' has unknown check '{}' in "
                            "decision set".format(self.name, name))

        return result

    def reached(self, checks):
        """
        Return True/False result of this conclusion and prepare issue info.
        """
        log.debug("running conclusion %s", self.name)
        logicmap = LogicalCollectionMap(self.decision.content,
                                        {name: lambda name: checks[name]
                                         for name in checks})
        result = LogicalCollectionHandler(logicmap)()
        if not result:
            return False

        search_results = None
        for name, check in checks.items():
            if check.expr and check.expr.cache.results:
                search_results = check.expr.cache.results.find_by_tag(name)
                if search_results:
                    # Save some context for the issue
                    self.context.set(**{r.source: r.linenumber
                                        for r in search_results})
            elif check.requires:
                # Dump the requires cache into the context. We improve this
                # later by addign more info.
                self.context.set(**check.requires.cache.cache)

        if self.raises.format_groups:
            if search_results:
                # we only use the first result
                message = self.raises.message_with_format_list_applied(
                                                             search_results[0])
            else:
                message = self.raises.message
                log.warning("no search results found so not applying format "
                            "groups")
        else:
            message = self.raises.message_with_format_dict_applied(
                                                                 checks=checks)

        if self.raises.type.ISSUE_TYPE == 'bug':
            self.issue = self.raises.type(self.raises.bug_id, message)
        else:
            self.issue = self.raises.type(message)

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
            yield YPropertyConclusion(c.name, c.priority, decision=c.decision,
                                      raises=c.raises)


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

    @cached_yproperty_attr
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
                log.debug("updating format-dict key=%s with cached %s (%s)",
                          key, value, rvalue)
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

    @cached_yproperty_attr
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

    @cached_yproperty_attr
    def format_groups(self):
        """ Optional """
        return self.content.get('search-result-format-groups')

    @cached_yproperty_attr
    def type(self):
        """ Name of core.issues.IssueTypeBase object and will be used to raise
        an issue or bug using message as argument. """
        _type = "hotsos.core.issues.{}".format(self.content['type'])
        return self.get_cls(_type)


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

    @cached_yproperty_attr
    def options(self):
        defaults = {'disable-all-logs': False,
                    'args': [],
                    'kwargs': {},
                    'args-callback': None}
        _options = self.content.get('options', defaults)
        defaults.update(_options)
        return defaults

    @cached_yproperty_attr
    def command(self):
        return self.content.get('command')

    @cached_yproperty_attr
    def fs_path(self):
        return self.content.get('path')

    @cached_yproperty_attr
    def path(self):
        if self.fs_path:  # pylint: disable=W0125
            path = os.path.join(HotSOSConfig.DATA_ROOT, self.fs_path)
            if (HotSOSConfig.USE_ALL_LOGS and not
                    self.options['disable-all-logs']):
                path = "{}*".format(path)

            return path

        if self.command:  # pylint: disable=W0125
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
    def result(self):
        """ Assert whether the requirement is met.

        Returns True if met otherwise False.
        """
        try:
            return self.handler()
        except Exception:
            # display traceback here before it gets swallowed up.
            log.exception("requires.%s.result raised the following",
                          self.__class__.__name__)
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
        packages_under_test = list(packages.keys())
        apt_info = APTPackageChecksBase(packages_under_test)
        for pkg, versions in packages.items():
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

    def check_service(self, svc, ops, started_after_svc_obj=None):
        if started_after_svc_obj:
            a = svc.start_time
            b = started_after_svc_obj.start_time
            if a and b:
                log.debug("%s started=%s, %s started=%s", svc.name,
                          a, started_after_svc_obj.name, b)
                if a < b:
                    delta = b - a
                else:
                    delta = a - b

                # Allow a small grace period to avoid false positives e.g.
                # on node boot when services are started all at once.
                grace = 120
                # In order for a service A to have been started after B it must
                # have been started more than GRACE seconds after B.
                if a > b:
                    if delta >= timedelta(seconds=grace):
                        log.debug("svc %s started >= %ds of start of %s "
                                  "(delta=%s)", svc.name, grace,
                                  started_after_svc_obj.name, delta)
                    else:
                        log.debug("svc %s started < %ds of start of %s "
                                  "(delta=%s)", svc.name, grace,
                                  started_after_svc_obj.name, delta)
                        return False
                else:
                    log.debug("svc %s started before or same as %s "
                              "(delta=%s)", svc.name,
                              started_after_svc_obj.name, delta)
                    return False

        return self.apply_ops(ops, input=svc.state)

    def handler(self):
        default_op = 'eq'
        result = True

        if type(self.settings) != dict:
            service_checks = {self.settings: None}
        else:
            service_checks = self.settings

        services_under_test = list(service_checks.keys())
        for settings in service_checks.values():
            if type(settings) == dict and 'started-after' in settings:
                services_under_test.append(settings['started-after'])

        svcinfo = ServiceChecksBase(services_under_test).services
        cache_info = {}
        for svc, settings in service_checks.items():
            if svc not in svcinfo:
                result = False
                # bail on first fail
                break

            svc_obj = svcinfo[svc]
            cache_info[svc] = {'actual': svc_obj.state}

            # The service critera can be defined in three different ways;
            # string svc name, dict of svc name: state and dict of svc name:
            # dict of settings.
            if settings is None:
                continue

            started_after_svc_obj = None
            if type(settings) == str:
                state = settings
                ops = [[default_op, state]]
            else:
                op = settings.get('op', default_op)
                started_after = settings.get('started-after')
                if started_after:
                    started_after_svc_obj = svcinfo.get(started_after)
                    if not started_after_svc_obj:
                        # if a started-after service has been provided but
                        # that service does not exist then we return False.
                        result = False
                        continue

                if 'state' in settings:
                    ops = [[op, settings.get('state')]]
                else:
                    ops = []

            cache_info[svc]['ops'] = self.ops_to_str(ops)
            result = self.check_service(
                                   svc_obj, ops,
                                   started_after_svc_obj=started_after_svc_obj)
            if not result:
                # bail on first fail
                break

        self.cache.set('services', ', '.join(cache_info))
        svcs = ["{}={}".format(svc, state)
                for svc, state in service_checks.items()]
        log.debug('requirement check: %s (result=%s)',
                  ', '.join(svcs), result)
        return result


class YRequirementTypeProperty(YRequirementTypeBase):

    def handler(self):
        default_ops = [['truth']]
        if type(self.settings) != dict:
            path = self.settings
            # default is get bool (True/False) for value
            ops = default_ops
        else:
            path = self.settings['path']
            ops = self.settings.get('ops', default_ops)

        actual = self.get_property(path)
        result = self.apply_ops(ops, input=actual)
        log.debug('requirement check: property %s %s (result=%s)',
                  path, self.ops_to_str(ops), result)
        self.cache.set('property', path)
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
    REQ_TYPES = {'apt': YRequirementTypeAPT,
                 'snap': YRequirementTypeSnap,
                 'config': YRequirementTypeConfig,
                 'systemd': YRequirementTypeSystemd,
                 'property': YRequirementTypeProperty}

    @property
    def property_name(self):
        return 'requires'

    @property
    def passes(self):
        """
        Content can either be a single requirement, dict of requirement groups
        or list of requirements. List may contain individual requirements or
        groups.
        """
        log.debug("running requirement")
        logicmap = LogicalCollectionMap(self.content, self.REQ_TYPES,
                                        cache=self.cache)
        result = LogicalCollectionHandler(logicmap)()
        self.cache.set('passes', result)
        return result
