from collections import UserDict

from hotsos.core.config import HotSOSConfig
from hotsos.core.ycheck.engine import (
    YDefsLoader,
    YDefsSection,
)
from hotsos.core.log import log
from hotsos.core.search import (
    FileSearcher,
    SearchConstraintSearchSince,
)
from hotsos.core.ycheck.engine.properties import search
from hotsos.core.ycheck.engine.properties.search import CommonTimestampMatcher


class SearchRegistryKeyConflict(Exception):
    def __init__(self, key, all_keys):
        self.key = key
        self.all_keys = all_keys

    def __str__(self):
        return (f"'{self.key}' key already exists in search registry. "
                "Available keys are:\n      - {}".
                format('\n      - '.join(self.all_keys)))


class SearchRegistryKeyNotFound(Exception):
    def __init__(self, key, all_keys):
        self.key = key
        self.all_keys = all_keys

    def __str__(self):
        return ("'{}' not found in search registry. Available keys are:"
                "\n      - {}".
                format(self.key, '\n      - '.join(self.all_keys)))


class GlobalSearcher(FileSearcher):
    """ Searcher with deferred execution and cached results. """

    def __init__(self):
        constraint = SearchConstraintSearchSince(
                                         ts_matcher_cls=CommonTimestampMatcher)
        self._results = None
        log.debug("creating new global searcher (%s)", self)
        super().__init__(constraint=constraint)

    @property
    def results(self):
        """
        Execute searches of first time called and cached results for future
        callers.
        """
        if self._results is not None:
            log.debug("using cached global searcher results")
            return self._results

        log.debug("fetching global searcher results")
        self._results = self.run()
        return self._results


class GlobalSearchRegistry(UserDict):
    """
    Maintains a set of properties e.g. dot paths to events or scenarios in yaml
    tree - that have been registered as having a search property, a global
    FileSearcher object and the results from running searches. This information
    is used to load searches from a set of events, run them and save their
    results for later retrieval. Search results are tagged with the names
    stored here.
    """

    def __init__(self):
        self._global_searcher = None
        super().__init__()

    def __setitem__(self, key, item):
        if key in self:
            raise SearchRegistryKeyConflict(key, list(self.data))

        log.debug("adding key=%s to search registry", key)
        super().__setitem__(key, item)

    def __getitem__(self, key):
        try:
            return super().__getitem__(key)
        except KeyError:
            raise SearchRegistryKeyNotFound(key, list(self.data)) from KeyError

    @property
    def searcher(self):
        if self._global_searcher is None:
            raise Exception("global searcher is not set but is expected to "
                            "be.")

        log.debug("using existing global searcher (%s)",
                  self._global_searcher)
        return self._global_searcher

    def reset(self):
        log.info("resetting global searcher registry")
        self.data = {}
        self._global_searcher = GlobalSearcher()

    @staticmethod
    def skip_filtered_item(event_path):
        e_filter = HotSOSConfig.event_filter
        if e_filter and event_path != e_filter:
            log.info("skipping event %s (filter=%s)", event_path, e_filter)
            return True

        return False

    @staticmethod
    def _find_search_prop_parent(items, path):
        """
        Walk down path until we hit the item containing the
        search property. We skip root/plugin name at start and
        ".search" at the end.

        @param item: YDefsSection object representing the entire tree of
                      items.
        @param path: item search property resolve path.
        """
        item = None
        for branch in path.split('.')[1:-1]:
            item = getattr(items if item is None else item, branch)

        return item

    @classmethod
    def _load_item_search(cls, item, searcher):
        """ Load search information from item into searcher.

        @param item: YDefsSection item object
        @param searcher: FileSearcher object
        """
        if len(item.input.paths) == 0:
            return

        allow_constraints = True
        if item.input.command:
            # don't apply constraints to command outputs
            allow_constraints = False

        # Add to registry in case it is needed by handlers e.g. for
        # sequence lookups.
        GLOBAL_SEARCH_REGISTRY[item.resolve_path] = {'search': item.search}

        for path in item.input.paths:
            log.debug("loading search for item %s (path=%s, tag=%s)",
                      item.resolve_path,
                      path, item.search.unique_search_tag)
            item.search.load_searcher(
                                searcher, path,
                                allow_constraints=allow_constraints)

    @classmethod
    def preload_event_searches(cls, group=None):
        """
        Find all items that have a search property and load their search into
        the global searcher.

        @param group: a group path can be provided to filter a subset of
                      items.
        """
        searcher = GLOBAL_SEARCH_REGISTRY.searcher
        if len(searcher.catalog) > 0:
            raise Exception("global searcher catalog is not empty "
                            "and must be reset before loading so as not "
                            "to include searches from a previous run.")

        log.debug("started loading (group=%s) searches into searcher "
                  "(%s)", group, searcher)

        search_props = set()
        plugin_defs = YDefsLoader('events', filter_path=group).plugin_defs
        items = YDefsSection(HotSOSConfig.plugin_name, plugin_defs or {})
        for prop in items.manager.properties.values():
            for item in prop:
                if not issubclass(item['cls'], search.YPropertySearch):
                    break

                search_props.add(item['path'])

        if len(search_props) == 0:
            log.debug("finished loading searches but no search "
                      "properties found")
            return

        log.debug("loading searches for %s items", len(search_props))
        for item_search_prop_path in search_props:
            item = cls._find_search_prop_parent(items, item_search_prop_path)
            if cls.skip_filtered_item(item.resolve_path):
                log.debug("skipping item %s", item.resolve_path)
                continue

            cls._load_item_search(item, searcher)

        log.debug("finished loading item searches into searcher "
                  "(registry has %s items)", len(GLOBAL_SEARCH_REGISTRY))


# Maintain a global searcher in module scope so that it is available to
# everyone. Upon the start of each plugin this should be cleared and populated
# then executed as early as possible so that results are ready to be used.
GLOBAL_SEARCH_REGISTRY = GlobalSearchRegistry()


class GlobalSearchContext(object):

    def __enter__(self):
        GLOBAL_SEARCH_REGISTRY.reset()

    def __exit__(self, *args, **kwargs):
        GLOBAL_SEARCH_REGISTRY.reset()
