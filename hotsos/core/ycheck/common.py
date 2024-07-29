import abc
import contextlib
from collections import UserDict

from hotsos.core.log import log
from hotsos.core.search import (
    FileSearcher,
    SearchConstraintSearchSince,
)
from hotsos.core.config import HotSOSConfig
from hotsos.core.search import CommonTimestampMatcher
from hotsos.core.exceptions import NameNotSetError


class SearchRegistryError(Exception):
    """ Generic search registry exception. """
    def __init__(self, msg):
        self.msg = msg


class SearchRegistryKeyConflict(Exception):
    """ Search registry key conflict exception.

    This is raised when an attempt is made to register a new item in the
    registry using a key for which an item has already been registered.
    """
    def __init__(self, key, all_keys):
        self.key = key
        self.all_keys = all_keys

    def __str__(self):
        return (f"'{self.key}' key already exists in search registry. "  # noqa, pylint: disable=consider-using-f-string
                "Available keys are:\n      - {}".
                format('\n      - '.join(self.all_keys)))


class SearchRegistryKeyNotFound(Exception):
    """ Search registry key not found exception.

    This is raised when an attempt is made to retrieve an item from the
    registry using a key for which an item does not exist.
    """
    def __init__(self, key, all_keys):
        self.key = key
        self.all_keys = all_keys

    def __str__(self):
        return (f"'{self.key}' not found in search registry. Available keys "  # noqa, pylint: disable=consider-using-f-string
                "are:\n      - {}".
                format('\n      - '.join(self.all_keys)))


SEARCHES_TO_BE_REGISTERED = []


class GlobalSearcher(contextlib.AbstractContextManager, UserDict):
    """
    A shared searcher used to load searches from as many sources as
    possible prior to execution so as to minimise the amount of times we have
    to walk the same files. The is particularly useful for YAML checks
    i.e. events and scenarios that contain many search properties.

    Search properties are registered using their resolve path i.e. to the
    parent events or scenarios check in the yaml tree that contains them.
    Entries must be unique. Once all searches are loaded they are executed and
    their results are made available to anyone who wants them. Results are
    accessed using the yaml dot path used to register the search.
    """

    def __init__(self):
        constraint = SearchConstraintSearchSince(
                                         ts_matcher_cls=CommonTimestampMatcher)
        self._loaded_searches = []
        self._results = None
        self._searcher = FileSearcher(constraint=constraint)
        log.debug("creating new global searcher (%s)", self._searcher)
        super().__init__()

    def __exit__(self, *exc_details):
        pass

    def __setitem__(self, key, item):
        """ Register a new search.

        @param key: search property YAML resolve path.
        @param item: search property object.
        """
        if key in self:
            raise SearchRegistryKeyConflict(key, list(self.data))

        log.debug("adding key=%s to search registry", key)
        super().__setitem__(key, item)

    def __getitem__(self, key):
        """ Access a search entry.

        @param key: search property YAML resolve path.
        """
        try:
            return super().__getitem__(key)
        except KeyError:
            raise SearchRegistryKeyNotFound(key, list(self.data)) from KeyError

    def set_loaded(self, label):
        """ After loading a set of searches it is useful to set a label as an
        easy to later check if they have been loaded since this can only be
        done once per label.

        @param label: string label to mark a set of searches as registered.
        """
        if label in self._loaded_searches:
            raise SearchRegistryError("Search Registry has already been "
                                      f"loaded by label={label}")

        self._loaded_searches.append(label)

    def is_loaded(self, label):
        return label in self._loaded_searches

    @property
    def searcher(self):
        return self._searcher

    @property
    def results(self):
        """
        Execute searches if first time called and use cached results for
        future calls.
        """
        if self._results is not None:
            log.debug("using cached global searcher results")
            return self._results

        for s in SEARCHES_TO_BE_REGISTERED:
            if not s().validate(HotSOSConfig.plugin_name):
                continue

            self.add_search(s.simple_search(), s.sequence_search(),
                            s.passthrough_results, s.paths())

        log.debug("fetching global searcher results")
        self._results = self.searcher.run()
        return self._results

    def add_search(self, simple_search, sequence_search, passthrough_results,
                   paths):
        """
        Register a new search in the registry and add it to the global
        searcher.

        @param simple_search: SearchDef object.
        @param sequence_search: SequenceSearchDef object.
        @param passthrough_results: True or False.
        @param paths: list of one or more paths.
        """
        if simple_search is not None:
            searchdef = simple_search
        else:
            searchdef = sequence_search

        tag = searchdef.tag
        self[tag] = {'search_tag': tag,
                     'passthrough_results': passthrough_results,
                     'simple_search': simple_search,
                     'sequence_search': sequence_search}

        for path in paths:
            log.debug("loading search (tag=%s, input_path=%s)", tag,
                      path)
            self.searcher.add(searchdef, path,
                              allow_global_constraints=True)

    def run(self):
        _ = self.results


class GlobalSearcherPreloaderBase():
    """ Used by plugin components to preload the global searcher. """

    @staticmethod
    def _find_search_prop_parent(items, path):
        """
        Walk down path until we hit the item containing the property. We skip
        root/plugin name at start and ".<property>" at the end.

        @param items: YDefsSection object representing the entire tree of
                      properties.
        @param path: property resolve path.
        """
        item = None
        for branch in path.split('.')[1:-1]:
            item = getattr(items if item is None else item, branch)

        return item

    @staticmethod
    def _load_item_search(global_searcher, search_property, search_input):
        """ Load search property information into searcher.

        @param global_searcher: GlobalSearcher object
        @param search_property: YPropertySearch object
        @param search_input: YPropertyInput object
        """
        if len(search_input.paths) == 0:
            return

        allow_constraints = True
        if search_input.command:
            # don't apply constraints to command outputs
            allow_constraints = False

        # Add to registry in case it is needed by handlers e.g. for
        # sequence lookups.
        # IMPORTANT: do not store reference to ycheck property itself.
        tag = search_property.unique_search_tag
        global_searcher[tag] = {'search_tag': tag,
                                'passthrough_results':
                                    search_property.passthrough_results,
                                'simple_search':
                                    search_property.simple_search,
                                'sequence_search':
                                    search_property.sequence_search}

        for path in search_input.paths:
            log.debug("loading search (tag=%s, input_path=%s, "
                      "resolve_path=%s)", tag, path,
                      search_property.override_path)
            search_property.load_searcher(global_searcher.searcher, path,
                                          allow_constraints=allow_constraints)

    @staticmethod
    @abc.abstractmethod
    def skip_filtered(path):
        pass

    @abc.abstractmethod
    def preload_searches(self, global_searcher):
        pass


class GlobalSearcherAutoRegisterMeta(type):
    """ Add to list of searches to be registered at runtime. """

    def __init__(cls, _name, _mro, _members):
        if cls.unique_search_tag is None:
            return

        SEARCHES_TO_BE_REGISTERED.append(cls)


class GlobalSearcherAutoRegisterBase(metaclass=GlobalSearcherAutoRegisterMeta):
    """
    Generic interface for loading search definitions into the global searcher.
    The attributes of this class are intentionally similar to those of
    hotsos.core.ycheck.engine.properties.search so as to be able to give them
    equivalent meaning but this is really intended for use by code that wants
    to perform searches but that is not using YPropertySearch (i.e. not event
    or scenario yaml).
    """
    # This must be set to the same value as used by corresponding
    # implementation of PluginPartBase.plugin_name.
    plugin_name = None
    # This will be used to register and lookup the search in the registry and
    # must not conflict with any existing tags.
    unique_search_tag = None

    def validate(self, plugin_name):
        """
        This is used to ensure that we only load searches applicable to the
        plugin currently being executed.

        Returns True if we are running the context of the plugin to which this
        search belongs.
        """
        if self.plugin_name is None:
            raise NameNotSetError(
                f"{self.__class__.__name__}.plugin_name must be set "
                "to the name of the plugin in which it will run "
                f"(currently={self.plugin_name})")

        return plugin_name == self.plugin_name

    @property
    def passthrough_results(self):
        return False

    @classmethod
    def simple_search(cls):
        """ Returns SearchDef object.

        NOTE: either this or sequence_search must be implemented but not both.
        """

    @classmethod
    def sequence_search(cls):
        """ Returns a SequenceSearchDef object.

        NOTE: either this or simple_search must be implemented but not both.
        """

    @classmethod
    @abc.abstractmethod
    def paths(cls):
        """ Returns a list of one or more paths to search. """
