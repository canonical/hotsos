from hotsos.core.log import log
from hotsos.core.searchtools import (
    SearchDef,
    SequenceSearchDef,
)
from hotsos.core.ycheck import (
    YDefsLoader,
    ChecksBase,
    YDefsSection,
)


class EventCheckResult(object):
    """ This is passed to an event check callback when matches are found """

    def __init__(self, defs_section, defs_event, search_results,
                 sequence_def=None):
        """
        @param defs_section: section name from yaml
        @param defs_event: event label/name from yaml
        @param search_results: searchtools.SearchResultsCollection
        @param sequence_def: if set the search results are from a
                            searchtools.SequenceSearchDef and are therefore
                            grouped as sections of results rather than a single
                            set of results.
        """
        self.section = defs_section
        self.name = defs_event
        self.results = search_results
        self.sequence_def = sequence_def


class YEventCheckerBase(ChecksBase):

    def __init__(self, *args, callback_helper=None, **kwargs):
        """
        @param callback_helper: optionally provide a callback helper. This is
        used to "register" callbacks against events defined in the yaml so
        that they are automatically called when corresponding events are
        detected.
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
        plugin = YDefsLoader('events').load_plugin_defs()
        if not plugin:
            return

        group_name = self._yaml_defs_group
        log.debug("loading defs for subgroup=%s", group_name)
        group_defs = plugin.get(group_name)
        group = YDefsSection(group_name, group_defs)
        log.debug("sections=%s, events=%s",
                  len(group.branch_sections),
                  len(group.leaf_sections))

        for event in group.leaf_sections:
            results_passthrough = bool(event.passthrough_results)
            log.debug("event: %s", event.name)
            log.debug("input: %s (command=%s)", event.input.path,
                      event.input.command is not None)
            log.debug("passthrough: %s", results_passthrough)

            section_name = event.parent.name
            # this is hopefully unique enough to allow two events from
            # different sections to have the same name and not clobber each
            # others results.
            search_tag = "{}.{}".format(section_name, event.name)

            # if this is a multiline event (has a start and end), append
            # this to the tag so that it can be used with
            # core.analytics.LogEventStats.
            search_meta = {'searchdefs': [], 'datasource': None,
                           'passthrough_results': results_passthrough}

            if event.expr:
                hint = None
                if event.hint:
                    hint = event.hint.value

                search_meta['searchdefs'].append(
                    SearchDef(event.expr.value, tag=search_tag, hint=hint))
            elif event.start:
                if (event.body or
                        (event.end and not results_passthrough)):
                    log.debug("event '%s' search is a sequence", event.name)
                    sd_start = SearchDef(event.start.expr)

                    sd_end = None
                    # explicit end is optional for sequence definition
                    if event.end:
                        sd_end = SearchDef(event.end.expr)

                    sd_body = None
                    if event.body:
                        sd_body = SearchDef(event.body.expr)

                    # NOTE: we don't use hints here
                    sequence_def = SequenceSearchDef(start=sd_start,
                                                     body=sd_body,
                                                     end=sd_end,
                                                     tag=search_tag)
                    search_meta['searchdefs'].append(sequence_def)
                    search_meta['is_sequence'] = True
                elif (results_passthrough and
                      (event.start and event.end)):
                    # start and end required for core.analytics.LogEventStats
                    search_meta['searchdefs'].append(
                        SearchDef(event.start.expr,
                                  tag="{}-start".format(search_tag),
                                  hint=event.start.hint))
                    search_meta['searchdefs'].append(
                        SearchDef(event.end.expr,
                                  tag="{}-end".format(search_tag),
                                  hint=event.end.hint))
                else:
                    log.debug("unexpected search definition passthrough=%s "
                              "body provided=%s, end provided=%s",
                              results_passthrough, event.body is not None,
                              event.end is not None)
            else:
                log.debug("invalid search definition for event '%s' in "
                          "section '%s'", event, event.parent.name)
                continue

            datasource = event.input.path
            if section_name not in self.__event_defs:
                self.__event_defs[section_name] = {}

            search_meta['datasource'] = datasource
            self.__event_defs[section_name][event.name] = search_meta

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
        """
        Load and register the search definitions for all events.

        @param root_key: events.yaml root key
        """
        for defs in self.event_definitions.values():
            for label in defs:
                event = defs[label]
                for sd in event["searchdefs"]:
                    self.searchobj.add_search_term(sd, event["datasource"])

    @property
    def final_event_results(self):
        """
        This is a cache of the results obtained by running run().
        """
        return self.__final_event_results

    def run(self, results):
        """
        Provide a default way for results to be processed. This requires a
        CallbackHelper to have been provided and callbacks registered. If that
        is not the case the method must be re-implemented with another means
        of processing results.

        See defs/events.yaml for definitions.
        """
        if self.__final_event_results:
            return self.__final_event_results

        if self.callback_helper is None or not self.callback_helper.callbacks:
            # If there are no callbacks registered this method must be
            # (re)implemented.
            raise NotImplementedError

        info = {}
        for section_name, section in self.event_definitions.items():
            for event, event_meta in section.items():
                search_tag = "{}.{}".format(section_name, event)
                sequence_def = None
                if event_meta.get('passthrough_results'):
                    # this is for implementations that have their own means of
                    # retreiving results.
                    search_results = results
                else:
                    if event_meta.get('is_sequence'):
                        sequence_def = event_meta['searchdefs'][0]
                        search_results = results.find_sequence_sections(
                            sequence_def)
                        if search_results:
                            search_results = search_results.values()
                    else:
                        search_results = results.find_by_tag(search_tag)

                if not search_results:
                    continue

                # We want this to throw an exception if the callback is not
                # defined.
                callback_name = event.replace('-', '_')
                callback = self.callback_helper.callbacks[callback_name]
                event_results_obj = EventCheckResult(section_name, event,
                                                     search_results,
                                                     sequence_def=sequence_def)
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
