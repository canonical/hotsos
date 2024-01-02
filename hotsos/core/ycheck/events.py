import abc
from functools import cached_property

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
from hotsos.core.ycheck.engine.properties.search import CommonTimestampMatcher


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
                for key in info:
                    if not isinstance(info[key], dict):
                        break

                    info[key] = sorted_dict(info[key], key=lambda e: e[1],
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


class EventHandlerBase(YHandlerBase, EventProcessingUtils):
    """
    Root name used to identify a group of event definitions. Once all the
    yaml definitions are loaded this defines the level below which events
    for this checker are expected to be found.
    """
    event_group = None

    def __init__(self, *args, searcher=None, **kwargs):
        """
        @param searcher: optional FileSearcher object. When running many event
                         checkers it is more efficient to share a
                         FileSearcher across them so that all searches are
                         done at once.
        """
        super().__init__(*args, **kwargs)
        if not searcher:
            log.debug("creating searcher for event checker")
            searcher = FileSearcher(constraint=SearchConstraintSearchSince(
                                        ts_matcher_cls=CommonTimestampMatcher))

        self._searcher = searcher
        self._event_results = None

    @property
    def searcher(self):
        return self._searcher

    @cached_property
    def event_definitions(self):
        """ Load event definitions from yaml. """
        _event_defs = {}

        plugin = YDefsLoader('events').plugin_defs
        if not plugin:
            return _event_defs

        log.debug("loading defs for subgroup=%s", self.event_group)
        ytree = plugin
        ypath = self.event_group.split('.')
        for i, g in enumerate(ypath):
            if i >= len(ypath) - 1:
                group_defs = ytree.get(g)
            else:
                ytree = ytree.get(g)

        group = YDefsSection(self.event_group, group_defs)
        log.debug("sections=%s, events=%s",
                  len(group.branch_sections),
                  len(group.leaf_sections))

        for event in group.leaf_sections:
            fullname = "{}.{}.{}".format(HotSOSConfig.plugin_name,
                                         event.parent.name, event.name)
            if (HotSOSConfig.event_filter and
                    fullname != HotSOSConfig.event_filter):
                log.info("skipping event %s (filter=%s)", fullname,
                         HotSOSConfig.event_filter)
                continue

            if (not HotSOSConfig.force_mode and event.requires and not
                    event.requires.passes):
                log.error("event '%s' pre-requisites not met - "
                          "skipping", event.name)
                return {}

            log.debug("event: %s", event.name)
            log.debug("input: %s (command=%s)", event.input.paths,
                      event.input.command is not None)

            section_name = event.parent.name
            if section_name not in _event_defs:
                _event_defs[section_name] = {}

            for path in event.input.paths:
                if event.input.command:
                    # don't apply constraints to command outputs
                    allow_constraints = False
                else:
                    allow_constraints = True

                event.search.load_searcher(self.searcher, path,
                                           allow_constraints=allow_constraints)

            emeta = {'passthrough': event.search.passthrough_results_opt,
                     'sequence': event.search.sequence_search,
                     'tag': event.search.unique_search_tag}
            _event_defs[section_name][event.name] = emeta

        return _event_defs

    def load(self):
        """ Pre-load event definitions. """
        self.event_definitions

    @property
    def final_event_results(self):
        """ Cache of results in case run() is called again. """
        return self._event_results

    def run(self, results):
        """
        Process each event and call respective callback functions when results
        where found.

        @param results: SearchResultsCollection object.
        """
        if self.final_event_results is not None:
            return self.final_event_results

        if not CALLBACKS:
            raise Exception("need to register at least one callback for "
                            "event handler.")

        log.debug("registered callbacks:\n%s", '\n'.join(CALLBACKS.keys()))
        info = {}
        for section_name, section in self.event_definitions.items():
            for event, event_meta in section.items():
                search_tag = event_meta['tag']
                seq_def = None
                if event_meta['passthrough']:
                    # this is for implementations that have their own means of
                    # retrieving results.
                    search_results = results
                else:
                    seq_def = event_meta['sequence']
                    if seq_def:
                        search_results = results.find_sequence_sections(
                            seq_def)
                        if search_results:
                            search_results = search_results.values()
                    else:
                        search_results = results.find_by_tag(search_tag)

                if not search_results:
                    log.debug("event %s did not yield any results", event)
                    continue

                # We want this to throw an exception if the callback is not
                # defined.
                callback_name = '{}.{}'.format(self.event_group, event)
                if callback_name not in CALLBACKS:
                    msg = ("no callback found for event {}".
                           format(callback_name))
                    raise EventCallbackNotFound(msg)

                callback = CALLBACKS[callback_name]
                event_results_obj = EventCheckResult(section_name, event,
                                                     search_results,
                                                     search_tag,
                                                     self.searcher,
                                                     sequence_def=seq_def)
                log.debug("executing event %s.%s callback '%s'",
                          event_results_obj.section, event,
                          callback_name)
                ret = callback()(event_results_obj)
                if not ret:
                    continue

                # if the return is a tuple it is assumed to be of the form
                # (<output value>, <output key>) where <output key> is used to
                # override the output key for the result which defaults to the
                # event name.
                if type(ret) == tuple:
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

    def load_and_run(self):
        self.load()
        return self.run(self.searcher.run())
