import re
from datetime import timedelta
from functools import cached_property

from searchkit.constraints import TimestampMatcherBase
from hotsos.core.host_helpers import UptimeHelper, CLIHelper
from hotsos.core.log import log
from hotsos.core.search import (
    SearchDef,
    SequenceSearchDef,
    SearchConstraintSearchSince,
)
from hotsos.core.ycheck.engine.properties.common import (
    YPropertyOverrideBase,
    YPropertyMappedOverrideBase,
)


class CommonTimestampMatcher(TimestampMatcherBase):
    """
    This class must support regex patterns to match any kind of timestamp that
    we would expect to find. When a plugin results in the search of file
    (typically log files) that contain timestamps it is necessary to ensure
    the patterns in this class support matching those timestamps in order for
    search constraints to work.

    TODO: timestamps typically use an RFC format so we should brand them
          as such here.
    """
    MONTH_MAP = {'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4, 'may': 5,
                 'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10,
                 'nov': 11, 'dec': 12}

    @cached_property
    def _current_year(self):
        return CLIHelper().date(format='+%Y')

    @property
    def year(self):
        """ Needed for kernlog which has no year group. """
        try:
            return self.result.group('year')
        except IndexError:
            pass

        return self._current_year

    @property
    def month(self):
        """ Needed for kernlog which has a string month. """
        try:
            return int(self.result.group('month'))
        except ValueError:
            pass

        _month = self.result.group('month').lower()
        try:
            return self.MONTH_MAP[_month[:3]]
        except KeyError:
            log.exception("could not establish month integer from '%s'",
                          _month)

    @property
    def patterns(self):
        """
        This needs to contain timestamp patterns for any/all types of file
        we want to analyse where SearchConstraintsSince is to be applied.
        """
        # should match plugins.openstack.openstack.OpenstackDateTimeMatcher
        openstack = (r'^(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})+\s+'
                     r'(?P<hours>\d{2}):(?P<minutes>\d{2}):(?P<seconds>\d+)')
        # since they are identical we wont add but leaving in case we want to.
        # edit later.
        # juju = openstack
        # should match plugins.storage.ceph.CephDateTimeMatcher
        ceph = (r'^(?P<year>\d{4})-(?P<month>\d{2})-(?P<day>\d{2})[\sT]'
                r'(?P<hours>\d{2}):(?P<minutes>\d{2}):(?P<seconds>\d+)')
        # since they are identical we wont add but leaving in case we want to
        # edit later.
        # openvswitch = ceph
        kernlog = (r'^(?P<month>\w{3,5})\s+(?P<day>\d{1,2})\s+'
                   r'(?P<hours>\d{2}):(?P<minutes>\d{2}):(?P<seconds>\d{2})')
        return [openstack, ceph, kernlog]


class YPropertySearchConstraints(YPropertyOverrideBase):
    _override_keys = ['constraints']

    @property
    def valid_attributes(self):
        return ['search-period-hours', 'search-result-age-hours',
                'min-hours-since-last-boot', 'min-results']

    @cached_property
    def search_period_hours(self):
        """
        If min is provided this is used to determine the period within which
        min applies. If period is unset, the period is infinite i.e. across all
        available data.

        Supported values:
          <int> hours

        """
        return int(self.content.get('search-period-hours', 0))

    @cached_property
    def search_result_age_hours(self):
        """
        Result must have occurred within this number of hours from the current
        time (for a sosreport this would be when it was created).
        """
        return int(self.content.get('search-result-age-hours', 0))

    @cached_property
    def min_hours_since_last_boot(self):
        """
        Search result must be at least this number of hours after the last
        boot time.
        """
        return int(self.content.get('min-hours-since-last-boot', 0))

    @cached_property
    def min_results(self):
        """
        Minimum search matches required for result to be True (default is 1)
        """
        return int(self.content.get('min-results', 1))

    @cached_property
    def filesearch_constraints_obj(self):
        """
        Create a search constraints object representing the paramaters in
        this property.
        """
        invalid = []
        for attr in self.content:
            if attr not in self.valid_attributes:
                invalid.append(attr)

        if invalid:
            raise Exception("Invalid search constraints attributes found: {}. "
                            "Valid options are: {}".
                            format(', '.join(invalid),
                                   ', '.join(self.valid_attributes)))

        has_result_hours = 'search-result-age-hours' in self.content
        has_boot_hours = 'min-hours-since-last-boot' in self.content
        if not any([has_result_hours, has_boot_hours]):
            return

        uptime_etime_hours = UptimeHelper().in_hours
        hours = self.search_result_age_hours
        min_hours_since_last_boot = self.min_hours_since_last_boot
        if not hours:
            hours = max(uptime_etime_hours - min_hours_since_last_boot, 0)
        elif min_hours_since_last_boot > 0:
            hours = min(hours,
                        max(uptime_etime_hours - min_hours_since_last_boot, 0))

        return SearchConstraintSearchSince(
                                         ts_matcher_cls=CommonTimestampMatcher,
                                         hours=hours)


class YPropertySearchBase(YPropertyOverrideBase):

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
        else:
            ts = "{} 00:00:00".format(ts)

        ts_matcher = CommonTimestampMatcher(ts)
        if ts_matcher.matched:
            return ts_matcher.strptime

        log.warning("failed to parse timestamp string '%s' (num_group=%s) - "
                    "returning None", ts, len(result))

    @classmethod
    def filter_by_period(cls, results, period_hours):
        """ Return the most recent period_hours worth of results. """
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

        for r in sorted(_results, key=lambda i: i[0], reverse=True):
            if last is None:
                last = r[0]
            elif r[0] < last - timedelta(hours=period_hours):
                break

            results.append(r)

        log.debug("%s results remain after applying filter", len(results))
        return [r[1] for r in results]

    def apply_extra_constraints(self, results):
        """
        Apply further constraints filtering to search results.

        These are constraints supported by the constraints property that
        are not/cannot be applied by the search engine itself using
        SearchConstraintSearchSince.
        """
        if not self.constraints:
            log.debug("no extra search constraints to apply")
            return results

        log.debug("applying extra search constraints")
        if results:
            period_hours = self.constraints.search_period_hours
            results = self.filter_by_period(results, period_hours)

        count = len(results)
        if count < self.constraints.min_results:
            log.debug("search does not have enough matches (%s) to "
                      "satisfy min of %s", count, self.constraints.min_results)
            return []

        log.debug("applying extra search constraints reduced results from %s "
                  "to %s", count, len(results))
        return results

    @property
    def unique_search_tag(self):
        return self._override_path  # pylint: disable=E1101

    def _resolve_exprs(self, patterns):
        """
        Resolve any expressions provided as variable to their value. Non-vars
        are returned as-is.
        """
        _patterns = []
        if isinstance(patterns, list):
            for p in patterns:
                _patterns.append(self.resolve_var(p))  # pylint: disable=E1101
        else:
            _patterns.append(self.resolve_var(patterns))  # noqa, pylint: disable=E1101

        return _patterns

    @property
    def search_pattern(self):
        try:
            if self.expr:
                if isinstance(self, YPropertySearch):
                    expr = self.expr.expr
                else:
                    expr = self.expr
            else:
                expr = self.content

            # can be supplied as a single string or list of strings
            patterns = self._resolve_exprs(expr)
            if len(patterns) == 0:
                raise Exception("no search pattern (expr) defined")

            for pattern in patterns:
                if not re.search(r"[^\\]?\(.+\)", pattern):
                    log.info("pattern '%s' does not contain a subgroup. this "
                             "is inefficient and can result in unnecessary "
                             "memory consumption", pattern)

            if len(patterns) == 1:
                return patterns[0]

            return patterns
        except Exception:
            log.exception("")
            raise

    @property
    def is_sequence_search(self):
        seq_keys = YPropertySequencePart._get_override_keys_back_compat()
        return any(getattr(self, key) for key in seq_keys)

    @property
    def simple_search(self):
        if (self.is_sequence_search or not self.search_pattern or
                self.passthrough_results):
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
        if not self.is_sequence_search or self.passthrough_results:
            return

        sdef = self.cache.sequence_search
        if sdef:
            return sdef

        seq_start = self.start
        seq_body = self.body
        seq_end = self.end

        if (seq_body or (seq_end and not self.passthrough_results)):
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

        log.warning("invalid sequence definition passthrough=%s "
                    "start=%s, body=%s, end=%s",
                    self.passthrough_results, seq_start, seq_body,
                    seq_end)

    @property
    def sequence_passthrough_search(self):
        if not self.is_sequence_search or not self.passthrough_results:
            return

        sdef = self.cache.sequence_passthrough_search
        if sdef:
            return sdef

        seq_start = self.start
        seq_end = self.end

        if self.passthrough_results and all([seq_start, seq_end]):
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


class YPropertySearchOpt(YPropertyOverrideBase):
    _override_keys = ['expr', 'hint', 'passthrough-results']

    def __bool__(self):
        return bool(self.content)

    @property
    def expr(self):
        """ Can be string or list. """
        return self.content

    def __str__(self):
        # should use bool() for passthrough-results
        invalid = ['passthrough-results', 'expr']
        valid = [k for k in
                 self._get_override_keys_back_compat() if k not in invalid]
        if self._override_name not in valid:
            raise Exception("__str__ only valid for {} (not {})".
                            format(','.join(valid),
                                   self._override_name))

        return self.content


class SeqPartSearchOptsBase(object):

    @property
    def expr(self):
        if not isinstance(self.content, dict):  # pylint: disable=E1101
            return self.content  # pylint: disable=E1101

        return self.content.get('expr', '')  # pylint: disable=E1101

    @property
    def hint(self):
        if not isinstance(self.content, dict):  # pylint: disable=E1101
            return None

        return self.content.get('hint', '')  # pylint: disable=E1101

    @property
    def passthrough_results(self):
        if not isinstance(self.content, dict):  # pylint: disable=E1101
            return False

        return self.content.get('passthrough-results', False)  # noqa, pylint: disable=E1101


class YPropertySequencePart(YPropertySearchBase, SeqPartSearchOptsBase,
                            YPropertyOverrideBase):
    _override_keys = ['start', 'body', 'end']


class YPropertySearch(YPropertySearchBase, YPropertyMappedOverrideBase):
    _override_keys = ['search']
    _override_members = [YPropertySearchOpt, YPropertySearchConstraints,
                         YPropertySequencePart]

    @property
    def passthrough_results(self):
        """ Override the member to ensure we always return a bool. """
        if not isinstance(self.content, dict):
            return False

        return bool(self.content.get('passthrough-results', False))
