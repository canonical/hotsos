import os

from . import utils

from hotsos.core import analytics
from hotsos.core.config import HotSOSConfig
from hotsos.core.search import FileSearcher, SearchDef


SEQ_TEST_1 = """2021-07-19 09:01:58.498 iteration:0 start
2021-07-19 09:02:58.498 iteration:0 end
2021-07-19 09:03:58.498 iteration:1 start
2021-07-19 09:04:58.498 iteration:1 end
"""

SEQ_TEST_2 = """2021-07-19 09:01:58.498 iteration:1 start
2021-07-19 09:02:58.498 iteration:1 end
2021-07-19 09:03:58.498 iteration:0 start
2021-07-19 09:04:58.498 iteration:0 end
"""

SEQ_TEST_3 = """2021-07-19 09:01:58.498 iteration:0 start
2021-07-19 09:02:58.498 iteration:0 end
2021-07-19 09:03:58.498 iteration:1 start
2021-07-19 09:04:58.498 iteration:1 end
2021-07-19 09:05:58.498 iteration:0 start
2021-07-19 09:06:58.498 iteration:0 end
"""

SEQ_TEST_4 = """2021-07-19 09:01:58.498 iteration:0 start
2021-07-19 09:03:58.498 iteration:1 start
2021-07-19 09:04:58.498 iteration:1 end
2021-07-19 09:05:58.498 iteration:0 start
2021-07-19 09:06:58.498 iteration:0 start
2021-07-19 09:07:58.498 iteration:0 end
"""

SEQ_TEST_5 = """2021-07-19 09:01:58.498 iteration:0 start
2021-07-19 09:03:58.498 iteration:1 start
2021-07-19 09:04:58.498 iteration:1 end
2021-07-19 09:05:58.498 iteration:0 start
2021-07-19 09:05:58.498 iteration:1 start
2021-07-19 09:07:58.498 iteration:0 end
"""

SEQ_TEST_6 = """2021-07-19 09:01:58.498 iteration:0 start
2021-07-19 09:03:58.498 iteration:1 start
2021-07-19 09:04:58.498 iteration:1 end
2021-07-19 09:05:58.498 iteration:0 start
2021-07-19 09:06:58.498 iteration:1 start
2021-07-19 09:07:58.498 iteration:0 end
2021-07-19 09:08:58.498 iteration:0 start
2021-07-19 09:09:58.498 iteration:0 end
"""


class TestAnalytics(utils.BaseTestCase):

    @utils.create_data_root({'atestfile': SEQ_TEST_1})
    def test_ordered_complete(self):
        fname = os.path.join(HotSOSConfig.data_root, 'atestfile')
        start0 = '2021-07-19 09:01:58.498000'
        end0 = '2021-07-19 09:02:58.498000'
        start1 = '2021-07-19 09:03:58.498000'
        end1 = '2021-07-19 09:04:58.498000'
        expected = {'0': {'duration': 60.0,
                          'start': start0, 'end': end0},
                    '1': {'duration': 60.0, 'start': start1, 'end': end1}}
        s = FileSearcher()
        expr = r'^([0-9\-]+) (\S+) iteration:([0-9]+) start'
        s.add_search_term(SearchDef(expr, tag="eventX-start"),
                          path=fname)
        expr = r'^([0-9\-]+) (\S+) iteration:([0-9]+) end'
        s.add_search_term(SearchDef(expr, tag="eventX-end"),
                          path=fname)
        events = analytics.LogEventStats(s.search(), "eventX")
        events.run()
        top5 = events.get_top_n_events_sorted(5)
        self.assertEqual(top5, expected)
        stats = events.get_event_stats()
        expected = {'avg': 60.0, 'max': 60.0, 'min': 60.0, 'samples': 2,
                    'stdev': 0.0}
        self.assertEqual(stats, expected)

    @utils.create_data_root({'atestfile': SEQ_TEST_2})
    def test_unordered_complete(self):
        fname = os.path.join(HotSOSConfig.data_root, 'atestfile')
        start0 = '2021-07-19 09:03:58.498000'
        end0 = '2021-07-19 09:04:58.498000'
        start1 = '2021-07-19 09:01:58.498000'
        end1 = '2021-07-19 09:02:58.498000'
        expected = {'0': {'duration': 60.0,
                          'start': start0, 'end': end0},
                    '1': {'duration': 60.0, 'start': start1, 'end': end1}}
        s = FileSearcher()
        expr = r'^([0-9\-]+) (\S+) iteration:([0-9]+) start'
        s.add_search_term(SearchDef(expr, tag="eventX-start"),
                          path=fname)
        expr = r'^([0-9\-]+) (\S+) iteration:([0-9]+) end'
        s.add_search_term(SearchDef(expr, tag="eventX-end"),
                          path=fname)
        events = analytics.LogEventStats(s.search(), "eventX")
        events.run()
        top5 = events.get_top_n_events_sorted(5)
        self.assertEqual(top5, expected)
        stats = events.get_event_stats()
        expected = {'avg': 60.0, 'max': 60.0, 'min': 60.0, 'samples': 2,
                    'stdev': 0.0}
        self.assertEqual(stats, expected)

    @utils.create_data_root({'atestfile': SEQ_TEST_3})
    def test_ordered_complete_clobbered(self):
        fname = os.path.join(HotSOSConfig.data_root, 'atestfile')
        start0 = '2021-07-19 09:05:58.498000'
        end0 = '2021-07-19 09:06:58.498000'
        start1 = '2021-07-19 09:03:58.498000'
        end1 = '2021-07-19 09:04:58.498000'
        expected = {'0': {'duration': 60.0,
                          'start': start0, 'end': end0},
                    '1': {'duration': 60.0, 'start': start1, 'end': end1}}
        s = FileSearcher()
        expr = r'^([0-9\-]+) (\S+) iteration:([0-9]+) start'
        s.add_search_term(SearchDef(expr, tag="eventX-start"),
                          path=fname)
        expr = r'^([0-9\-]+) (\S+) iteration:([0-9]+) end'
        s.add_search_term(SearchDef(expr, tag="eventX-end"),
                          path=fname)
        events = analytics.LogEventStats(s.search(), "eventX")
        events.run()
        top5 = events.get_top_n_events_sorted(5)
        self.assertEqual(top5, expected)
        stats = events.get_event_stats()
        expected = {'avg': 60.0,
                    'max': 60.0,
                    'min': 60.0,
                    'samples': 2,
                    'stdev': 0.0}
        self.assertEqual(stats, expected)

    @utils.create_data_root({'atestfile': SEQ_TEST_4})
    def test_ordered_incomplete_clobbered(self):
        fname = os.path.join(HotSOSConfig.data_root, 'atestfile')
        start0 = '2021-07-19 09:06:58.498000'
        end0 = '2021-07-19 09:07:58.498000'
        start1 = '2021-07-19 09:03:58.498000'
        end1 = '2021-07-19 09:04:58.498000'
        expected = {'0': {'duration': 60.0,
                          'start': start0, 'end': end0},
                    '1': {'duration': 60.0, 'start': start1, 'end': end1}}
        s = FileSearcher()
        expr = r'^([0-9\-]+) (\S+) iteration:([0-9]+) start'
        s.add_search_term(SearchDef(expr, tag="eventX-start"),
                          path=fname)
        expr = r'^([0-9\-]+) (\S+) iteration:([0-9]+) end'
        s.add_search_term(SearchDef(expr, tag="eventX-end"),
                          path=fname)
        events = analytics.LogEventStats(s.search(), "eventX")
        events.run()
        top5 = events.get_top_n_events_sorted(5)
        self.assertEqual(top5, expected)
        stats = events.get_event_stats()
        expected = {'avg': 60.0,
                    'incomplete': 1,
                    'max': 60.0,
                    'min': 60.0,
                    'samples': 2,
                    'stdev': 0.0}
        self.assertEqual(stats, expected)

    @utils.create_data_root({'atestfile': SEQ_TEST_5})
    def test_ordered_incomplete_clobbered2(self):
        fname = os.path.join(HotSOSConfig.data_root, 'atestfile')
        start0 = '2021-07-19 09:05:58.498000'
        end0 = '2021-07-19 09:07:58.498000'
        start1 = '2021-07-19 09:03:58.498000'
        end1 = '2021-07-19 09:04:58.498000'
        expected = {'0': {'duration': 120.0,
                          'start': start0, 'end': end0},
                    '1': {'duration': 60.0, 'start': start1, 'end': end1}}
        s = FileSearcher()
        expr = r'^([0-9\-]+) (\S+) iteration:([0-9]+) start'
        s.add_search_term(SearchDef(expr, tag="eventX-start"),
                          path=fname)
        expr = r'^([0-9\-]+) (\S+) iteration:([0-9]+) end'
        s.add_search_term(SearchDef(expr, tag="eventX-end"),
                          path=fname)
        events = analytics.LogEventStats(s.search(), "eventX")
        events.run()
        top5 = events.get_top_n_events_sorted(5)
        self.assertEqual(top5, expected)
        stats = events.get_event_stats()
        expected = {'avg': 90.0, 'incomplete': 2, 'max': 120.0, 'min': 60.0,
                    'samples': 2, 'stdev': 30.0}
        self.assertEqual(stats, expected)

    @utils.create_data_root({'atestfile': SEQ_TEST_6})
    def test_ordered_multiple(self):
        fname = os.path.join(HotSOSConfig.data_root, 'atestfile')
        start0 = '2021-07-19 09:08:58.498000'
        end0 = '2021-07-19 09:09:58.498000'
        start1 = '2021-07-19 09:03:58.498000'
        end1 = '2021-07-19 09:04:58.498000'
        expected = {'0': {'duration': 60.0,
                          'start': start0, 'end': end0},
                    '1': {'duration': 60.0, 'start': start1, 'end': end1}}
        s = FileSearcher()
        expr = r'^([0-9\-]+) (\S+) iteration:([0-9]+) start'
        s.add_search_term(SearchDef(expr, tag="eventX-start"),
                          path=fname)
        expr = r'^([0-9\-]+) (\S+) iteration:([0-9]+) end'
        s.add_search_term(SearchDef(expr, tag="eventX-end"),
                          path=fname)
        events = analytics.LogEventStats(s.search(), "eventX")
        events.run()
        top5 = events.get_top_n_events_sorted(5)
        self.assertEqual(top5, expected)
        stats = events.get_event_stats()
        expected = {'avg': 60.0, 'incomplete': 2, 'max': 60.0, 'min': 60.0,
                    'samples': 2, 'stdev': 0.0}
        self.assertEqual(stats, expected)
