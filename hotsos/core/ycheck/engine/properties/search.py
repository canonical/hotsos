from datetime import (
    datetime,
    timedelta,
)
from hotsos.core.host_helpers import UptimeHelper, CLIHelper
from hotsos.core.log import log
from hotsos.core.search import (
    SearchDef,
    SequenceSearchDef,
    SearchConstraintSearchSince,
)
from hotsos.core.ycheck.engine.properties.common import (
    cached_yproperty_attr,
    YPropertyOverrideBase,
    YPropertyMappedOverrideBase,
    add_to_property_catalog,
)

# use some common expressions. these include from openstack and  ceph plugins.
COMMON_LOG_DATETIME_EXPRS = [r"^([\d-]+\s+[\d:]+)", r"^([\d-]+)[\sT]([\d:]+)",
                             r"^([0-9-]+)T([0-9:]+)"]


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
        Result must have occurred within this number of hours from the current
        time (for a sosreport this would be when it was created).
        """
        return int(self.content.get('search-result-age-hours', 0))

    @cached_yproperty_attr
    def min_hours_since_last_boot(self):
        """
        Search result must be at least this number of hours after the last
        boot time.
        """
        return int(self.content.get('min-hours-since-last-boot', 0))

    @cached_yproperty_attr
    def min_results(self):
        """
        Minimum search matches required for result to be True (default is 1)
        """
        return int(self.content.get('min-results', 1))

    @cached_yproperty_attr
    def filesearch_constraints_obj(self):
        """
        Create a search constraints object representing the paramaters in
        this property.
        """
        has_result_hours = 'search-result-age-hours' in self.content
        has_boot_hours = 'min-hours-since-last-boot' in self.content
        if not any([has_result_hours, has_boot_hours]):
            return

        uptime_etime_hours = UptimeHelper().hours
        hours = self.search_result_age_hours
        min_hours_since_last_boot = self.min_hours_since_last_boot
        if not hours:
            hours = max(uptime_etime_hours - min_hours_since_last_boot, 0)
        elif min_hours_since_last_boot > 0:  # pylint: disable=W0143
            hours = min(hours,
                        max(uptime_etime_hours - min_hours_since_last_boot, 0))

        return SearchConstraintSearchSince(exprs=COMMON_LOG_DATETIME_EXPRS,
                                           hours=hours)


class YPropertySearchOpt(YPropertyOverrideBase):

    @classmethod
    def _override_keys(cls):
        return ['expr', 'hint', 'passthrough-results']

    def __bool__(self):
        return bool(self.content)

    @property
    def expr(self):
        """ Can be string or list. """
        return self.content

    def __str__(self):
        # should use bool() for passthrough-results
        invalid = ['passthrough-results', 'expr']
        valid = [k for k in self._override_keys() if k not in invalid]
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
            log.debug("no search constraints to apply")
            return results

        log.debug("applying search constraints")
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

    def _resolve_exprs(self, patterns):
        """
        Resolve any expressions provided as variable to their value. Non-vars
        are returned as-is.
        """
        _patterns = []
        if type(patterns) == list:
            for p in patterns:
                _patterns.append(self.resolve_var(p))
        else:
            _patterns = self.resolve_var(patterns)

        return _patterns

    @property
    def search_pattern(self):
        if self.expr:
            return self._resolve_exprs(self.expr.expr)

        # can be supplied as a single string or list of strings
        patterns = self._resolve_exprs(list(self.content.keys()))
        if len(patterns) == 1:
            return patterns[0]

        return patterns

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

        constraints = None
        if self.constraints and self.constraints.filesearch_constraints_obj:
            constraints = [self.constraints.filesearch_constraints_obj]

        sdef = SearchDef(pattern, tag=self.unique_search_tag, hint=hint,
                         constraints=constraints)

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

    def load_searcher(self, searchobj, search_path, allow_constraints=True):
        """ Load search definitions into the given searcher object. """
        sdef = self.simple_search
        if sdef:
            log.debug("loading simple search")
            searchobj.add(sdef, search_path,
                          allow_global_constraints=allow_constraints)
            return

        sdef = self.sequence_search
        if sdef:
            log.debug("loading sequence search")
            searchobj.add(sdef, search_path,
                          allow_global_constraints=allow_constraints)
            return

        sdef = self.sequence_passthrough_search
        if sdef:
            log.debug("loading sequence passthrough searches")
            for _sdef in sdef:
                searchobj.add(_sdef, search_path,
                              allow_global_constraints=allow_constraints)


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
