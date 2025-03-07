import os
from collections import OrderedDict

import yaml
from hotsos.core.config import HotSOSConfig
from hotsos.core.ycheck.engine import YDefsSection
from hotsos.core.ycheck.common import GlobalSearcher
from hotsos.core.ycheck.events import (
    EventHandlerBase,
    EventCallbackBase,
    EventCallbackNotFound,
    EventProcessingUtils,
    EventsSearchPreloader,
)

from .. import utils

# It is fine for a test to access a protected member so allow it for all tests
# pylint: disable=protected-access

EVENT_DEF_INPUT = """
pluginX:
  myeventgroup:
    input:
      path: foo/bar1
    myeventsubgroup:
      someevent:
        requires:
          apt: foo
"""

EVENT_DEF_INPUT_SUPERSEDED = """
pluginX:
  myeventgroup:
    input:
      path: foo/bar1
    myeventsubgroup:
      input:
        path: foo/bar2
      someevent:
        requires:
          apt: foo
"""

EVENT_DEF_INPUT_SUPERSEDED2 = """
pluginX:
  myeventgroup:
    input:
      path: foo/bar1
    myeventsubgroup:
      input:
        path: foo/bar2
      someevent:
        input:
          path: foo/bar3
        requires:
          apt: foo
"""

EVENT_DEF_SIMPLE = r"""
myeventgroup:
  input:
    path: a/path
  myeventsubgroup:
    event1:
      expr: 'event1'
    event2:
      expr: 'event2'
"""  # noqa

EVENT_DEF_MULTI_SEARCH = r"""
myplugin:
  myeventgroup:
    input:
      path: {path}
    myeventsubgroup:
      my-sequence-search:
        start: '^hello'
        body: '^\S+'
        end: '^world'
      my-passthrough-search:
        passthrough-results: True
        start: '^hello'
        end: '^world'
      my-pass-search:
        expr: '^hello'
        hint: '.+'
      my-fail-search1:
        expr: '^hello'
        hint: '^foo'
      my-fail-search2:
        expr: '^foo'
        hint: '.+'
"""  # noqa


class TestYamlEventsPreLoad(utils.BaseTestCase):
    """
    Tests events search pre-load functionality.
    """
    @utils.create_data_root({'data.txt': 'hello\nbrave\nworld\n',
                             'events/myplugin/mygroup.yaml':
                             EVENT_DEF_MULTI_SEARCH.format(path='data.txt')})
    @utils.global_search_context
    def test_events_search_preload(self, global_searcher):
        HotSOSConfig.plugin_yaml_defs = HotSOSConfig.data_root
        HotSOSConfig.plugin_name = 'myplugin'
        spl = EventsSearchPreloader(global_searcher)
        events = list(spl.events)
        self.assertEqual(len(events), 5)
        spl.run()
        self.assertListEqual([e.name for e in spl.events],
                             ['my-sequence-search', 'my-passthrough-search',
                              'my-pass-search', 'my-fail-search1',
                              'my-fail-search2'])
        for e in spl.events:
            for path in e.input.paths:
                self.assertEqual(os.path.basename(path), 'data.txt*')


class TestYamlEvents(utils.BaseTestCase):
    """ Tests for yaml events """

    def test_yaml_def_group_input(self):
        plugin_checks = yaml.safe_load(EVENT_DEF_INPUT).get('pluginX')
        for name, group in plugin_checks.items():
            group = YDefsSection(name, group)
            for entry in group.leaf_sections:
                self.assertEqual(entry.input.paths,
                                 [os.path.join(HotSOSConfig.data_root,
                                               'foo/bar1*')])

    def test_yaml_def_section_input_override(self):
        plugin_checks = yaml.safe_load(EVENT_DEF_INPUT_SUPERSEDED)
        for name, group in plugin_checks.get('pluginX').items():
            group = YDefsSection(name, group)
            for entry in group.leaf_sections:
                self.assertEqual(entry.input.paths,
                                 [os.path.join(HotSOSConfig.data_root,
                                               'foo/bar2*')])

    def test_yaml_def_entry_input_override(self):
        plugin_checks = yaml.safe_load(EVENT_DEF_INPUT_SUPERSEDED2)
        for name, group in plugin_checks.get('pluginX').items():
            group = YDefsSection(name, group)
            for entry in group.leaf_sections:
                self.assertEqual(entry.input.paths,
                                 [os.path.join(HotSOSConfig.data_root,
                                               'foo/bar3*')])

    @utils.create_data_root({'data.txt': 'hello\nbrave\nworld\n',
                             'events/myplugin/mygroup.yaml':
                             EVENT_DEF_MULTI_SEARCH.format(path='data.txt')})
    def test_yaml_def_entry_input_paths(self):
        _yaml = EVENT_DEF_MULTI_SEARCH.format(path='data.txt')
        plugin_checks = yaml.safe_load(_yaml).get('myplugin')
        for name, group in plugin_checks.items():
            group = YDefsSection(name, group)
            data_file = os.path.join(HotSOSConfig.data_root, 'data.txt')
            for entry in group.leaf_sections:
                self.assertEqual(entry.input.paths, [f'{data_file}*'])

    @utils.create_data_root({'data.txt': 'hello\nbrave\nworld\n',
                             'events/myplugin/mygroup.yaml':
                             EVENT_DEF_MULTI_SEARCH.format(path='data.txt')})
    def test_yaml_def_entry_seq(self):
        test_self = self
        match_count = {'count': 0}
        callbacks_called = {}
        HotSOSConfig.plugin_yaml_defs = HotSOSConfig.data_root
        HotSOSConfig.plugin_name = 'myplugin'

        class MyEventCallback(EventCallbackBase):  # noqa, pylint: disable=W0612
            """ Test Callback """
            event_group = 'mygroup'
            event_names = ['my-sequence-search', 'my-passthrough-search',
                           'my-pass-search', 'my-fail-search1',
                           'my-fail-search2']

            @staticmethod
            def my_sequence_search(event):
                callbacks_called[event.name] = True
                for section in event.results:
                    for result in section:
                        if result.tag.endswith('-start'):
                            match_count['count'] += 1
                            test_self.assertEqual(result.get(0), 'hello')
                        elif result.tag.endswith('-body'):
                            match_count['count'] += 1
                            test_self.assertEqual(result.get(0), 'brave')
                        elif result.tag.endswith('-end'):
                            match_count['count'] += 1
                            test_self.assertEqual(result.get(0), 'world')

            @staticmethod
            def my_passthrough_search(event):
                # expected to be passthough results (i.e. raw)
                callbacks_called[event.name] = True
                tag = f'{event.search_tag}-start'
                start_results = event.results.find_by_tag(tag)
                test_self.assertEqual(start_results[0].get(0), 'hello')

            def __call__(self, event):
                callbacks_called[event.name] = True
                if event.name == 'my-sequence-search':
                    return self.my_sequence_search(event)

                if event.name == 'my-passthrough-search':
                    return self.my_passthrough_search(event)

                test_self.assertEqual(event.results[0].get(0), 'hello')
                return None

        class MyEventHandler(EventHandlerBase):
            """ Test Handler """
            @property
            def event_group(self):
                return 'mygroup'

        with GlobalSearcher() as searcher:
            MyEventHandler(global_searcher=searcher).run()

        self.assertEqual(match_count['count'], 3)
        self.assertEqual(list(callbacks_called.keys()),
                         ['my-sequence-search',
                          'my-passthrough-search',
                          'my-pass-search'])

    @utils.create_data_root({'data.txt': 'hello\nbrave\nworld\n',
                             'events/myplugin/mygroup.yaml':
                             EVENT_DEF_MULTI_SEARCH.format(path='data.txt')})
    def test_yaml_def_entry_callback_not_found(self):
        HotSOSConfig.plugin_yaml_defs = HotSOSConfig.data_root
        HotSOSConfig.plugin_name = 'myplugin'

        class MyEventHandler(EventHandlerBase):
            """ Test Handler """
            @property
            def event_group(self):
                return 'mygroup'

        with self.assertRaises(EventCallbackNotFound):
            with GlobalSearcher() as searcher:
                MyEventHandler(global_searcher=searcher).run()

    @utils.create_data_root({'events/myplugin/mygroup.yaml': EVENT_DEF_SIMPLE,
                             'a/path': 'content'})
    def test_events_filter_none(self):
        HotSOSConfig.plugin_yaml_defs = HotSOSConfig.data_root
        HotSOSConfig.plugin_name = 'myplugin'

        class MyEventHandler(EventHandlerBase):
            """ Test Handler """
            @property
            def event_group(self):
                return 'mygroup'

        defs = {'myeventsubgroup': {
                    'event1': ('myplugin.mygroup.myeventgroup.myeventsubgroup.'
                               'event1.search'),
                    'event2': ('myplugin.mygroup.myeventgroup.myeventsubgroup.'
                               'event2.search')}}

        with GlobalSearcher() as searcher:
            handler = MyEventHandler(global_searcher=searcher)

        self.assertEqual(handler.events, defs)
        self.assertEqual(len(handler.searcher.catalog), 1)

    @utils.create_data_root({'events/myplugin/mygroup.yaml': EVENT_DEF_SIMPLE,
                             'a/path': 'content'})
    def test_events_filter_event2(self):
        HotSOSConfig.plugin_yaml_defs = HotSOSConfig.data_root
        HotSOSConfig.event_filter = ('myplugin.mygroup.myeventgroup.'
                                     'myeventsubgroup.event2')
        HotSOSConfig.plugin_name = 'myplugin'

        class MyEventHandler(EventHandlerBase):
            """ Test Handler """
            @property
            def event_group(self):
                return 'mygroup'

        defs = {'myeventsubgroup': {
                    'event2': ('myplugin.mygroup.myeventgroup.myeventsubgroup.'
                               'event2.search')}}
        with GlobalSearcher() as searcher:
            handler = MyEventHandler(global_searcher=searcher)

        self.assertEqual(handler.events, defs)
        self.assertEqual(len(handler.searcher.catalog), 1)

    @utils.create_data_root({'events/myplugin/mygroup.yaml': EVENT_DEF_SIMPLE,
                             'a/path': 'content'})
    def test_events_filter_nonexistent(self):
        HotSOSConfig.plugin_yaml_defs = HotSOSConfig.data_root
        HotSOSConfig.event_filter = 'blahblah'
        HotSOSConfig.plugin_name = 'myplugin'

        class MyEventHandler(EventHandlerBase):
            """ Test Handler """
            @property
            def event_group(self):
                return 'mygroup'

        defs = {}
        with GlobalSearcher() as searcher:
            handler = MyEventHandler(global_searcher=searcher)

        self.assertEqual(handler.events, defs)
        self.assertEqual(len(handler.searcher.catalog), 0)

    def test_processing_utils_key_by_date_true(self):
        info = {}
        results = [{'date': '2000-01-04', 'key': 'f4'},
                   {'date': '2000-01-01', 'key': 'f1'},
                   {'date': '2000-01-01', 'key': 'f3'},
                   {'date': '2000-01-02', 'key': 'f2'}]
        for r in results:
            EventProcessingUtils._get_tally(
                r, info, options=EventProcessingUtils.EventProcessingOptions()
            )
        self.assertEqual(info, {'2000-01-04': {'f4': 1},
                                '2000-01-01': {'f1': 1,
                                               'f3': 1},
                                '2000-01-02': {'f2': 1}})
        ret = EventProcessingUtils._sort_results(
            info, options=EventProcessingUtils.EventProcessingOptions()
        )
        expected = OrderedDict({'2000-01-01': {'f1': 1,
                                               'f3': 1},
                                '2000-01-02': {'f2': 1},
                                '2000-01-04': {'f4': 1}})
        self.assertEqual(ret, expected)
        # check key order
        self.assertEqual(list(ret), list(expected))

    def test_processing_utils_key_by_date_false(self):
        info = {}
        results = [{'date': '2000-01-04', 'key': 'f4'},
                   {'date': '2000-01-01', 'key': 'f1'},
                   {'date': '2000-01-01', 'key': 'f3'},
                   {'date': '2000-01-03', 'key': 'f3'},
                   {'date': '2000-01-02', 'key': 'f2'}]
        for r in results:
            EventProcessingUtils._get_tally(
                r,
                info,
                options=EventProcessingUtils.EventProcessingOptions(
                  key_by_date=False),
            )
        self.assertEqual(info, {'f1': {'2000-01-01': 1},
                                'f2': {'2000-01-02': 1},
                                'f3': {'2000-01-01': 1,
                                       '2000-01-03': 1},
                                'f4': {'2000-01-04': 1}})
        ret = EventProcessingUtils._sort_results(
            info, options=EventProcessingUtils.EventProcessingOptions(
              key_by_date=False)
        )
        expected = OrderedDict({'f4': {'2000-01-04': 1},
                                'f3': {'2000-01-01': 1,
                                       '2000-01-03': 1},
                                'f2': {'2000-01-02': 1},
                                'f1': {'2000-01-01': 1}})
        self.assertEqual(ret, expected)
        # check key order
        self.assertEqual(list(ret), list(expected))

    def test_processing_utils_top5_results(self):
        results = [{'date': '2000-01-01', 'key': '10'},
                   {'date': '2000-01-01', 'key': '9'},
                   {'date': '2000-01-01', 'key': '6'},
                   {'date': '2000-01-01', 'key': '6'},
                   {'date': '2000-01-01', 'key': '2'}]
        options = EventProcessingUtils.EventProcessingOptions(
                                                        max_results_per_date=3)
        ret = EventProcessingUtils.categorise_events('testevent', results,
                                                     options=options)
        expected = OrderedDict({'2000-01-01': {'top3': {
                                                   '10': 1,
                                                   '9': 1,
                                                   '6': 2}, 'total': 4}})
        self.assertEqual(ret, expected)
        # check key order
        self.assertEqual(list(ret), list(expected))
