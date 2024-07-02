import statistics
from datetime import datetime


class EventCollection():
    """Used to collect events found in logfiles. Events are defined as having
    identifiable start and end points containing timestamp information such
    that we can calculate their duration.

    Sequences can span multiple files and are identified by an "event_id" which
    may occur more than once. As such we always try to match using the closest
    available marker by date.
    """
    def __init__(self):
        self._events = {}

    @staticmethod
    def most_recent(items):
        """ For an event id that has been re-used, find the most recent one.

        This means that when we calculate stats on events found we will include
        only the most recent instance of an event with a given id.
        """
        return sorted(items, key=lambda e: e["end"], reverse=True)[0]

    @property
    def complete_events(self):
        """ Complete events are ones for which a duration has been
        calculated which implies their start and has been identified. """
        complete = {}
        for event_id, info in self._events.items():
            for item in info.get("heads", []):
                if "duration" in item:
                    if event_id not in complete:
                        complete[event_id] = []

                    complete[event_id].append(item)

            if event_id in complete:
                complete[event_id] = self.most_recent(complete[event_id])

        return complete

    @property
    def incomplete_events(self):
        incomplete = {}
        for event_id, info in self._events.items():
            for item in info.get("heads", []):
                if "duration" not in item:
                    if event_id not in incomplete:
                        incomplete[event_id] = []

                    incomplete[event_id].append(item)

        return incomplete

    def find_most_recent_start(self, event_id, end_ts):
        """
        For a given event end marker, find the most recent start marker.
        """
        last = {}
        for item in self._events[event_id].get("heads", []):
            start_ts = item["start"]
            if start_ts <= end_ts:
                if not last or start_ts > last["start"]:
                    last = item

        return last

    def add_event_end(self, event_id, end_ts):
        """
        Add an event termination marker with given event id and timestamp.

        We support non-unique event ids in the case that e.g. they get rotated
        by storing as a list of their corresponding end/tail timestamps.

        @param event_id: id used to identify an event iteration. This is
                         usually a sequence id but could be anything.
        @param end_ts: timestamp of the end of an event.
        """
        if event_id not in self._events:
            self._events[event_id] = {}

        if "tails" not in self._events[event_id]:
            self._events[event_id]["tails"] = [end_ts]
        else:
            self._events[event_id]["tails"].append(end_ts)

    def add_event_start(self, event_id, start_ts, metadata=None,
                        metadata_key=None):
        """
        Add an event start marker with given event id and timestamp.

        We support non-unique event ids in the case that e.g. they get rotated
        by storing as a list of their corresponding start timestamps. If an
        event includes some metadata that we want to collect we store it as
        part of the event start/head.

        @param event_id: id used to identify an event iteration. This is
                         usually a sequence id but could be anything.
        @param start_ts: timestamp of the start of an event.
        @param metadata: an optional field that can be extracted from the
                         search result.
        @param metadata_key: a custom key name used to store the metadata in
                             results.
        """
        event_info = {"start": start_ts}
        if metadata:
            if not metadata_key:
                metadata_key = "metadata"

            event_info[metadata_key] = metadata

        if event_id not in self._events:
            self._events[event_id] = {}

        if "heads" not in self._events[event_id]:
            self._events[event_id]["heads"] = [event_info]
        else:
            self._events[event_id]["heads"].append(event_info)

    def calculate_event_deltas(self):
        """
        Once we have collected all complete events i.e. ones that have a start
        and end, we can calculate their elapsed time. We add this to the start
        item.

        Since it is possible for events to be incomplete i.e. not have a start
        or end, we ensure to account for this by matching ends with their
        most recent start.
        """
        for event, info in self._events.items():
            _prev_start = None
            for end_ts in info.get("tails", []):
                start_item = self.find_most_recent_start(event, end_ts)
                if not start_item:
                    # incomplete event
                    continue

                new_start = start_item["start"]
                if _prev_start is None:
                    _prev_start = new_start
                elif _prev_start == new_start:
                    # If we have already closed a start/end loop, ignore any
                    # further endings
                    break

                etime = end_ts - new_start
                duration = round(float(etime.total_seconds()), 2)
                start_item["duration"] = duration
                start_item["end"] = end_ts


class SearchResultIndices():
    def __init__(self, day_idx=1, secs_idx=2, event_id_idx=3,
                 metadata_idx=None, metadata_key=None):
        """
        This is used to know where to find required information within a
        SearchResult. The indexes refer to python.re groups.

        The minimum required information that a result must contain is day,
        secs and event_id. Results will be referred to using whatever event_id
        is set to.
        """
        self.day = day_idx
        self.secs = secs_idx
        self.event_id = event_id_idx
        self.metadata = metadata_idx
        self.metadata_key = metadata_key


class LogEventStats():
    """Used to identify events within logs whereby a event has a start and end
    point. It can thenbe implemented by other classes to perform further
    analysis on event data.

    This class supports overlapping events e.g. for scenarios where logs
    are generated by parallal tasks.
    """

    def __init__(self, results, results_tag_prefix, custom_idxs=None):
        """
        @param results: FileSearcher results. This will be searched using
                        <results_tag_prefix>-start and <results_tag_prefix>-end
        @param results_tag_prefix: prefix of tag used for search results for
                                   events start and end.
        @param custom_idxs: optionally provide custom SearchResultIndices.
        """
        self.data = EventCollection()
        self.results = results
        self.results_tag_prefix = results_tag_prefix
        if custom_idxs:
            log_seq_idxs = custom_idxs
        else:
            log_seq_idxs = SearchResultIndices()

        self.log_seq_idxs = log_seq_idxs

    def run(self):
        """ Collect event start markers and end markers then attempt to link
        them to form complete events thus allowing us to calculate their
        duration.
        """
        seq_idxs = self.log_seq_idxs

        end_tag = "{}-end".format(self.results_tag_prefix)
        for result in self.results.find_by_tag(end_tag):
            day = result.get(seq_idxs.day)
            secs = result.get(seq_idxs.secs)
            end = "{} {}".format(day, secs)
            end = datetime.strptime(end, "%Y-%m-%d %H:%M:%S.%f")
            self.data.add_event_end(result.get(seq_idxs.event_id), end)

        start_tag = "{}-start".format(self.results_tag_prefix)
        for result in self.results.find_by_tag(start_tag):
            day = result.get(seq_idxs.day)
            secs = result.get(seq_idxs.secs)
            start = "{} {}".format(day, secs)
            start = datetime.strptime(start, "%Y-%m-%d %H:%M:%S.%f")
            metadata = result.get(seq_idxs.metadata)
            meta_key = seq_idxs.metadata_key
            event_id = result.get(seq_idxs.event_id)
            self.data.add_event_start(event_id, start, metadata=metadata,
                                      metadata_key=meta_key)

        self.data.calculate_event_deltas()

    def get_top_n_events_sorted(self, maximum, reverse=True):
        """
        Find events with the longest duration limited to max results.

        @param max: integer number of events to include.
        @param reverse: defaults to True for longest durations. Set to False to
        fetch events with shortest duration.
        @return: dictionary of results.
        """
        count = 0
        top_n = {}
        top_n_sorted = {}

        for event_id, item in sorted(self.data.complete_events.items(),
                                     key=lambda e: e[1]["duration"],
                                     reverse=reverse):
            if count >= maximum:
                break

            count += 1
            top_n[event_id] = item

        for event_id, item in sorted(top_n.items(),
                                     key=lambda x: x[1]["start"],
                                     reverse=reverse):
            top_n_sorted[event_id] = {"start": str(item["start"]),
                                      "end": str(item["end"]),
                                      "duration": item["duration"]}

            # include metadata in results if it is available.
            metadata_key = self.log_seq_idxs.metadata_key
            if item.get(metadata_key):
                top_n_sorted[event_id][metadata_key] = item[metadata_key]

        return top_n_sorted

    def get_event_stats(self):
        """ Return common statistics on the dataset of events. """
        events = self.data.complete_events
        if not events:
            return

        events = [s["duration"] for s in events.values()]
        stats = {'min': round(min(events), 2),
                 'max': round(max(events), 2),
                 'stdev': round(statistics.pstdev(events), 2),
                 'avg': round(statistics.mean(events), 2),
                 'samples': len(events)}

        if self.data.incomplete_events:
            stats['incomplete'] = len(self.data.incomplete_events.values())

        return stats
