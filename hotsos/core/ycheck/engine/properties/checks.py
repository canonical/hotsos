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


class CheckBase():

    def fetch_item_result(self, item):
        log.debug("%s: fetch_item_result() %s", self.__class__.__name__,
                  item.__class__.__name__)
        check = self.context['check']  # pylint: disable=E1101
        if isinstance(item, YPropertySearch):
            _results = check._search_results
            check._set_search_cache_info(_results)
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
    _override_autoregister = False

    @property
    def result(self):
        try:
            return super().result
        except Exception as exc:
            log.exception("%s failed with exception: %s",
                          self.__class__.__name__, exc)
            raise


class YPropertyCheck(CheckBase, YPropertyMappedOverrideBase):
    _override_keys = ['check']
    _override_members = [YPropertyRequires, YPropertySearch, YPropertyInput]
    _override_logical_grouping_type = CheckLogicalGrouping

    @property
    def _search_results(self):
        """
        Retrieve the global searchkit.SearchResultsCollection from this
        property's context. We filter results using our tag and apply any
        search constraints requested.
        """
        global_results = self.context.global_searcher.results
        if global_results is None:
            raise Exception("no search results provided to check '{}'".
                            format(self.check_name))  # pylint: disable=E1101

        tag = self.search.unique_search_tag  # pylint: disable=E1101

        # first get simple search results
        simple_results = global_results.find_by_tag(tag)
        log.debug("check %s has %s simple search results with tag %s",
                  self.check_name, len(simple_results), tag)  # noqa, pylint: disable=E1101
        results = self.search.apply_extra_constraints(simple_results)  # noqa, pylint: disable=E1101

        search_info = self.context.global_searcher[tag]
        if search_info['sequence_search'] is None:
            return results

        # Not try for sequence search results
        sections = global_results.find_sequence_by_tag(tag).values()
        log.debug("check %s has %s sequence search results with tag %s",
                  self.check_name, len(sections), tag)  # pylint: disable=E1101
        if not sections:
            return results

        # Use the result of the first section start as the final
        # result. This is enough for now because the section is guaranteed
        # to be complete i.e. a full match and the result is ultimately
        # True/False based on whether or not a result was found.
        for result in list(sections)[0]:
            if result.tag == search_info['sequence_search'].start_tag:
                # NOTE: we don't yet support applying extra constraints here
                results.append(result)
                break

        return results

    @property
    def name(self):
        if hasattr(self, 'check_name'):
            return getattr(self, 'check_name')

    def _set_search_cache_info(self, results):
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
    _override_keys = ['checks']

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
            raise Exception("checks not yet initialised")

        resolved = []
        for name, content in self.content.items():
            s = YDefsSection(self._override_name, {name: {'check': content}},
                             override_handlers=self.root.override_handlers,
                             resolve_path=self._override_path,
                             context=self.check_context)
            for c in s.leaf_sections:
                c.check.check_name = c.name
                resolved.append(c.check)

        return resolved

    def __iter__(self):
        log.debug("iterating over checks")
        for c in self._checks:
            log.debug("returning check %s", c.name)
            yield c
