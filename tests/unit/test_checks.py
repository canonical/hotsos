import os
import tempfile
import yaml

import mock

import utils

from core import checks
from core.ystruct import YAMLDefSection


YAML_DEF_W_INPUT = """
pluginX:
  groupA:
    input:
      type: filesystem
      value: foo/bar1
    sectionA:
      artifactX:
        settings: True
"""

YAML_DEF_W_INPUT_SUPERSEDED = """
pluginX:
  groupA:
    input:
      type: filesystem
      value: foo/bar1
    sectionA:
      input:
        type: filesystem
        value: foo/bar2
      artifactX:
        settings: True
"""

YAML_DEF_W_INPUT_SUPERSEDED2 = """
pluginX:
  groupA:
    input:
      type: filesystem
      value: foo/bar1
    sectionA:
      input:
        type: filesystem
        value: foo/bar2
      artifactX:
        input:
            type: filesystem
            value: foo/bar3
        settings: True
"""

YAML_DEF_EXPR_TYPES = r"""
myplugin:
  mygroup:
    input:
      type: filesystem
      value: {path}
    section1:
      my-sequence-search:
        start: '^hello'
        body: '^\S+'
        end: '^world'
      my-standard-search:
        passthrough-results: True
        start: '^hello'
        end: '^world'
      my-standard-search2:
        expr: '^hello'
        hint: '.+'
      my-standard-search3:
        expr: '^hello'
        hint: '^foo'
"""  # noqa


DUMMY_CONFIG = """
[a-section]
a-key = 1023
"""

YAML_DEF_CONFIG_CHECK = """
myplugin:
  raises: core.issues.issue_types.OpenstackWarning
  mygroup:
    config:
      handler: core.plugins.openstack.OpenstackConfig
      path: dummy.conf
    requires:
      type: apt
      value: a-package
    message: >-
      something important.
    settings:
      a-key:
        section: a-section
        value: 1024
        operator: ge
        allow-unset: False
"""


class TestChecks(utils.BaseTestCase):

    def setUp(self):
        # NOTE: remember that data_root is configured so helpers will always
        # use fake_data_root if possible. If you write a test that wants to
        # test scenario where no data root is set (i.e. no sosreport) you need
        # to unset it as part of the test.
        super().setUp()

    def tearDown(self):
        super().tearDown()

    def test_APTPackageChecksBase_core_only(self):
        expected = {'systemd': '245.4-4ubuntu3.11',
                    'systemd-container': '245.4-4ubuntu3.11',
                    'systemd-sysv': '245.4-4ubuntu3.11',
                    'systemd-timesyncd': '245.4-4ubuntu3.11'}
        obj = checks.APTPackageChecksBase(["systemd"])
        self.assertEqual(obj.all, expected)
        # lookup package already loaded
        self.assertEqual(obj.get_version("systemd"), "245.4-4ubuntu3.11")
        # lookup package not already loaded
        self.assertEqual(obj.get_version("apt"), "2.0.6")

    def test_APTPackageChecksBase_all(self):
        expected = {'python3-systemd': '234-3build2',
                    'systemd': '245.4-4ubuntu3.11',
                    'systemd-container': '245.4-4ubuntu3.11',
                    'systemd-sysv': '245.4-4ubuntu3.11',
                    'systemd-timesyncd': '245.4-4ubuntu3.11'}
        obj = checks.APTPackageChecksBase(["systemd"], ["python3?-systemd"])
        self.assertEqual(obj.all, expected)

    def test_APTPackageChecksBase_formatted(self):
        expected = ['systemd 245.4-4ubuntu3.11',
                    'systemd-container 245.4-4ubuntu3.11',
                    'systemd-sysv 245.4-4ubuntu3.11',
                    'systemd-timesyncd 245.4-4ubuntu3.11']
        obj = checks.APTPackageChecksBase(["systemd"])
        self.assertEqual(obj.all_formatted, expected)

    def test_SnapPackageChecksBase(self):
        expected = {'core': '16-2.48.2'}
        obj = checks.SnapPackageChecksBase(["core"])
        self.assertEqual(obj.all, expected)
        # lookup package already loaded
        self.assertEqual(obj.get_version("core"), "16-2.48.2")
        # lookup package not already loaded
        self.assertEqual(obj.get_version("juju"), "2.7.8")

    def test_SnapPackageChecksBase_formatted(self):
        expected = ['core 16-2.48.2']
        obj = checks.SnapPackageChecksBase(["core"])
        self.assertEqual(obj.all_formatted, expected)

    def test_PackageBugChecksBase(self):
        os.environ['PLUGIN_NAME'] = 'openstack'
        with mock.patch.object(checks, 'add_known_bug') as mock_add_known_bug:
            pkg_info = {'neutron-common': '2:16.4.0-0ubuntu4~cloud0'}
            obj = checks.PackageBugChecksBase('ussuri', pkg_info)
            obj()
            self.assertFalse(mock_add_known_bug.called)

            mock_add_known_bug.reset_mock()
            pkg_info = {'neutron-common': '2:16.4.0-0ubuntu2~cloud0'}
            obj = checks.PackageBugChecksBase('ussuri', pkg_info)
            obj()
            self.assertTrue(mock_add_known_bug.called)

            mock_add_known_bug.reset_mock()
            pkg_info = {'neutron-common': '2:16.2.0-0ubuntu4~cloud0'}
            obj = checks.PackageBugChecksBase('ussuri', pkg_info)
            obj()
            self.assertFalse(mock_add_known_bug.called)

    def test_yaml_def_group_input(self):
        plugin_checks = yaml.safe_load(YAML_DEF_W_INPUT).get('pluginX')
        for name, group in plugin_checks.items():
            overrides = [checks.YAMLDefInput, checks.YAMLDefExpr]
            group = YAMLDefSection(name, group, override_handlers=overrides)
            for entry in group.leaf_sections:
                self.assertEquals(entry.input.type, 'filesystem')
                self.assertEquals(entry.input.path,
                                  os.path.join(checks.constants.DATA_ROOT,
                                               'foo/bar1*'))

    def test_yaml_def_section_input_override(self):
        plugin_checks = yaml.safe_load(YAML_DEF_W_INPUT_SUPERSEDED)
        for name, group in plugin_checks.get('pluginX').items():
            overrides = [checks.YAMLDefInput, checks.YAMLDefExpr]
            group = YAMLDefSection(name, group, override_handlers=overrides)
            for entry in group.leaf_sections:
                self.assertEquals(entry.input.type, 'filesystem')
                self.assertEquals(entry.input.path,
                                  os.path.join(checks.constants.DATA_ROOT,
                                               'foo/bar2*'))

    def test_yaml_def_entry_input_override(self):
        plugin_checks = yaml.safe_load(YAML_DEF_W_INPUT_SUPERSEDED2)
        for name, group in plugin_checks.get('pluginX').items():
            overrides = [checks.YAMLDefInput, checks.YAMLDefExpr]
            group = YAMLDefSection(name, group, override_handlers=overrides)
            for entry in group.leaf_sections:
                self.assertEquals(entry.input.type, 'filesystem')
                self.assertEquals(entry.input.path,
                                  os.path.join(checks.constants.DATA_ROOT,
                                               'foo/bar3*'))

    def test_yaml_def_entry_seq(self):
        with tempfile.TemporaryDirectory() as dtmp:
            os.environ['DATA_ROOT'] = dtmp
            data_file = os.path.join(dtmp, 'data.txt')
            _yaml = YAML_DEF_EXPR_TYPES.format(
                                             path=os.path.basename(data_file))
            open(os.path.join(dtmp, 'events.yaml'), 'w').write(_yaml)
            open(data_file, 'w').write('hello\nbrave\nworld\n')
            plugin_checks = yaml.safe_load(_yaml).get('myplugin')

            overrides = [checks.YAMLDefInput, checks.YAMLDefExpr,
                         checks.YAMLDefResultsPassthrough]
            for name, group in plugin_checks.items():
                group = YAMLDefSection(name, group,
                                       override_handlers=overrides)
                for entry in group.leaf_sections:
                    self.assertEquals(entry.input.type, 'filesystem')
                    self.assertEquals(entry.input.path,
                                      '{}*'.format(data_file))

            test_self = self
            match_count = {'count': 0}
            callbacks_called = {}
            os.environ['PLUGIN_YAML_DEFS'] = dtmp
            os.environ['PLUGIN_NAME'] = 'myplugin'
            EVENTCALLBACKS = checks.CallbackHelper()

            class MyEventHandler(checks.EventChecksBase):
                def __init__(self):
                    super().__init__(yaml_defs_group='mygroup',
                                     callback_helper=EVENTCALLBACKS)

                @EVENTCALLBACKS.callback
                def my_sequence_search(self, event):
                    callbacks_called['my_sequence_search'] = True
                    for section in event.results:
                        for result in section:
                            if result.tag.endswith('-start'):
                                match_count['count'] += 1
                                test_self.assertEquals(result.get(0), 'hello')
                            elif result.tag.endswith('-body'):
                                match_count['count'] += 1
                                test_self.assertEquals(result.get(0), 'brave')
                            elif result.tag.endswith('-end'):
                                match_count['count'] += 1
                                test_self.assertEquals(result.get(0), 'world')

                @EVENTCALLBACKS.callback
                def my_standard_search(self, event):
                    # expected to be passthough results (i.e. raw)
                    callbacks_called['my_standard_search'] = True
                    tag = 'my-standard-search-start'
                    start_results = event.results.find_by_tag(tag)
                    test_self.assertEquals(start_results[0].get(0), 'hello')

                @EVENTCALLBACKS.callback
                def my_standard_search2(self, event):
                    callbacks_called['my_standard_search2'] = True
                    test_self.assertEquals(event.results[0].get(0), 'hello')

                @EVENTCALLBACKS.callback
                def my_standard_search3(self, event):
                    callbacks_called['my_standard_search3'] = True
                    test_self.assertEquals(event.results[0].get(0), 'hello')

                def __call__(self):
                    self.run_checks()

            MyEventHandler()()
            self.assertEquals(match_count['count'], 3)
            self.assertEquals(list(callbacks_called.keys()),
                              ['my_sequence_search',
                               'my_standard_search',
                               'my_standard_search2'])

    @mock.patch('core.issues.issue_utils.add_issue')
    @mock.patch.object(checks, 'APTPackageChecksBase')
    def test_yaml_def_config_requires(self, apt_check, add_issue):
        apt_check.is_installed.return_value = True
        with tempfile.TemporaryDirectory() as dtmp:
            os.environ['DATA_ROOT'] = dtmp
            conf = os.path.join(dtmp, 'dummy.conf')
            with open(conf, 'w') as fd:
                fd.write(DUMMY_CONFIG)

            plugin = yaml.safe_load(YAML_DEF_CONFIG_CHECK).get('myplugin')
            overrides = [checks.YAMLDefInput, checks.YAMLDefExpr,
                         checks.YAMLDefConfig, checks.YAMLDefRequires,
                         checks.YAMLDefSettings, checks.YAMLDefMessage,
                         checks.YAMLDefIssueType]
            group = YAMLDefSection('myplugin', plugin,
                                   override_handlers=overrides)
            for entry in group.leaf_sections:
                self.assertTrue(entry.requires.passes)

            os.environ['PLUGIN_YAML_DEFS'] = dtmp
            open(os.path.join(dtmp, 'config_checks.yaml'),
                 'w').write(YAML_DEF_CONFIG_CHECK)
            os.environ['PLUGIN_NAME'] = 'myplugin'
            checks.ConfigChecksBase()()
            self.assertTrue(add_issue.called)
