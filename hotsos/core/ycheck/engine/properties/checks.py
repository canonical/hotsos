from hotsos.core.log import log
from hotsos.core.searchtools import FileSearcher
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
from hotsos.core.ycheck.engine.properties.search import YPropertySearch
from hotsos.core.ycheck.engine.properties.input import YPropertyInput


@add_to_property_catalog
class YPropertyCheck(YPropertyMappedOverrideBase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._search_results = None

    @property
    def search_results(self):
        if self.search and self._search_results is not None:
            return self._search_results

        raise Exception("search results not set")

    @search_results.setter
    def search_results(self, value):
        self._search_results = value

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
        s = FileSearcher()
        # first load all the search definitions into the searcher
        with_searches = []
        for c in self._checks:
            if c.search:
                with_searches.append(c)
                # local takes precedence over global
                _input = c.input or input
                for path in _input.paths:
                    c.search.load_searcher(s, path)

        log.debug("executing check searches")
        results = s.search()

        # now extract each checks's set of results
        log.debug("extracting check search results")
        for c in with_searches:
            tag = c.search.unique_search_tag
            c.search_results = results.find_by_tag(tag)

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
