import abc
from functools import cached_property
from dataclasses import dataclass

from hotsos.core.config import HotSOSConfig
from hotsos.core.log import log
from hotsos.core.utils import sorted_dict
from hotsos.core.ycheck.engine import (
    YDefsLoader,
    YHandlerBase,
    YDefsSection,
)
from hotsos.core.ycheck.common import GlobalSearcherPreloaderBase
from hotsos.core.ycheck.engine.properties import search
from hotsos.core.exceptions import (
    NotEnoughParametersError,
    AlreadyLoadedError,
    NoCallbacksRegisteredError,
)

CALLBACKS = {}


class EventCallbackNameConflict(Exception):
    """
    When more than one callback are registered with the same name this
    exception is raised.
    """


class EventCallbackNotFound(Exception):
    """
    When an event is raised but the associated callback is not found, this
    exception is raised.
    """


class EventCallbackAutoRegister(type):
    """
    Event callbacks are registered by implementing this metaclass so that they
    are automatically added to the list of callbacks on which we do a lookup to
    find a match when an event is raised.
    """
    def __init__(cls, _name, _mro, members):
        event_group = members.get('event_group')
        if event_group is None:
            return

        for event in members['event_names']:
            event = f'{event_group}.{event}'
            if event in CALLBACKS:
                msg = f"event callback already registered: {event}"
                raise EventCallbackNameConflict(msg)

            CALLBACKS[event] = cls


@dataclass(frozen=True)
class EventCheckResult:
    """ This is passed to an event check callback when matches are found.

        @param name: event label/name from yaml
        @param section_name: section name from yaml
        @param results: searchkit.SearchResultsCollection
        @param search_tag: unique tag used to identify the results
        @param searcher: global FileSearcher object
        @param sequence_def: if set the search results are from a
                            searchkit.SequenceSearchDef and are therefore
                            grouped as sections of results rather than a single
                            set of results.
    """
    name: str
    section_name: str
    results: object
    search_tag: str
    searcher: object
    sequence_def: object = None


class EventProcessingUtils():
    """
    A set of helper methods to help with the processing of event results.
    """

    @dataclass()
    class EventProcessingOptions:
        """Common options for EventProcessingUtils functions."""
        key_by_date: bool = True
        include_time: bool = False
        squash_if_none_keys: bool = False
        max_results_per_date: int = None

    @classmethod
    def _get_event_results(cls, event):
        """
        Return dicts with keys 'date', 'key' and 'value' extracted from event
        search results. The result can have between one and three groups to
        match these keys respectively. If only one group (date) this provide a
        tally per date. Two groups provides a tally per key per date etc.
        """
        _fail_count = 0
        # Use these to ensure we only print the message once to avoid spamming
        # the logs.
        msg_flag = True
        for r in event.results:
            # the search expression used much ensure that these are
            # available in order for this to work.
            if len(r) > 2:
                if not set([None, None, None]).intersection([r.get(1),
                                                             r.get(2),
                                                             r.get(3)]):
                    yield {'date': r.get(1), 'time': r.get(2), 'key': r.get(3)}
                else:
                    _fail_count += 1
            elif len(r) == 0:
                msg = (f"result (tag={r.tag}) does not have enough groups "
                       "(min 1) to be categorised - aborting")
                raise NotEnoughParametersError(msg)
            else:
                if msg_flag and len(r) < 2:
                    msg_flag = False
                    # results with just a date will have None for the key
                    log.debug("results with tag=%s have just one group which "
                              "is assumed to be a date so using key=None",
                              r.tag)

                yield {'date': r.get(1), 'key': r.get(2)}

        if _fail_count:
            log.info("%s results ignored from event %s due to insufficient "
                     "fields",
                     _fail_count, event.name)

    @staticmethod
    def _get_tally(result, info, options: EventProcessingOptions):
        if options.key_by_date:
            key = result['date']
            value = result['key']
        else:
            key = result['key']
            value = result['date']

        if key not in info:
            info[key] = {}

        if value is None and options.squash_if_none_keys:
            if info[key] == {}:
                info[key] = 1
            else:
                info[key] += 1
        else:
            ts_time = result.get('time')
            if value not in info[key]:
                if ts_time is not None and options.include_time:
                    info[key][value] = {}
                else:
                    info[key][value] = 0

            if ts_time is not None and options.include_time:
                if ts_time not in info[key][value]:
                    info[key][value][ts_time] = 1
                else:
                    info[key][value][ts_time] += 1
            else:
                info[key][value] += 1

    @staticmethod
    def _sort_results(categorised_results, options: EventProcessingOptions):
        log.debug("sorting categorised results")
        if all([options.key_by_date, options.include_time]):
            return {}

        # sort main dict keys
        categorised_results = sorted_dict(categorised_results,
                                          reverse=not options.key_by_date)

        # Sort values if they are dicts.
        for key, value in categorised_results.items():
            # If not using date as key we need to sort the values so that they
            # will have the same order as if they were sorted by date key.
            if not options.key_by_date:
                categorised_results[key] = sorted_dict(value)
                continue

            # sort by value i.e. tally/count
            for key, value in categorised_results.items():
                if not isinstance(value, dict):
                    break

                categorised_results[key] = sorted_dict(value,
                                                       key=lambda e: e[1],
                                                       reverse=True)

        return categorised_results

    @classmethod
    def global_event_tally_time_granularity_override(cls):
        """
        If results are categorised without time included and this returned True
        we checks if HotSOSConfig.event_tally_granularity is set to 'time' and
        if so enforce time included in results.

        Implementations should override this property to return True if they
        want this behaviour.
        """
        return False

    @classmethod
    def categorise_events(
        cls,
        event,
        results=None,
        options: EventProcessingOptions = None,
    ):
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
        if options is None:
            options = EventProcessingUtils.EventProcessingOptions()

        if results is None:
            results = cls._get_event_results(event)

        if cls.global_event_tally_time_granularity_override() is True:
            options.include_time = HotSOSConfig.event_tally_granularity == \
                 "time"

        categorised_results = {}
        for r in results:
            cls._get_tally(r, categorised_results, options)

        if not categorised_results:
            return {}

        categorised_results = cls._sort_results(categorised_results, options)
        if not (options.key_by_date and options.max_results_per_date):
            return categorised_results

        shortened = {}
        for date, entries in categorised_results.items():
            if len(entries) <= options.max_results_per_date:
                shortened[date] = entries
                continue

            top_n = dict(sorted(entries.items(),
                                key=lambda e: e[1],
                                reverse=True)[:options.max_results_per_date])
            shortened[date] = {
                "total": len(entries),
                f"top{options.max_results_per_date}": top_n,
            }

        return shortened


class EventCallbackBase(EventProcessingUtils,
                        metaclass=EventCallbackAutoRegister):
    """ Base class used for all event callbacks. """
    # All implementations must set these and event_group must match that used
    # in the handler.
    event_group = None
    event_names = []

    @abc.abstractmethod
    def __call__(self):
        """ Callback method. """


class EventsSearchPreloader(YHandlerBase, GlobalSearcherPreloaderBase):
    """
    Pre-load all searches used in event definitions into a global FileSearcher
    object and execute the search before running any event callbacks.
    """

    @staticmethod
    def skip_filtered(path):
        e_filter = HotSOSConfig.event_filter
        if e_filter and path != e_filter:
            log.info("skipping event %s (filter=%s)", path, e_filter)
            return True

        return False

    def preload_searches(self, global_searcher, group=None):
        """
        Find all events that have a search property and load their search into
        the global searcher.

        @param global_searcher: GlobalSearcher object
        @param group: a group path can be provided to filter a subset of
                      items.
        """
        if global_searcher.is_loaded(self.__class__.__name__):
            raise AlreadyLoadedError(
                "event searches have already been loaded into the "
                "global searcher. This operation can only be "
                "performed once.")

        log.debug("started loading (group=%s) searches into searcher "
                  "(%s)", group, global_searcher.searcher)

        plugin_defs = YDefsLoader('events', filter_path=group).plugin_defs
        root = YDefsSection(HotSOSConfig.plugin_name, plugin_defs or {})
        added = 0
        for prop in root.manager.properties.values():
            if not issubclass(prop[0]['cls'], search.YPropertySearch):
                continue

            for item in prop:
                parent = self._find_search_prop_parent(root, item['path'])
                if self.skip_filtered(parent.resolve_path):
                    log.debug("skipping item %s", parent.resolve_path)
                    continue

                added += 1
                self._load_item_search(global_searcher, parent.search,
                                       parent.input)

        global_searcher.set_loaded(self.__class__.__name__)
        log.debug("identified a total of %s event check searches", added)
        log.debug("finished loading event searches into searcher "
                  "(registry now has %s items)", len(global_searcher))

    def run(self, group=None):
        log.debug("registered event callbacks:\n%s", '\n'.
                  join(CALLBACKS.keys()))

        # Pre-load all event searches into a global searcher
        self.preload_searches(self.global_searcher, group=group)


class EventHandlerBase(YHandlerBase, EventProcessingUtils):
    """
    Root name used to identify a group of event definitions. Once all the
    yaml definitions are loaded this defines the level below which events
    for this checker are expected to be found.
    """
    event_group = None

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # It is assumed that the global searcher already exists, is loaded with
        # searches and they have been executed. Unit tests however, should be
        # resetting the registry prior to each run and we will therefore need
        # to load searches each time which is why we do this here. This is
        # therefore not intended to be used outside of a test scenario.
        label = EventsSearchPreloader.__name__
        if not self.global_searcher.is_loaded(label):
            log.info("global searcher catalog is empty so launching "
                     "pre-load of event searches for group '%s'",
                     self.event_group)
            # NOTE: this is not re-entrant safe and is only ever expected
            #       to be done from a unit test.
            EventsSearchPreloader(self.global_searcher).run(
                                                        group=self.event_group)

        self._event_results = None

    @staticmethod
    def meets_requirements(item):
        """
        If an item or group has a requirements property it must return True
        in order to be executed.
        """
        if HotSOSConfig.force_mode:
            return True

        if item.requires and not item.requires.result:
            log.debug("item '%s' pre-requisites not met - "
                      "skipping", item.name)
            return False

        return True

    @property
    def searcher(self):
        return self.global_searcher.searcher

    @cached_property
    def events(self):
        """ Load event definitions from yaml. """
        group_defs = YDefsLoader('events',
                                 filter_path=self.event_group).plugin_defs
        group = YDefsSection(HotSOSConfig.plugin_name, group_defs or {})
        log.debug("sections=%s, events=%s",
                  len(list(group.branch_sections)),
                  len(list(group.leaf_sections)))

        _events = {}
        for event in group.leaf_sections:
            if EventsSearchPreloader.skip_filtered(event.resolve_path):
                continue

            if not self.meets_requirements(event):
                return {}

            log.debug("event: %s", event.name)
            log.debug("input: %s (command=%s)", event.input.paths,
                      event.input.command is not None)

            section_name = event.parent.name
            if section_name not in _events:
                _events[section_name] = {}

            _events[section_name][event.name] = event.search.unique_search_tag

        return _events

    @property
    def final_event_results(self):
        """ Cache of results in case run() is called again. """
        return self._event_results

    @staticmethod
    def _get_event_search_results(global_results, search_tag,
                                  sequence_search_def, passthrough_results):
        if passthrough_results:
            # this is for implementations that have their own means of
            # retrieving results.
            return global_results

        if sequence_search_def is None:
            return global_results.find_by_tag(search_tag)

        search_results = global_results.find_sequence_sections(
                             sequence_search_def)
        if search_results:
            return search_results.values()

        return {}

    def run(self):
        """
        Process each event and call respective callback functions when results
        where found.
        """

        results = self.global_searcher.results
        if self.final_event_results is not None:
            return self.final_event_results

        if not CALLBACKS:
            raise NoCallbacksRegisteredError(
                "need to register at least one callback for event handler.")

        log.debug("running event(s) for group=%s", self.event_group)
        info = {}
        for section_name, section in self.events.items():
            for event, fullname in section.items():
                event_search = self.global_searcher[fullname]
                seq_def = event_search['sequence_search']
                search_tag = event_search['search_tag']
                passthrough = event_search['passthrough_results']
                search_results = self._get_event_search_results(results,
                                                                search_tag,
                                                                seq_def,
                                                                passthrough)
                if not search_results:
                    log.debug("event %s (tag=%s) did not yield any results",
                              event, event_search['search_tag'])
                    continue

                # We want this to throw an exception if the callback is not
                # defined.
                callback_name = f'{self.event_group}.{event}'
                if callback_name not in CALLBACKS:
                    msg = f"no callback found for event {callback_name}"
                    raise EventCallbackNotFound(msg)

                callback = CALLBACKS[callback_name]
                event_result = EventCheckResult(
                    name=event,
                    section_name=section_name,
                    results=search_results,
                    search_tag=search_tag,
                    searcher=self.global_searcher.searcher,
                    sequence_def=seq_def
                )
                log.debug("executing event %s.%s callback '%s'",
                          event_result.section_name, event, callback_name)
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

        return {}
