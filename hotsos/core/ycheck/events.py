import abc
from functools import cached_property
from collections import UserDict

from hotsos.core.config import HotSOSConfig
from hotsos.core.log import log
from hotsos.core.search import (
    FileSearcher,
    SearchConstraintSearchSince,
)
from hotsos.core.utils import sorted_dict
from hotsos.core.ycheck.engine import (
    YDefsLoader,
    YHandlerBase,
    YDefsSection,
)
from hotsos.core.ycheck.engine.properties import search
from hotsos.core.ycheck.engine.properties.search import CommonTimestampMatcher


CALLBACKS = {}


class EventCallbackNameConflict(Exception):
    pass


class EventCallbackNotFound(Exception):
    pass


class EventsSearchRegistryKeyNotFound(Exception):
    def __init__(self, key, all_keys):
        self.key = key
        self.all_keys = all_keys

    def __str__(self):
        return ("'{}' not found in event registry. Available keys are:"
                "\n      - {}".
                format(self.key, '\n      - '.join(self.all_keys)))


class EventCallbackMeta(type):

    def __init__(cls, _name, _mro, members):
        event_group = members.get('event_group')
        if event_group is None:
            return

        for event in members['event_names']:
            event = '{}.{}'.format(event_group, event)
            if event in CALLBACKS:
                msg = "event callback already registered: {}".format(event)
                raise EventCallbackNameConflict(msg)

            CALLBACKS[event] = cls


class EventCheckResult(object):
    """ This is passed to an event check callback when matches are found """

    def __init__(self, defs_section, defs_event, search_results, search_tag,
                 searcher, sequence_def=None):
        """
        @param defs_section: section name from yaml
        @param defs_event: event label/name from yaml
        @param search_results: searchkit.SearchResultsCollection
        @param search_tag: unique tag used to identify the results
        @param searcher: global FileSearcher object
        @param sequence_def: if set the search results are from a
                            searchkit.SequenceSearchDef and are therefore
                            grouped as sections of results rather than a single
                            set of results.
        """
        self.section = defs_section
        self.name = defs_event
        self.search_tag = search_tag
        self.results = search_results
        self.searcher = searcher
        self.sequence_def = sequence_def


class EventProcessingUtils(object):

    @classmethod
    def categorise_events(cls, event, results=None, key_by_date=True,
                          include_time=False, squash_if_none_keys=False,
                          max_results_per_date=None):
        """
        Provides a generic way to categorise events. The default is to group
        events by key which is typically some kind of resource id or event
        label, beneath which the events are grouped by date. If a time value is
        also available, events will be grouped by time beneath their date. It
        may sometimes be useful to group events by date at the top level which
        is also supported here.

        The date, time and key values are extracted from each event search
        result and  are expected to be at indexes 1, 2 and 3 respectively. If
        the search result only has two groups it is assumed that the second is
        "key" i.e. no time is given. If the results argument is provided, this
        will be used instead of event.results.

        @param event: EventCheckResult object
        @param results: optional list of results where each item is a dict with
                        keys 'date', 'key' and optionally 'time'.
        @param key_by_date: by default results are categorised by date but in
                            situations where a small number of event types
                            (keys) are spread across many dates/times it might
                            make sense to categorise by event type.
        @param include_time: If true events will be categorised by time beneath
                             date to provide an extra level of granularity.
        @param squash_if_none_keys: If true and any key is found to be None
                                    (perhaps because a regex pattern did not
                                    match properly) the results for each date
                                    will be squashed to a number/count of
                                    events.
        @param max_results_per_date: an integer such that if key_by_date is
                                     True this will pick the top N entries
                                     with the highest count.
        """
        info = {}
        squash = False
        if results is None:
            # use raw
            results = []
            _fail_count = 0
            for r in event.results:
                # the search expression used much ensure that tese are#
                # available in order for this to work.
                if len(r) > 2:
                    if not set([None, None, None]).intersection([r.get(1),
                                                                 r.get(2),
                                                                 r.get(3)]):
                        results.append({'date': r.get(1), 'time': r.get(2),
                                        'key': r.get(3)})
                    else:
                        _fail_count += 1
                elif len(r) < 1:
                    msg = ("result (tag={}) does not have enough groups "
                           "(min 1) to be categorised - aborting".
                           format(r.tag))
                    raise Exception(msg)
                else:
                    if len(r) < 2:
                        # results with just a date will have None for the key
                        log.debug("result (tag=%s) has just one group which "
                                  "is assumed to be a date and using key=None",
                                  r.tag)

                    results.append({'date': r.get(1), 'key': r.get(2)})

            if _fail_count:
                log.info("event '%s' has %s results with insufficient fields",
                         event.name, _fail_count)

        for r in results:
            if r['key'] is None and squash_if_none_keys:
                squash = True

            ts_time = r.get('time')
            if key_by_date:
                key = r['date']
                value = r['key']
            else:
                key = r['key']
                value = r['date']

            if key not in info:
                info[key] = {}

            if value not in info[key]:
                if ts_time is not None and include_time:
                    info[key][value] = {}
                else:
                    info[key][value] = 0

            if ts_time is not None and include_time:
                if ts_time not in info[key][value]:
                    info[key][value][ts_time] = 1
                else:
                    info[key][value][ts_time] += 1
            else:
                info[key][value] += 1

        if info:
            if squash:
                squashed = {}
                for k, v in info.items():
                    if k not in squashed:
                        squashed[k] = 0

                    for count in v.values():
                        squashed[k] += count

                info = squashed

            # If not using date as key we need to sort the values so that they
            # will have the same order as if they were sorted by date key.
            if not key_by_date:
                for key in info:
                    info[key] = sorted_dict(info[key])
            elif not include_time:
                # sort by value i.e. tally/count
                for key, value in info.items():
                    if not isinstance(value, dict):
                        break

                    info[key] = sorted_dict(value, key=lambda e: e[1],
                                            reverse=True)

            results = sorted_dict(info, reverse=not key_by_date)
            if not (key_by_date and max_results_per_date):
                return results

            shortened = {}
            for date, entries in results.items():
                if len(entries) <= max_results_per_date:
                    shortened[date] = entries
                    continue

                top_n = dict(sorted(entries.items(),
                                    key=lambda e: e[1],
                                    reverse=True)[:max_results_per_date])
                shortened[date] = {'total': len(entries),
                                   "top{}".format(max_results_per_date): top_n}

            return shortened


class EventCallbackBase(EventProcessingUtils, metaclass=EventCallbackMeta):
    # All implementations must set these and event_group must match that used
    # in the handler.
    event_group = None
    event_names = []

    @abc.abstractmethod
    def __call__(self):
        """ Callback method. """


class EventsSearchRegistry(UserDict):
    """
    Maintains a set of event names - dot paths to events in yaml tree - that
    have been registered as having a search property, a global FileSearcher
    object and the results from running searches. This information is used
    to load searches from a set of events, run them and save their results for
    later retrieval. Search results are tagged with the names stored here.

    It might be the case that an event handler wants to use its own
    FileSearcher in which case this supports setting a _custom_searcher that
    is cleared when the global searcher is accessed.
    """

    def __init__(self):
        self._global_searcher = None
        self._custom_searcher = None
        self._global_searcher_results = None
        super().__init__()

    def __getitem__(self, key):
        try:
            return super().__getitem__(key)
        except KeyError:
            raise EventsSearchRegistryKeyNotFound(
                                                key,
                                                list(self.data)) from KeyError

    def get_global_searcher_results(self):
        if self._global_searcher is None:
            raise Exception("registry global searcher is None")

        if self._global_searcher_results is not None:
            log.debug("using cached global event search results")
            return self._global_searcher_results

        log.debug("fetching global event search results")
        self._global_searcher_results = self._global_searcher.run()
        return self._global_searcher_results

    def get_global_searcher(self, allow_create=False):
        if self._global_searcher:
            log.debug("using existing global searcher (%s)",
                      self._global_searcher)
            return self._global_searcher

        if not allow_create:
            raise Exception("global events searcher is not set but is "
                            "expected to be.")

        self._custom_searcher = None
        constraint = SearchConstraintSearchSince(
                                         ts_matcher_cls=CommonTimestampMatcher)
        searcher = FileSearcher(constraint=constraint)
        self._global_searcher = searcher
        self._global_searcher_results = None
        log.debug("creating new global searcher (%s)", searcher)
        return searcher

    def set_custom_searcher(self, searcher):
        self._custom_searcher = searcher

    @property
    def current_searcher(self):
        return self._custom_searcher or self.get_global_searcher()

    def _reset_searchers(self):
        self._global_searcher = None
        self._custom_searcher = None
        self._global_searcher_results = None

    def reset(self, create_new_global_searcher=False):
        log.info("resetting events global registry")
        self._reset_searchers()
        self.data = {}
        if create_new_global_searcher:
            self.get_global_searcher(allow_create=True)


class EventsBase(object):
    # IMPORTANT: this state is maintained at class level so that all
    # implementations can share it. It is therefore crucial that state is reset
    # before loading a new set of event searches.
    search_registry = EventsSearchRegistry()

    @staticmethod
    def meets_requirements(event):
        """
        If an event or group has a requirements property it must return True
        for the events to be executed.
        """
        if HotSOSConfig.force_mode:
            return True

        if event.requires and not event.requires.result:
            log.debug("event '%s' pre-requisites not met - "
                      "skipping", event.name)
            return False

        return True

    @staticmethod
    def skip_filtered_event(event_path):
        """
        Apply event filter if provided.
        """
        e_filter = HotSOSConfig.event_filter
        if e_filter and event_path != e_filter:
            log.info("skipping event %s (filter=%s)", event_path, e_filter)
            return True

        return False

    @staticmethod
    def get_defs(group=None):
        """
        Load the event definitions for the current plugin. By default all are
        loaded and if a group path is provided, only events that are part of
        that group are included.

        @param group: a group path can be provided to include events part of a
                      group.
        """
        log.debug("loading event defs (group=%s)", group)
        plugin_defs = YDefsLoader('events').plugin_defs
        if not plugin_defs:
            return {}

        if not group:
            return plugin_defs

        # Exclude events that are not part of the group.
        groups = group.split('.')
        for i, subgroup in enumerate(groups):
            if i == 0:
                plugin_defs = {subgroup: plugin_defs[subgroup]}
            else:
                prev = groups[i - 1]
                plugin_defs[prev] = {subgroup: plugin_defs[prev][subgroup]}

        return plugin_defs

    @staticmethod
    def _get_event_from_path(events, path):
        """
        Walk down path until we hit the event containing the
        search property. We skip root/plugin name at start and
        ".search" at the end.

        @param event: YDefsSection object representing the entire tree of
                      events.
        @param path: event search property resolve path.
        """
        event = None
        for branch in path.split('.')[1:-1]:
            if event is None:
                event = getattr(events, branch)
            else:
                event = getattr(event, branch)

        return event

    @classmethod
    def _load_event_search(cls, event, searcher):
        """ Load search information from event into searcher.

        @param event: YDefsSection event object
        @param searcher: FileSearcher object
        """
        allow_constraints = True
        if event.input.command:
            # don't apply constraints to command outputs
            allow_constraints = False

        for path in event.input.paths:
            log.debug("loading search for event %s (path=%s, tag=%s)",
                      event.resolve_path,
                      path, event.search.unique_search_tag)
            # Add to registry in case it is needed by handlers e.g. for
            # sequence lookups.
            cls.search_registry[event.resolve_path] = {'search':
                                                       event.search}
            event.search.load_searcher(
                                searcher, path,
                                allow_constraints=allow_constraints)

    @classmethod
    def load_searches(cls, group=None, searcher=None):
        """
        Find all events that have a search property and load their search into
        the global searcher. A custom searcher will be used instead if
        provided.

        @param group: a group path can be provided to filter a subset of
                      events.
        @param searcher: customer FileSearcher object to be used instead of the
                         global searcher.
        """
        if searcher is None:
            searcher = cls.search_registry.get_global_searcher()
            if len(searcher.catalog) > 0:
                raise Exception("global event searcher catalog is not empty "
                                "and must be reset before loading so as not "
                                "to include searches from a previous run.")

        log.debug("started loading event (group=%s) searches into searcher "
                  "(%s)", group, searcher)

        search_props = set()
        events = YDefsSection(HotSOSConfig.plugin_name,
                              cls.get_defs(group) or {})
        for prop in events.manager.properties.values():
            for item in prop:
                if not issubclass(item['cls'], search.YPropertySearch):
                    break

                search_props.add(item['path'])

        if len(search_props) == 0:
            log.debug("finished loading event searches but no search "
                      "properties found")
            return

        log.debug("loading searches for %s events", len(search_props))
        for event_search_prop_path in search_props:
            event = cls._get_event_from_path(events, event_search_prop_path)
            if cls.skip_filtered_event(event.resolve_path):
                log.debug("skipping event %s", event.resolve_path)
                continue

            cls._load_event_search(event, searcher)

        log.debug("finished loading event searches into searcher "
                  "(registry has %s items)", len(cls.search_registry))


class EventsPreloader(EventsBase):
    """
    Pre-load all searches used in event definitions into a global FileSearcher
    object and execute the search before running any event callbacks.
    """

    @classmethod
    def execute(cls):
        # Pre-load all event searches into a global event searcher
        cls.load_searches()
        # Run the searches so that results are ready when event handlers are
        # run.
        cls.search_registry.get_global_searcher_results()

    @classmethod
    def reset(cls):
        # Make sure we start with a clean registry
        cls.search_registry.reset(create_new_global_searcher=True)

    @classmethod
    def run(cls):
        cls.reset()
        cls.execute()


class EventHandlerBase(EventsBase, YHandlerBase, EventProcessingUtils):
    """
    Root name used to identify a group of event definitions. Once all the
    yaml definitions are loaded this defines the level below which events
    for this checker are expected to be found.
    """
    event_group = None

    def __init__(self, *args, searcher=None, **kwargs):
        """
        @param searcher: optional FileSearcher object. If not provided then the
                         global searcher will be used which is the recommended
                         approach so that all searches are aggregated into one
                         operation and therefore files only need to be searched
                         once.
        """
        super().__init__(*args, **kwargs)
        if searcher is None:
            log.debug("no searcher provided - using global searcher")
            searcher = self.search_registry.get_global_searcher()
            # If no searcher is provided it is assumed that the global searcher
            # already exists, is loaded with searches and they have been
            # executed. Unit tests however, should be resetting the registry
            # prior to each run and we will therefore need to load searches
            # each time which is why we do this here. This is therefore not
            # intended to be used outside of a test scenario.
            if len(searcher.catalog) == 0:
                log.info("global searcher catalog is empty so launching "
                         "pre-load of event searches for group '%s'",
                         self.event_group)
                # NOTE: this is not re-entrant safe and is only ever expected
                #       to be done from a unit test.
                self.load_searches(group=self.event_group)
        else:
            # If a searcher is provided we switch over but do not clear global
            # searcher.
            if self.search_registry._custom_searcher != searcher:
                self.search_registry.set_custom_searcher(searcher)

            self.load_searches(group=self.event_group, searcher=searcher)

        self._event_results = None

    @property
    def searcher(self):
        """
        Return the current searcher we are using. If custom searcher is no
        longer needed it is expected that it will have been cleared in the
        __init__ method.
        """
        return self.search_registry.current_searcher

    @cached_property
    def events(self):
        """ Load event definitions from yaml. """
        group = YDefsSection(HotSOSConfig.plugin_name,
                             self.get_defs(self.event_group) or {})
        log.debug("sections=%s, events=%s",
                  len(list(group.branch_sections)),
                  len(list(group.leaf_sections)))

        _events = {}
        for event in group.leaf_sections:
            if self.skip_filtered_event(event.resolve_path):
                continue

            if not self.meets_requirements(event):
                return {}

            log.debug("event: %s", event.name)
            log.debug("input: %s (command=%s)", event.input.paths,
                      event.input.command is not None)

            section_name = event.parent.name
            if section_name not in _events:
                _events[section_name] = {}

            _events[section_name][event.name] = event.resolve_path

        return _events

    @property
    def final_event_results(self):
        """ Cache of results in case run() is called again. """
        return self._event_results

    def _get_event_search_results(self, event_search, global_results):
        if event_search.passthrough_results:
            # this is for implementations that have their own means of
            # retrieving results.
            return global_results

        seq_def = event_search.sequence_search
        if seq_def:
            search_results = global_results.find_sequence_sections(seq_def)
            if search_results:
                return search_results.values()
        else:
            return global_results.find_by_tag(event_search.unique_search_tag)

    def run(self, results=None):
        """
        Process each event and call respective callback functions when results
        where found.

        @param results: If no results are provides we get them from the global
                        searcher. This is provided for the case where a custom
                        searcher is in use.
        """
        if results is None:
            results = self.search_registry.get_global_searcher_results()

        if self.final_event_results is not None:
            return self.final_event_results

        if not CALLBACKS:
            raise Exception("need to register at least one callback for "
                            "event handler.")

        log.debug("registered event callbacks:\n%s", '\n'.
                  join(CALLBACKS.keys()))
        info = {}
        for section_name, section in self.events.items():
            for event, fullname in section.items():
                event_search = self.search_registry[fullname]['search']
                search_results = self._get_event_search_results(event_search,
                                                                results)
                if not search_results:
                    log.debug("event %s (tag=%s) did not yield any results",
                              event, event_search.unique_search_tag)
                    continue

                # We want this to throw an exception if the callback is not
                # defined.
                callback_name = '{}.{}'.format(self.event_group, event)
                if callback_name not in CALLBACKS:
                    msg = ("no callback found for event {}".
                           format(callback_name))
                    raise EventCallbackNotFound(msg)

                callback = CALLBACKS[callback_name]
                seq_def = event_search.sequence_search
                event_result = EventCheckResult(section_name, event,
                                                search_results,
                                                event_search.unique_search_tag,
                                                self.searcher,
                                                sequence_def=seq_def)
                log.debug("executing event %s.%s callback '%s'",
                          event_result.section, event, callback_name)
                ret = callback()(event_result)
                if not ret:
                    continue

                # if the return is a tuple it is assumed to be of the form
                # (<output value>, <output key>) where <output key> is used to
                # override the output key for the result which defaults to the
                # event name.
                if isinstance(ret, tuple):
                    out_key = ret[1]
                    ret = ret[0]
                    if not ret:
                        continue
                else:
                    out_key = event

                # Don't clobber results, instead allow them to aggregate.
                if out_key in info:
                    info[out_key].update(ret)
                else:
                    info[out_key] = ret

        if info:
            self._event_results = info
            return info
