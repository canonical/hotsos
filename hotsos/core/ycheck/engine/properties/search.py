import re
from functools import cached_property

from hotsos.core.log import log
from hotsos.core.search import (
    create_constraint,
    SearchDef,
    SequenceSearchDef,
    ExtraSearchConstraints,
)
from hotsos.core.ycheck.engine.properties.common import (
    YPropertyOverrideBase,
    YPropertyMappedOverrideBase,
)


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
            raise Exception("Invalid search constraints attributes found: "
                            f"{', '.join(invalid)}. "
                            "Valid options are: "
                            f"{', '.join(self.valid_attributes)}")
        return create_constraint(self.search_result_age_hours,
                                 self.min_hours_since_last_boot)


class YPropertySearchBase(YPropertyOverrideBase):

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
        count = len(results)
        results = ExtraSearchConstraints().apply(
                    results,
                    self.constraints.search_period_hours,
                    self.constraints.min_results)
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
            return None

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
            return None

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
        return None

    @property
    def sequence_passthrough_search(self):
        if not self.is_sequence_search or not self.passthrough_results:
            return None

        sdef = self.cache.sequence_passthrough_search
        if sdef:
            return sdef

        seq_start = self.start
        seq_end = self.end

        if not (self.passthrough_results and all([seq_start, seq_end])):
            return None

        # start and end required for core.analytics.LogEventStats
        start_tag = f"{self.unique_search_tag}-start"
        end_tag = f"{self.unique_search_tag}-end"
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
        else:
            sdef = self.sequence_search
            if sdef:
                log.debug("loading sequence search")
                searchobj.add(sdef, search_path,
                              allow_global_constraints=allow_constraints)
            else:
                sdef = self.sequence_passthrough_search
                if sdef:
                    log.debug("loading sequence passthrough searches")
                    for _sdef in sdef:
                        searchobj.add(
                            _sdef,
                            search_path,
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
            raise Exception(f"__str__ only valid for {','.join(valid)} "
                            f"(not {self._override_name})")

        return self.content


class SeqPartSearchOptsBase():

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
