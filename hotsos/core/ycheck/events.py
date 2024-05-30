import abc
from functools import cached_property

from hotsos.core.config import HotSOSConfig
from hotsos.core.log import log
from hotsos.core.utils import sorted_dict
from hotsos.core.ycheck.engine import (
    YDefsLoader,
    YHandlerBase,
    YDefsSection,
)

CALLBACKS = {}


class EventCallbackNameConflict(Exception):
    pass


class EventCallbackNotFound(Exception):
    pass


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
                msg = ("result (tag={}) does not have enough groups "
                       "(min 1) to be categorised - aborting".
                       format(r.tag))
                raise Exception(msg)
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

    @classmethod
    def _get_tally(cls, result, info, key_by_date, include_time,
                   squash_if_none_keys):
        if key_by_date:
            key = result['date']
            value = result['key']
        else:
            key = result['key']
            value = result['date']

        if key not in info:
            info[key] = {}

        if value is None and squash_if_none_keys:
            if info[key] == {}:
                info[key] = 1
            else:
                info[key] += 1
        else:
            ts_time = result.get('time')
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

    @classmethod
    def _sort_results(cls, categorised_results, key_by_date, include_time):
        log.debug("sorting categorised results")
        # sort main dict keys
        categorised_results = sorted_dict(categorised_results,
                                          reverse=not key_by_date)

        if all([key_by_date, include_time]):
            return

        # Sort values if they are dicts.
        for key, value in categorised_results.items():
            # If not using date as key we need to sort the values so that they
            # will have the same order as if they were sorted by date key.
            if not key_by_date:
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
        if results is None:
            results = cls._get_event_results(event)

        categorised_results = {}
        for r in results:
            cls._get_tally(r, categorised_results, key_by_date, include_time,
                           squash_if_none_keys)

        if not categorised_results:
            return

        categorised_results = cls._sort_results(categorised_results,
                                                key_by_date, include_time)
        if not (key_by_date and max_results_per_date):
            return categorised_results

        shortened = {}
        for date, entries in categorised_results.items():
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


class EventsPreloader(YHandlerBase):
    """
    Pre-load all searches used in event definitions into a global FileSearcher
    object and execute the search before running any event callbacks.
    """

    def run(self):
        # Pre-load all event searches into a global event searcher
        self.global_searcher.preload_event_searches()
        # Run the searches so that results are ready when event handlers are
        # run.
        self.global_searcher.results


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
        if len(self.global_searcher) == 0:
            log.info("global searcher catalog is empty so launching "
                     "pre-load of event searches for group '%s'",
                     self.event_group)
            # NOTE: this is not re-entrant safe and is only ever expected
            #       to be done from a unit test.
            self.global_searcher.preload_event_searches(
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

    @staticmethod
    def skip_filtered_item(event_path):
        e_filter = HotSOSConfig.event_filter
        if e_filter and event_path != e_filter:
            log.info("skipping event %s (filter=%s)", event_path, e_filter)
            return True

        return False

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
            if self.skip_filtered_item(event.resolve_path):
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

    def run(self):
        """
        Process each event and call respective callback functions when results
        where found.
        """

        results = self.global_searcher.results
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
                event_search = self.global_searcher[fullname]['search']
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
                event_result = EventCheckResult(
                                               section_name,
                                               event,
                                               search_results,
                                               event_search.unique_search_tag,
                                               self.global_searcher.searcher,
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
