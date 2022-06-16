import abc
import builtins
import operator
import os

from datetime import (
    datetime,
    timedelta,
)

from hotsos.core.searchtools import (
    FileSearcher,
    SearchDef,
    SequenceSearchDef,
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
from hotsos.core.ystruct import YStructSection
from hotsos.core.ycheck.engine.properties_common import (
    cached_yproperty_attr,
    PropertyCacheRefResolver,
    YPropertyBase,
    YPropertyOverrideBase,
    YPropertyMappedOverrideBase,
    LogicalCollectionHandler,
    YDefsContext,
)


YPropertiesCatalog = []


class YDefsSection(YStructSection):

    def __init__(self, name, content):
        """
        @param name: name of defs group
        @param content: defs tree of type dict
        """
        super().__init__(name, content, override_handlers=YPropertiesCatalog,
                         context=YDefsContext())


def add_to_property_catalog(c):
    """
    Add property implementation to the global catalog.
    """
    YPropertiesCatalog.append(c)
    return c


@add_to_property_catalog
class YPropertyPriority(YPropertyOverrideBase):

    @classmethod
    def _override_keys(cls):
        return ['priority']

    @cached_yproperty_attr
    def value(self):
        return int(self.content or 1)


class YPropertyCheck(YPropertyBase):

    def __init__(self, name, search, input, requires, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = name
        self.search = search
        self.input = input
        self.requires = requires

    def _result(self):
        if self.search:
            if self.cache.search:
                results = self.cache.search.results
                log.debug("check %s - using cached result=%s", self.name,
                          results)
            else:
                results = self.search_results
                # save raw first
                self.search.cache.set('results_raw', results)
                # now save actual i.e. with constraints applied
                results = self.search.apply_constraints(results)
                self.search.cache.set('results', results)

                # The following aggregates results by group/index and stores in
                # the property cache to make them accessible via
                # PropertyCacheRefResolver.
                results_by_idx = {}
                for result in results:
                    for idx, value in enumerate(result):
                        if idx not in results_by_idx:
                            results_by_idx[idx] = set()

                        results_by_idx[idx].add(value)

                for idx in results_by_idx:
                    self.search.cache.set('results_group_{}'.format(idx),
                                          list(results_by_idx[idx]))

                self.cache.set('search', self.search.cache)

            if not results:
                log.debug("check %s search has no matches so result=False",
                          self.name)
                return False

            return True

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
class YPropertyChecks(YPropertyOverrideBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._resolved_checks = None

        s = FileSearcher()
        # first load all the search definitions into the searcher
        log.debug("loading checks searchdefs into filesearcher")
        for c in self.resolved_checks:
            if c.search:
                c.search.load_searcher(s, c.input.path)

        log.debug("executing searches")
        results = s.search()

        # now extract each checks's set of results
        log.debug("extracting search results")
        for c in self.resolved_checks:
            if c.search:
                tag = c.search.unique_search_tag
                c.search_results = results.find_by_tag(tag)

    @classmethod
    def _override_keys(cls):
        return ['checks']

    @cached_yproperty_attr
    def resolved_checks(self):
        if self._resolved_checks:
            return self._resolved_checks

        log.debug("parsing checks section")
        checks = YDefsSection(self._override_name, self.content)
        resolved = []
        for c in checks.leaf_sections:
            resolved.append(YPropertyCheck(c.name, c.search, c.input,
                                           c.requires))

        self._resolved_checks = resolved
        return resolved

    def __iter__(self):
        log.debug("iterating over checks")
        for c in self.resolved_checks:
            log.debug("returning check %s", c.name)
            yield c


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

    def reached(self, checks):
        """
        Return True/False result of this conclusion and prepare issue info.
        """
        log.debug("running conclusion %s", self.name)
        self.decision.add_checks_instances(checks)
        log.debug("decision:start")
        result = self.decision.run_collection()
        log.debug("decision:end")
        if not result:
            return False

        search_results = None
        for check in checks.values():
            if check.search and check.search.cache.results:
                search_results = check.search.cache.results
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
class YPropertyConclusions(YPropertyOverrideBase):

    @classmethod
    def _override_keys(cls):
        return ['conclusions']

    def __iter__(self):
        section = YDefsSection(self._override_name, self.content)
        for c in section.leaf_sections:
            yield YPropertyConclusion(c.name, c.priority, decision=c.decision,
                                      raises=c.raises)


class YPropertyDecisionBase(YPropertyMappedOverrideBase,
                            LogicalCollectionHandler):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.checks_instances = None

    @classmethod
    def _override_mapped_member_types(cls):
        return []

    def add_checks_instances(self, checks):
        self.checks_instances = checks

    def get_item_result_callback(self, item):
        name = str(item)
        if name not in self.checks_instances:
            raise Exception("no check found with name {}".format(name))

        return self.checks_instances[name].result

    def run_single(self, item):
        final_results = []
        for checkname in item:
            final_results.append(self.get_item_result_callback(checkname))

        return final_results


class YPropertyDecisionLogicalGroupsExtension(YPropertyDecisionBase):

    @classmethod
    def _override_keys(cls):
        return LogicalCollectionHandler.VALID_GROUP_KEYS


@add_to_property_catalog
class YPropertyDecision(YPropertyDecisionBase):

    @classmethod
    def _override_keys(cls):
        return ['decision']

    @classmethod
    def _override_mapped_member_types(cls):
        return super()._override_mapped_member_types() + \
                    [YPropertyDecisionLogicalGroupsExtension]


class YPropertySearchConstraints(YPropertyOverrideBase):

    @classmethod
    def _override_keys(cls):
        return ['constraints']

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


class YPropertySearchOpt(YPropertyOverrideBase):

    @classmethod
    def _override_keys(cls):
        return ['expr', 'hint', 'passthrough-results']

    def __bool__(self):
        return bool(self.content)

    def __str__(self):
        # should use bool() for passthrough-results
        invalid = 'passthrough-results'
        valid = [k for k in self._override_keys() if k != invalid]
        if self._override_name not in valid:
            raise Exception("__str__ only valid for {} (not {})".
                            format(','.join(valid),
                                   self._override_name))

        return self.content


class YPropertySearchBase(YPropertyMappedOverrideBase):

    @classmethod
    def _override_mapped_member_types(cls):
        return [YPropertySearchOpt, YPropertySearchConstraints]

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

        log.debug("%s results remain after applying filter", len(_results))
        return _results

    @classmethod
    def filter_by_period(cls, results, period_hours):
        if not period_hours:
            log.debug("period filter not specified - skipping")
            return results

        log.debug("applying search filter (period_hours=%s)", period_hours)

        _results = []
        for r in results:
            ts = cls.get_datetime_from_result(r)
            if ts:
                _results.append((ts, r))

        results = []
        last = None
        prev = None

        for r in sorted(_results, key=lambda i: i[0], reverse=True):
            if last is None:
                last = r[0]
            elif r[0] < last - timedelta(hours=period_hours):
                last = prev
                prev = None
                # pop first element since it is now invalidated
                results = results[1:]
            elif prev is None:
                prev = r[0]

            results.append(r)

        log.debug("%s results remain after applying filter", len(results))
        return [r[1] for r in results]

    def apply_constraints(self, results):
        if not self.constraints:
            return results

        count = len(results)
        result_age_hours = self.constraints.search_result_age_hours
        results = self.filter_by_age(results, result_age_hours)
        if results:
            period_hours = self.constraints.search_period_hours
            results = self.filter_by_period(results, period_hours)

        count = len(results)
        if count < self.constraints.min_results:
            log.debug("search does not have enough matches (%s) to "
                      "satisfy min of %s", count, self.constraints.min_results)
            return []

        log.debug("applying search constraints reduced results from %s to %s",
                  count, len(results))
        return results

    @property
    def unique_search_tag(self):
        return self._override_path

    @property
    def passthrough_results_opt(self):
        if self.passthrough_results is not None:
            return bool(self.passthrough_results)

        return False

    @property
    def search_pattern(self):
        if self.expr:
            return str(self.expr)

        return str(self)

    @property
    def is_sequence_search(self):
        seq_keys = YPropertySequencePart._override_keys()
        return any([getattr(self, key) for key in seq_keys])

    @property
    def simple_search(self):
        if (self.is_sequence_search or not self.search_pattern or
                self.passthrough_results_opt):
            return

        sdef = self.cache.simple_search
        if sdef:
            return sdef

        pattern = self.search_pattern
        hint = None
        if self.hint:
            hint = str(self.hint)

        sdef = SearchDef(pattern, tag=self.unique_search_tag, hint=hint)
        self.cache.set('simple_search', sdef)
        return sdef

    @property
    def sequence_search(self):
        if not self.is_sequence_search or self.passthrough_results_opt:
            return

        sdef = self.cache.sequence_search
        if sdef:
            return sdef

        seq_start = self.start
        seq_body = self.body
        seq_end = self.end

        if (seq_body or (seq_end and not self.passthrough_results_opt)):
            sd_start = SearchDef(seq_start.search_pattern)

            sd_end = None
            # explicit end is optional for sequence definition
            if seq_end:
                sd_end = SearchDef(seq_end.search_pattern)

            sd_body = None
            if seq_body:
                sd_body = SearchDef(seq_body.search_pattern)

            # NOTE: we don't use hints here
            tag = self.unique_search_tag
            sdef = SequenceSearchDef(start=sd_start, body=sd_body,
                                     end=sd_end, tag=tag)
            self.cache.set('sequence_search', sdef)
            return sdef
        else:
            log.warning("invalid sequence definition passthrough=%s "
                        "start=%s, body=%s, end=%s",
                        self.passthrough_results_opt, seq_start, seq_body,
                        seq_end)

    @property
    def sequence_passthrough_search(self):
        if not self.is_sequence_search or not self.passthrough_results_opt:
            return

        sdef = self.cache.sequence_passthrough_search
        if sdef:
            return sdef

        seq_start = self.start
        seq_end = self.end

        if self.passthrough_results_opt and all([seq_start, seq_end]):
            # start and end required for core.analytics.LogEventStats
            start_tag = "{}-start".format(self.unique_search_tag)
            end_tag = "{}-end".format(self.unique_search_tag)
            sdefs = [SearchDef(str(seq_start.search_pattern), tag=start_tag),
                     SearchDef(str(seq_end.search_pattern), tag=end_tag)]
            self.cache.set('sequence_passthrough_search', sdefs)
            return sdefs

    def load_searcher(self, searchobj, search_path):
        """ Load search definitions into the given searcher object. """
        sdef = self.simple_search
        if sdef:
            log.debug("loading simple search")
            searchobj.add_search_term(sdef, search_path)
            return

        sdef = self.sequence_search
        if sdef:
            log.debug("loading sequence search")
            searchobj.add_search_term(sdef, search_path)
            return

        sdef = self.sequence_passthrough_search
        if sdef:
            log.debug("loading sequence passthrough searches")
            for _sdef in sdef:
                searchobj.add_search_term(_sdef, search_path)


class YPropertySequencePart(YPropertySearchBase):

    @classmethod
    def _override_keys(cls):
        return ['start', 'body', 'end']

    def __str__(self):
        for stack in self._stack.current.content.values():
            return stack.current.content


@add_to_property_catalog
class YPropertySearch(YPropertySearchBase):

    @classmethod
    def _override_keys(cls):
        return ['search']

    @classmethod
    def _override_mapped_member_types(cls):
        members = super()._override_mapped_member_types()
        return members + [YPropertySequencePart]


@add_to_property_catalog
class YPropertyRaises(YPropertyOverrideBase):

    @classmethod
    def _override_keys(cls):
        return ['raises']

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

    def apply_renderer_function(self, value, func):
        if not func:
            return value

        if func == "comma_join":
            # needless to say this will only work with lists, dicts etc.
            return ', '.join(value)

        return getattr(builtins, func)(value)

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
                func = v.partition(':')[2]
                v = v.partition(':')[0]
                fdict[k] = self.apply_renderer_function(self.get_import(v),
                                                        func)

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


class YPropertyInputBase(object):

    @property
    def options(self):
        defaults = {'disable-all-logs': False,
                    'args': [],
                    'kwargs': {},
                    'args-callback': None}

        if type(self.content) == dict:
            _options = self.content.get('options', defaults)
            defaults.update(_options)

        return defaults

    @cached_yproperty_attr
    def command(self):
        return self.content.get('command')

    @cached_yproperty_attr
    def fs_path(self):
        if type(self.content) == str:
            return self.content

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
            cmd_tmp_path = self.cache.cmd_tmp_path
            if cmd_tmp_path:
                return cmd_tmp_path

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

            cmd_tmp_path = mktemp_dump(out)
            self.cache.set('cmd_tmp_path', cmd_tmp_path)
            return cmd_tmp_path

        log.debug("no input provided")


@add_to_property_catalog
class YPropertyInput(YPropertyOverrideBase, YPropertyInputBase):

    @classmethod
    def _override_keys(cls):
        return ['input']


class YRequirementTypeBase(YPropertyOverrideBase):

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

    @classmethod
    def _override_keys(cls):
        return ['apt']

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
        if type(self.content) != dict:
            packages = {self.content: None}
        else:
            packages = self.content

        versions_actual = []
        packages_under_test = list(packages.keys())
        apt_info = APTPackageChecksBase(packages_under_test)
        for pkg, versions in packages.items():
            result = apt_info.is_installed(pkg) or False
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

    @classmethod
    def _override_keys(cls):
        return ['snap']

    def handler(self):
        pkg = self.content
        result = pkg in SnapPackageChecksBase(core_snaps=[pkg]).all
        log.debug('requirement check: snap %s (result=%s)', pkg, result)
        self.cache.set('package', pkg)
        return result


class YRequirementTypeSystemd(YRequirementTypeBase):

    @classmethod
    def _override_keys(cls):
        return ['systemd']

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

        if type(self.content) != dict:
            service_checks = {self.content: None}
        else:
            service_checks = self.content

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

    @classmethod
    def _override_keys(cls):
        return ['property']

    def handler(self):
        default_ops = [['truth']]
        if type(self.content) != dict:
            path = self.content
            # default is get bool (True/False) for value
            ops = default_ops
        else:
            path = self.content['path']
            ops = self.content.get('ops', default_ops)

        actual = self.get_property(path)
        result = self.apply_ops(ops, input=actual)
        log.debug('requirement check: property %s %s (result=%s)',
                  path, self.ops_to_str(ops), result)
        self.cache.set('property', path)
        self.cache.set('ops', self.ops_to_str(ops))
        self.cache.set('value_actual', actual)
        return result


class YRequirementTypeConfig(YRequirementTypeBase):

    @classmethod
    def _override_keys(cls):
        return ['config']

    def handler(self):
        invert_result = self.content.get('invert-result', False)
        handler = self.content['handler']
        obj = self.get_cls(handler)
        path = self.content.get('path')
        if path:
            path = os.path.join(HotSOSConfig.DATA_ROOT, path)
            cfg = obj(path)
        else:
            cfg = obj()

        results = []
        for key, assertion in self.content['assertions'].items():
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


class YRequirementTypePath(YPropertyInputBase, YRequirementTypeBase):

    @classmethod
    def _override_keys(cls):
        # We can't use 'input' since that property is already used.
        return ['path']

    @property
    def options(self):
        """
        Override this since we never want to have all-logs applied since
        it is not relevant in checking if the path exists.
        """
        _options = super().options
        _options['disable-all-logs'] = True
        return _options

    def handler(self):
        result = False
        # first try fs path in its raw format i.e. without ALL_LOGS applied. if
        # that is not available try the parsed path which would be command.
        if self.path and os.path.exists(self.path):
            result = True

        log.debug('requirement check: path %s (result=%s)', self.path, result)
        self.cache.set('path', self.path)
        return result


class YPropertyRequiresBase(YPropertyMappedOverrideBase,
                            LogicalCollectionHandler):

    @classmethod
    def _override_mapped_member_types(cls):
        return [YRequirementTypeAPT, YRequirementTypeSnap,
                YRequirementTypeConfig, YRequirementTypeSystemd,
                YRequirementTypeProperty, YRequirementTypePath]

    def get_item_result_callback(self, item, copy_cache=False):
        result = item.result
        if copy_cache:
            log.debug("merging cache with item of type %s",
                      item.__class__.__name__)
            self.cache.merge(item.cache)

        return result

    def run_single(self, item):
        final_results = []
        for rtype in item:
            for entry in rtype:
                result = self.get_item_result_callback(entry,
                                                       copy_cache=True)
                final_results.append(result)

        return final_results

    @property
    def passes(self):
        """
        Content can either be a single requirement, dict of requirement groups
        or list of requirements. List may contain individual requirements or
        groups.
        """
        log.debug("running requirement")
        try:
            result = self.run_collection()
        except Exception:
            log.exception("exception caught during run_collection:")
            raise

        self.cache.set('passes', result)
        return result


class YPropertyRequiresLogicalGroupsExtension(YPropertyRequiresBase):

    @classmethod
    def _override_keys(cls):
        return LogicalCollectionHandler.VALID_GROUP_KEYS


@add_to_property_catalog
class YPropertyRequires(YPropertyRequiresBase):

    @classmethod
    def _override_keys(cls):
        return ['requires']

    @classmethod
    def _override_mapped_member_types(cls):
        return super()._override_mapped_member_types() + \
                    [YPropertyRequiresLogicalGroupsExtension]
