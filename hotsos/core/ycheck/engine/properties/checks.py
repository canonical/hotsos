from hotsos.core.log import log
from hotsos.core.searchtools import FileSearcher
from hotsos.core.ycheck.engine.properties.common import (
    cached_yproperty_attr,
    YPropertyBase,
    YPropertyOverrideBase,
    YDefsSection,
    add_to_property_catalog,
)


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
