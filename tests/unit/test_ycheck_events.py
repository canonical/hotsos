import os

import yaml
from hotsos.core.config import HotSOSConfig
from hotsos.core.ycheck.engine import YDefsSection
from hotsos.core.ycheck.events import (
    EventHandlerBase,
    EventCallbackBase,
    EventCallbackNotFound,
)

from . import utils

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
myplugin:
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


class TestYamlEvents(utils.BaseTestCase):

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
                self.assertEqual(entry.input.paths,
                                 ['{}*'.format(data_file)])

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
            event_group = 'mygroup'
            event_names = ['my-sequence-search', 'my-passthrough-search',
                           'my-pass-search', 'my-fail-search1',
                           'my-fail-search2']

            def my_sequence_search(self, event):
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

            def my_passthrough_search(self, event):
                # expected to be passthough results (i.e. raw)
                callbacks_called[event.name] = True
                tag = '{}-start'.format(event.search_tag)
                start_results = event.results.find_by_tag(tag)
                test_self.assertEqual(start_results[0].get(0), 'hello')

            def __call__(self, event):
                callbacks_called[event.name] = True
                if event.name == 'my-sequence-search':
                    return self.my_sequence_search(event)

                if event.name == 'my-passthrough-search':
                    return self.my_passthrough_search(event)

                test_self.assertEqual(event.results[0].get(0), 'hello')

        class MyEventHandler(EventHandlerBase):

            @property
            def event_group(self):
                return 'mygroup'

        MyEventHandler().load_and_run()
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

            @property
            def event_group(self):
                return 'mygroup'

        with self.assertRaises(EventCallbackNotFound):
            MyEventHandler().load_and_run()

    @utils.create_data_root({'events/myplugin/mygroup.yaml': EVENT_DEF_SIMPLE})
    def test_events_filter_none(self):
        HotSOSConfig.plugin_yaml_defs = HotSOSConfig.data_root
        HotSOSConfig.plugin_name = 'myplugin'

        class MyEventHandler(EventHandlerBase):

            @property
            def event_group(self):
                return 'mygroup'

        prefix = 'mygroup.myplugin.myeventgroup.myeventsubgroup'
        defs = {'myeventsubgroup': {
                    'event1': {
                        'passthrough': False,
                        'sequence': None,
                        'tag': prefix + '.event1.search'},
                    'event2': {
                        'passthrough': False,
                        'sequence': None,
                        'tag': prefix + '.event2.search'}}}
        self.assertEqual(MyEventHandler().event_definitions, defs)

    @utils.create_data_root({'events/myplugin/mygroup.yaml': EVENT_DEF_SIMPLE})
    def test_events_filter_event2(self):
        HotSOSConfig.plugin_yaml_defs = HotSOSConfig.data_root
        HotSOSConfig.event_filter = 'myplugin.myeventsubgroup.event2'
        HotSOSConfig.plugin_name = 'myplugin'

        class MyEventHandler(EventHandlerBase):

            @property
            def event_group(self):
                return 'mygroup'

        prefix = 'mygroup.myplugin.myeventgroup.myeventsubgroup'
        defs = {'myeventsubgroup': {
                    'event2': {
                        'passthrough': False,
                        'sequence': None,
                        'tag': prefix + '.event2.search'}}}
        self.assertEqual(MyEventHandler().event_definitions, defs)

    @utils.create_data_root({'events/myplugin/mygroup.yaml': EVENT_DEF_SIMPLE})
    def test_events_filter_nonexistent(self):
        HotSOSConfig.plugin_yaml_defs = HotSOSConfig.data_root
        HotSOSConfig.event_filter = 'blahblah'
        HotSOSConfig.plugin_name = 'myplugin'

        class MyEventHandler(EventHandlerBase):

            @property
            def event_group(self):
                return 'mygroup'

        defs = {}
        self.assertEqual(MyEventHandler().event_definitions, defs)
