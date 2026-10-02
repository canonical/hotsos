from functools import cached_property

from propertree.propertree2 import PTreeLogicalGrouping
from hotsos.core.log import log
from hotsos.core.ycheck.engine.properties.common import (
    YPropertyOverrideBase,
    YPropertyMappedOverrideBase,
    YDefsSection,
    YDefsContext,
)
from hotsos.core.ycheck.engine.properties.requires.requires import (
    YPropertyRequires
)
from hotsos.core.ycheck.engine.properties.search import (
    YPropertySearch,
)
from hotsos.core.ycheck.engine.properties.inputdef import YPropertyInput
from hotsos.core.exceptions import NotYetInitializedError, PreconditionError


class CheckBase():
    """ Base class used with checks implementations. """
    def fetch_item_result(self, item):
        """ Evaluate a single check item and return its boolean result. """
        log.debug("%s: fetch_item_result() %s", self.__class__.__name__,
                  item.__class__.__name__)
        check = self.context['check']  # pylint: disable=E1101
        if isinstance(item, YPropertySearch):
            _results = check.search_results
            check.set_search_cache_info(_results)
            if not _results:
                log.debug("check %s search has no matches so result=False",
                          check.name)
                return False

            return True

        if isinstance(item, YPropertyRequires):
            result = item.result
            if result or check.cache.requires is None:
                check.cache.set('requires', item.cache)

            return result

        return item.result


class CheckLogicalGrouping(CheckBase, PTreeLogicalGrouping):
    """ Logical grouping for check property. """
    override_autoregister = False

    @property
    def result(self):
        try:
            return super().result
        except Exception as exc:
            log.exception("%s failed with exception: %s",
                          self.__class__.__name__, exc)
            raise


class YPropertyCheck(CheckBase, YPropertyMappedOverrideBase):
    """ Check property. Provides support for defining a check. """
    override_keys = ['check']
    override_members = [YPropertyRequires, YPropertySearch, YPropertyInput]
    override_logical_grouping_type = CheckLogicalGrouping

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # These are set later on before the check is used
        self._initialised = False
        self.check_name = None

    @property
    def search_results(self):
        """
        Retrieve the global searchkit.SearchResultsCollection from this
        property's context. We filter results using our tag and apply any
        search constraints requested.
        """
        global_results = self.context.global_searcher.results
        if global_results is None:
            raise PreconditionError("no search results provided to check "
                                    f"'{self.check_name}'")

        tag = self.search.unique_search_tag  # pylint: disable=E1101

        # first get simple search results
        results = global_results.find_by_tag(tag)
        log.debug("check %s has %s simple search results with tag %s",
                  self.check_name, len(results), tag)
        if results:
            results = self.search.apply_extra_constraints(results)  # noqa, pylint: disable=no-member

        search_info = self.context.global_searcher[tag]
        sequence_search = search_info['sequence_search']
        if sequence_search is None:
            return results

        # Now try for sequence search results
        sections = global_results.find_sequence_by_tag(tag)
        log.debug("check %s has %s sequence search results with tag %s",
                  self.check_name, len(sections), tag)
        if not sections:
            return results

        filtered = self._filter_sequence_sections(sections, sequence_search)
        # Only include section start results since the length of the returned
        # list is treated as the number of search matches.
        results.extend(self._get_sequence_start_results(
                            filtered, sequence_search.start_tag))
        return results

    @staticmethod
    def _get_section_start_end_tuple(sequence_search, section):
        start = end = None
        for result in section:
            if result.tag == sequence_search.start_tag:
                start = result
            elif result.tag == sequence_search.end_tag:
                end = result

        return (start, end)

    @staticmethod
    def _get_sequence_start_results(results, start_tag):
        """
        Return all the section start results for a given set of sequence
        results.
        """
        return [r for r in results if r.tag == start_tag]

    def _filter_sequence_sections(self, sections, sequence_search):
        """
        Apply extra search constraints to matched sequence sections.

        A section is guaranteed to be complete (a full match) so it is
        represented by its start result. Constraints are applied in two
        stages: first to the individual results in each matched section
        (typically the start result and optional end result), and then across
        the collected set of section start results. This means aggregate
        constraints such as min-results are evaluated against section
        starts only.

        @param sections: dict of section id to list of SearchResult objects.
        @param sequence_search: searchkit SequenceSearchDef for these results.
        @return: list of remaining sequence search results
        """
        total_results = []
        log.debug("applying extra constraints to sequence %s results",
                  sequence_search.id)
        for results in sections.values():
            start, end = self._get_section_start_end_tuple(sequence_search,
                                                           results)
            # NOTE: remember end is optional
            if start is None:
                continue

            results = [start] if end is None else [start, end]
            before = len(results)
            # Apply constraints to this sequence section. Note that in
            # reality this is only applying search-period-hours so that
            # if a window is provided both start and end fall within
            # that window.
            results = self.search.apply_extra_constraints(  # noqa pylint: disable=no-member
                        results, skip_min_results=True)
            # If length of results is the same as before then we are good
            # to use the sequence.
            if len(results) == before:
                total_results.extend(results)

        # Now apply all/any constraints to the full set of start results.
        # Note that for search-period-hours we are allowing this to
        # be applied to start results only which means that technically
        # speaking the end result could be outside of that window.
        starts = self._get_sequence_start_results(total_results,
                                                  sequence_search.start_tag)
        before = len(starts)
        results = self.search.apply_extra_constraints(starts)  # noqa, pylint: disable=no-member
        if not results:
            total_results = []
        elif before != len(results):
            remaining = [r.section_id for r in results]
            # Filter start and end (if available) for remaining results
            total_results = [r for r in total_results
                             if r.section_id in remaining]

        remaining = (len({r.section_id for r in total_results})
                     if total_results else 0)
        log.debug("%s sequence(s) remain after filtering", remaining)
        return total_results

    @property
    def name(self):
        """ Name of the check once initialised, else None. """
        if self._initialised:
            return self.check_name

        return None

    def initialise(self, name):
        """ Mark the check as initialised and record its name. """
        self._initialised = True
        self.check_name = name

    def set_search_cache_info(self, results):
        """
        Set information in check cache so that it can be retrieved using
        PropertyCacheRefResolver. This information is typically used
        when creating messages as part of raising issues.

        IMPORTANT: do not cache search results themselves as this can consume a
                   lot of memory.

        @param results: search results for query in search property found in
                        this check.
        """
        # this is so that the information can be accessed like:
        # @checks.<checkname>.search.<setting>
        self.cache.set('search', self.search.cache)  # pylint: disable=E1101
        self.search.cache.set('num_results', len(results))  # noqa, pylint: disable=E1101
        if not results:
            return

        # Saves a list of files that contained search results.
        sources = set(r.source_id for r in results)
        searcher = self.context.global_searcher.searcher
        files = [searcher.resolve_source_id(s) for s in sources]
        self.search.cache.set('files', files)  # pylint: disable=E1101

    @cached_property
    def result(self):
        """ Boolean result of running this check. """
        # pylint: disable=duplicate-code
        try:
            # Pass this object down to descendants so that they have access to
            # its cache etc. Note this is modifying global context but since
            # checks are processed sequentially this is fine.
            self.context['check'] = self
            log.debug("executing check %s", self.name)
            results = []
            stop_executon = False
            for member in self.members:
                for item in member:
                    # Ignore these here as they are used by search properties.
                    if isinstance(item, YPropertyInput):
                        continue

                    result = self.fetch_item_result(item)
                    results.append(result)
                    if CheckLogicalGrouping.is_exit_condition_met('and',
                                                                  result):
                        stop_executon = True
                        break

                if stop_executon:
                    break

            result = all(results)
            log.debug("check %s (%s) result=%s", self.name, results, result)
            return result
        except Exception:
            log.exception("something went wrong while executing check %s",
                          self.name)
            raise


class YPropertyChecks(YPropertyOverrideBase):
    """ Checks property. Provides support for defining scenario checks. """
    override_keys = ['checks']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._initialised = False
        self.check_context = YDefsContext()

    def initialise(self, local_vardefs):
        """
        Perform initialisation tasks for this set of checks.

        * create context containing vardefs for each check
        * pre-load searches from all/any checks and get results. This needs to
          be done before check results are consumed.

        @param local_vardefs: YPropertyVars object containing all variables
                              defined in the context of these checks and that
                              we wil pass on the all check def and properties.
        """
        self.check_context.update({'vars': local_vardefs})
        self._initialised = True

    @cached_property
    def _checks(self):
        log.debug("parsing checks section")
        if not self._initialised:
            raise NotYetInitializedError("checks not yet initialised")

        resolved = []
        for name, content in self.content.items():
            s = YDefsSection(self.override_name, {name: {'check': content}},
                             override_handlers=self.root.override_handlers,
                             resolve_path=self.override_path,
                             context=self.check_context)
            for c in s.leaf_sections:
                c.check.initialise(c.name)
                resolved.append(c.check)

        return resolved

    def __iter__(self):
        log.debug("iterating over checks")
        for c in self._checks:
            log.debug("returning check %s", c.name)
            yield c
