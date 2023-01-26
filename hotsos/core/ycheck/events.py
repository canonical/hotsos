from hotsos.core.log import log
from hotsos.core.config import HotSOSConfig
from hotsos.core.utils import sorted_dict
from hotsos.core.ycheck.engine import (
    YDefsLoader,
    YHandlerBase,
    YDefsSection,
)


class CallbackHelper(object):

    def __init__(self):
        self.callbacks = {}

    def callback(self, event_group, event_names=None):
        """
        Register a method as a callback for a given event.

        @param event_group: defs group containing these events. Needs to be
                             for the current plugin.
        @param event_names: optional list of event names. If none provided, the
                            name of the decorated function is used.
        """
        def callback_inner(f):
            def callback_inner2(*args, **kwargs):
                return f(*args, **kwargs)

            names = []
            if event_names:
                for name in event_names:
                    # convert event name to valid method name
                    names.append('{}.{}'.format(event_group,
                                                name.replace('-', '_')))
            else:
                names.append('{}.{}'.format(event_group, f.__name__))

            for name in names:
                if name in self.callbacks:
                    raise Exception("A callback has already been registered "
                                    "with name {}".format(name))

                self.callbacks[name] = callback_inner2

            return callback_inner2

        # we don't need to return but we leave it so that we can unit test
        # these methods.
        return callback_inner


class EventCheckResult(object):
    """ This is passed to an event check callback when matches are found """

    def __init__(self, defs_section, defs_event, search_results, search_tag,
                 sequence_def=None):
        """
        @param defs_section: section name from yaml
        @param defs_event: event label/name from yaml
        @param search_results: searchkit.SearchResultsCollection
        @param search_tag: unique tag used to identify the results
        @param sequence_def: if set the search results are from a
                            searchkit.SequenceSearchDef and are therefore
                            grouped as sections of results rather than a single
                            set of results.
        """
        self.section = defs_section
        self.name = defs_event
        self.search_tag = search_tag
        self.results = search_results
        self.sequence_def = sequence_def


class EventProcessingUtils(object):

    @classmethod
    def categorise_events(cls, event, results=None, key_by_date=True,
                          include_time=False, squash_if_none_keys=False):
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
                else:
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

            return sorted_dict(info, reverse=not key_by_date)


class YEventCheckerBase(YHandlerBase, EventProcessingUtils):

    def __init__(self, callback_helper, *args, **kwargs):
        """
        @param callback_helper: CallbackHelper object used to register
        callbacks against events defined in the yaml. When an event has results
        its associated callback with the same name is called to process the
        results.
        """
        super().__init__(*args, **kwargs)
        self.callback_helper = callback_helper
        self.__event_defs = {}
        self.__final_event_results = None

    def _load_event_definitions(self):
        """
        Load event search definitions from yaml.

        An event is identified using between one and two expressions. If it
        requires a start and end to be considered complete then these can be
        specified for match otherwise we can match on a single line.
        Note that multi-line events can be overlapping hence why we don't use a
        SequenceSearchDef (we use core.analytics.LogEventStats).
        """
        plugin = YDefsLoader('events').plugin_defs
        if not plugin:
            return

        group_name = self._yaml_defs_group
        log.debug("loading defs for subgroup=%s", group_name)
        ytree = plugin
        ypath = group_name.split('.')
        for i, g in enumerate(ypath):
            if i >= len(ypath) - 1:
                group_defs = ytree.get(g)
            else:
                ytree = ytree.get(g)

        group = YDefsSection(group_name, group_defs)
        log.debug("sections=%s, events=%s",
                  len(group.branch_sections),
                  len(group.leaf_sections))

        for event in group.leaf_sections:
            if (not HotSOSConfig.force_mode and event.requires and not
                    event.requires.passes):
                log.error("event '%s' pre-requisites not met - "
                          "skipping", event.name)
                return

            log.debug("event: %s", event.name)
            log.debug("input: %s (command=%s)", event.input.paths,
                      event.input.command is not None)

            section_name = event.parent.name
            if section_name not in self.__event_defs:
                self.__event_defs[section_name] = {}

            for path in event.input.paths:
                if event.input.command:
                    # don't apply constraints to command outputs
                    allow_constraints = False
                else:
                    allow_constraints = True

                event.search.load_searcher(self.searchobj, path,
                                           allow_constraints=allow_constraints)

            emeta = {'passthrough': event.search.passthrough_results_opt,
                     'sequence': event.search.sequence_search,
                     'tag': event.search.unique_search_tag}
            self.__event_defs[section_name][event.name] = emeta

    @property
    def event_definitions(self):
        """
        @return: dict of SearchDef objects and datasource for all entries in
        defs/events.yaml under _yaml_defs_group.
        """
        if self.__event_defs:
            return self.__event_defs

        self._load_event_definitions()
        return self.__event_defs

    def load(self):
        """ preload """
        self.event_definitions

    @property
    def final_event_results(self):
        """
        This is a cache of the results obtained by running run().
        """
        return self.__final_event_results

    def run(self, results):
        """
        Provide a default way for results to be processed.

        See defs/events.yaml for definitions.
        """
        if self.__final_event_results:
            return self.__final_event_results

        if not self.callback_helper.callbacks:
            raise Exception("need to register at least one callback for "
                            "event handler.")

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
                callback_name = '{}.{}'.format(self._yaml_defs_group,
                                               event.replace('-', '_'))
                callback = self.callback_helper.callbacks[callback_name]
                event_results_obj = EventCheckResult(section_name, event,
                                                     search_results,
                                                     search_tag,
                                                     sequence_def=seq_def)
                log.debug("executing event %s.%s callback '%s'",
                          event_results_obj.section, event,
                          callback_name)
                ret = callback(self, event_results_obj)
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
            self.__final_event_results = info
            return info
