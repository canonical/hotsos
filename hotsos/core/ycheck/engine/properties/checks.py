from hotsos.core.config import HotSOSConfig
from hotsos.core.log import log
from hotsos.core.search import (
    FileSearcher,
    SearchConstraintSearchSince,
)
from hotsos.core.ycheck.engine.properties.common import (
    cached_yproperty_attr,
    YPropertyOverrideBase,
    YPropertyMappedOverrideBase,
    YDefsSection,
    add_to_property_catalog,
    YDefsContext,
)
from hotsos.core.ycheck.engine.properties.requires.requires import (
    YPropertyRequires
)
from hotsos.core.ycheck.engine.properties.search import (
    YPropertySearch,
    COMMON_LOG_DATETIME_EXPRS,
)
from hotsos.core.ycheck.engine.properties.input import YPropertyInput

MAX_CACHED_SEARCH_RESULTS = 100


@add_to_property_catalog
class YPropertyCheck(YPropertyMappedOverrideBase):

    @property
    def first_search_result(self):
        return self.cache.first_search_result

    @property
    def _search_results(self):
        """
        Retrieve the global searchkit.SearchResultsCollection from this
        property's context. We filter results using our tag and apply any
        search constraints requested.
        """
        global_results = self.context.search_results
        if global_results is not None:
            tag = self.search.unique_search_tag
            _results = global_results.find_by_tag(tag)
            log.debug("check %s has %s search results with tag %s",
                      self.check_name, len(_results), tag)
            ret = self.search.apply_constraints(_results)
            if ret:
                self.cache.set('first_search_result', ret[0])

            return ret

        raise Exception("no search results provided to check '{}'".
                        format(self.check_name))

    @classmethod
    def _override_keys(cls):
        return ['check']

    @classmethod
    def _override_mapped_member_types(cls):
        return [YPropertyRequires, YPropertySearch, YPropertyInput]

    @property
    def name(self):
        if hasattr(self, 'check_name'):
            return getattr(self, 'check_name')

    def _set_search_cache_info(self, results):
        """
        Set information in the local property cache that can be retrieved
        using PropertyCacheRefResolver. This information is typically used
        when creating messages as part of raising issues.

        @param results: search results for query in search property found in
                        this check.
        """
        self.search.cache.set('num_results', len(results))
        if not results:
            return

        # The following aggregates results by group/index and stores in
        # the property cache to make them accessible via
        # PropertyCacheRefResolver.
        # NOTE: we cap at MAX_CACHED_SEARCH_RESULTS results to save memory
        results_by_idx = {}
        for i, result in enumerate(results):
            if i > MAX_CACHED_SEARCH_RESULTS:
                break

            for idx, value in enumerate(result):
                if idx not in results_by_idx:
                    results_by_idx[idx] = set()

                results_by_idx[idx].add(value)

        for idx in results_by_idx:
            self.search.cache.set('results_group_{}'.format(idx),
                                  list(results_by_idx[idx]))

        # Saves a list of files that contained search results.
        sources = set([r.source_id for r in results])
        files = [self.context.search_obj.resolve_source_id(s) for s in sources]
        self.search.cache.set('files', files)

        # make it available from this property
        self.cache.set('search', self.search.cache)

    def _result(self):
        if self.search:
            _results = self._search_results
            self._set_search_cache_info(_results)
            if not _results:
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

    @cached_yproperty_attr
    def result(self):
        log.debug("executing check %s", self.name)
        result = self._result()
        log.debug("check %s result=%s", self.name, result)
        return result


@add_to_property_catalog
class YPropertyChecks(YPropertyOverrideBase):

    @classmethod
    def _override_keys(cls):
        return ['checks']

    def initialise(self, vars, input):
        """
        Perform initialisation tasks for this set of checks.

        * create context containing vars for each check
        * pre-load searches from all/any checks and get results. This needs to
          be done before check results are consumed.
        """
        self.check_context = YDefsContext({'vars': vars})

        log.debug("loading checks searchdefs into filesearcher")

        if HotSOSConfig.use_all_logs:
            hours = 24 * HotSOSConfig.max_logrotate_depth
        else:
            hours = 24

        c = SearchConstraintSearchSince(exprs=COMMON_LOG_DATETIME_EXPRS,
                                        hours=hours)
        s = FileSearcher(constraint=c)
        # first load all the search definitions into the searcher
        for c in self._checks:
            if c.search:
                # local takes precedence over global
                _input = c.input or input
                if _input.command:
                    # don't apply constraints to command outputs
                    allow_constraints = False
                else:
                    allow_constraints = True

                for path in _input.paths:
                    log.debug("loading searches for check %s", c.check_name)
                    c.search.load_searcher(s, path,
                                           allow_constraints=allow_constraints)

        # provide results to each check object using global context
        log.debug("executing check searches")
        self.check_context.search_obj = s
        self.check_context.search_results = s.run()

    @cached_yproperty_attr
    def _checks(self):
        log.debug("parsing checks section")
        if not hasattr(self, 'check_context'):
            raise Exception("checks not yet initialised")

        resolved = []
        for name, content in self.content.items():
            s = YDefsSection(self._override_name, {name: {'check': content}},
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
