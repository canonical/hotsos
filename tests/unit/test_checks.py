import os
import tempfile
import yaml

import mock

import utils

from core import checks
from core import ycheck
from core.ycheck import (
    YDefsSection,
    bugs,
    events,
    configs,
    scenarios
)
from core.searchtools import FileSearcher, SearchDef


YAML_DEF_W_INPUT = """
pluginX:
  groupA:
    input:
      path: foo/bar1
    sectionA:
      artifactX:
        settings: True
"""

YAML_DEF_REQUIRES_GROUPED = """
passdef:
  requires:
    and:
      - apt: systemd
    or:
      - apt: nova-compute
    not:
      - apt: blah
faildef:
  requires:
    and:
      - apt: doo
      - apt: daa
    or:
      - apt: nova-compute
    not:
      - apt: blah
      - apt: nova-compute
"""

YAML_DEF_W_INPUT_SUPERSEDED = """
pluginX:
  groupA:
    input:
      path: foo/bar1
    sectionA:
      input:
        path: foo/bar2
      artifactX:
        settings: True
"""

YAML_DEF_W_INPUT_SUPERSEDED2 = """
pluginX:
  groupA:
    input:
      path: foo/bar1
    sectionA:
      input:
        path: foo/bar2
      artifactX:
        input:
          path: foo/bar3
        settings: True
"""

YAML_DEF_EXPR_TYPES = r"""
myplugin:
  mygroup:
    input:
      path: {path}
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
  mygroup:
    config:
      handler: core.plugins.openstack.OpenstackConfig
      path: dummy.conf
    requires:
      apt: a-package
    raises:
      type: core.issues.issue_types.OpenstackWarning
      message: >-
        something important.
    settings:
      a-key:
        section: a-section
        value: 1024
        operator: ge
        allow-unset: False
"""

SCENARIO_CHECKS = r"""
myplugin:
  myscenario:
    checks:
      logmatch:
        input:
          path: foo.log
        expr: '^([0-9-]+)\S* (\S+) .+'
        meta:
          min: 3
          period: 24
      aptexists:
        requires:
          apt: nova-compute
      snapexists:
        requires:
          snap: core18
      serviceexists:
        requires:
          systemd: nova-compute
          value: enabled
          op: eq
      servicenotstatus:
        requires:
          systemd: nova-compute
          value: enabled
          op: ne
    conclusions:
      justlog:
        priority: 1
        decision: logmatch
        raises:
          type: core.issues.issue_types.SystemWarning
          message: log matched
      logandsnap:
        priority: 2
        decision:
            and:
                - logmatched
                - snapexists
        raises:
          type: core.issues.issue_types.SystemWarning
          message: log matched and snap exists
      logandsnapandservice:
        priority: 3
        decision:
            and:
                - logmatched
                - snapexists
                - serviceexists
        raises:
          type: core.issues.issue_types.SystemWarning
          message: log matched, snap and service exists
"""  # noqa


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

    @mock.patch('core.plugins.openstack.OpenstackBase')
    @mock.patch.object(bugs, 'add_known_bug')
    def test_YBugChecker(self, mock_add_known_bug, mock_base):
        bugs_found = []

        def fake_add_known_bug(id, _msg):
            bugs_found.append(id)

        mock_add_known_bug.side_effect = fake_add_known_bug
        os.environ['PLUGIN_NAME'] = 'openstack'
        mock_ost_base = mock.MagicMock()
        mock_base.return_value = mock_ost_base
        mock_ost_base.apt_packages_all = {'neutron-common':
                                          '2:16.4.0-0ubuntu4~cloud0'}
        # reset
        bugs_found = []
        obj = bugs.YBugChecker()
        obj()
        self.assertFalse('1927868' in bugs_found)

        mock_ost_base.apt_packages_all = {'neutron-common':
                                          '2:16.4.0-0ubuntu2~cloud0'}
        # reset
        bugs_found = []
        obj = bugs.YBugChecker()
        obj()
        self.assertTrue('1927868' in bugs_found)

        mock_ost_base.apt_packages_all = {'neutron-common':
                                          '2:16.2.0-0ubuntu4~cloud0'}
        # reset
        bugs_found = []
        obj = bugs.YBugChecker()
        obj()
        self.assertFalse('1927868' in bugs_found)

    def test_yaml_def_group_input(self):
        plugin_checks = yaml.safe_load(YAML_DEF_W_INPUT).get('pluginX')
        for name, group in plugin_checks.items():
            group = YDefsSection(name, group)
            for entry in group.leaf_sections:
                self.assertEqual(entry.input.path,
                                 os.path.join(checks.constants.DATA_ROOT,
                                              'foo/bar1*'))

    def test_yaml_def_requires_grouped(self):
        mydef = YDefsSection('mydef',
                             yaml.safe_load(YAML_DEF_REQUIRES_GROUPED))
        tested = 0
        for entry in mydef.leaf_sections:
            if entry.name == 'passdef':
                tested += 1
                self.assertTrue(entry.requires.passes)
            elif entry.name == 'faildef':
                tested += 1
                self.assertFalse(entry.requires.passes)

        self.assertEqual(tested, 2)

    def test_yaml_def_section_input_override(self):
        plugin_checks = yaml.safe_load(YAML_DEF_W_INPUT_SUPERSEDED)
        for name, group in plugin_checks.get('pluginX').items():
            group = YDefsSection(name, group)
            for entry in group.leaf_sections:
                self.assertEqual(entry.input.path,
                                 os.path.join(checks.constants.DATA_ROOT,
                                              'foo/bar2*'))

    def test_yaml_def_entry_input_override(self):
        plugin_checks = yaml.safe_load(YAML_DEF_W_INPUT_SUPERSEDED2)
        for name, group in plugin_checks.get('pluginX').items():
            group = YDefsSection(name, group)
            for entry in group.leaf_sections:
                self.assertEqual(entry.input.path,
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
            for name, group in plugin_checks.items():
                group = YDefsSection(name, group)
                for entry in group.leaf_sections:
                    self.assertEqual(entry.input.path,
                                     '{}*'.format(data_file))

            test_self = self
            match_count = {'count': 0}
            callbacks_called = {}
            os.environ['PLUGIN_YAML_DEFS'] = dtmp
            os.environ['PLUGIN_NAME'] = 'myplugin'
            EVENTCALLBACKS = ycheck.CallbackHelper()

            class MyEventHandler(events.YEventCheckerBase):
                def __init__(self):
                    super().__init__(yaml_defs_group='mygroup',
                                     searchobj=FileSearcher(),
                                     callback_helper=EVENTCALLBACKS)

                @EVENTCALLBACKS.callback()
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

                @EVENTCALLBACKS.callback()
                def my_standard_search(self, event):
                    # expected to be passthough results (i.e. raw)
                    callbacks_called[event.name] = True
                    tag = 'my-standard-search-start'
                    start_results = event.results.find_by_tag(tag)
                    test_self.assertEqual(start_results[0].get(0), 'hello')

                @EVENTCALLBACKS.callback('my-standard-search2',
                                         'my-standard-search3')
                def my_standard_search_common(self, event):
                    callbacks_called[event.name] = True
                    test_self.assertEqual(event.results[0].get(0), 'hello')

                def __call__(self):
                    self.run_checks()

            MyEventHandler()()
            self.assertEqual(match_count['count'], 3)
            self.assertEqual(list(callbacks_called.keys()),
                             ['my-sequence-search',
                              'my-standard-search',
                              'my-standard-search2'])

    @mock.patch('core.issues.issue_utils.add_issue')
    @mock.patch.object(ycheck, 'APTPackageChecksBase')
    def test_yaml_def_config_requires(self, apt_check, add_issue):
        apt_check.is_installed.return_value = True
        with tempfile.TemporaryDirectory() as dtmp:
            os.environ['DATA_ROOT'] = dtmp
            conf = os.path.join(dtmp, 'dummy.conf')
            with open(conf, 'w') as fd:
                fd.write(DUMMY_CONFIG)

            plugin = yaml.safe_load(YAML_DEF_CONFIG_CHECK).get('myplugin')
            group = YDefsSection('myplugin', plugin)
            for entry in group.leaf_sections:
                self.assertTrue(entry.requires.passes)

            os.environ['PLUGIN_YAML_DEFS'] = dtmp
            open(os.path.join(dtmp, 'config_checks.yaml'),
                 'w').write(YAML_DEF_CONFIG_CHECK)
            os.environ['PLUGIN_NAME'] = 'myplugin'
            configs.YConfigChecker()()
            self.assertTrue(add_issue.called)

    @mock.patch('core.issues.issue_utils.add_issue')
    @mock.patch.object(ycheck, 'APTPackageChecksBase')
    def test_yaml_def_scenarios_no_issue(self, apt_check, add_issue):
        apt_check.is_installed.return_value = True
        os.environ['PLUGIN_NAME'] = 'juju'
        scenarios.YScenarioChecker()()
        self.assertFalse(add_issue.called)

    def test_yaml_def_scenario_checks_false(self):
        with tempfile.TemporaryDirectory() as dtmp:
            os.environ['DATA_ROOT'] = dtmp
            os.environ['PLUGIN_YAML_DEFS'] = dtmp
            os.environ['PLUGIN_NAME'] = 'myplugin'
            logfile = os.path.join(dtmp, 'foo.log')
            open(os.path.join(dtmp, 'scenarios.yaml'), 'w').write(
                                                               SCENARIO_CHECKS)
            contents = ['2021-04-01 00:31:00.000 an event\n']
            self._create_search_results(logfile, contents)
            checker = scenarios.YScenarioChecker()
            checker.load()
            self.assertEqual(len(checker.scenarios), 1)
            for scenario in checker.scenarios:
                for check in scenario.checks.values():
                    self.assertFalse(check.result)

    def test_yaml_def_scenario_checks_requires(self):
        with tempfile.TemporaryDirectory() as dtmp:
            os.environ['PLUGIN_YAML_DEFS'] = dtmp
            os.environ['PLUGIN_NAME'] = 'myplugin'
            open(os.path.join(dtmp, 'scenarios.yaml'), 'w').write(
                                                               SCENARIO_CHECKS)
            checker = scenarios.YScenarioChecker()
            checker.load()
            self.assertEqual(len(checker.scenarios), 1)
            checked = 0
            for scenario in checker.scenarios:
                for check in scenario.checks.values():
                    if check.name == 'aptexists':
                        checked += 1
                        self.assertTrue(check.result)
                    elif check.name == 'snapexists':
                        checked += 1
                        self.assertTrue(check.result)
                    elif check.name == 'serviceexists':
                        checked += 1
                        self.assertTrue(check.result)
                    elif check.name == 'servicenotstatus':
                        checked += 1
                        self.assertFalse(check.result)

            self.assertEquals(checked, 4)

    def test_yaml_def_scenario_checks_expr(self):
        with tempfile.TemporaryDirectory() as dtmp:
            os.environ['DATA_ROOT'] = dtmp
            os.environ['PLUGIN_YAML_DEFS'] = dtmp
            os.environ['PLUGIN_NAME'] = 'myplugin'
            logfile = os.path.join(dtmp, 'foo.log')
            open(os.path.join(dtmp, 'scenarios.yaml'), 'w').write(
                                                               SCENARIO_CHECKS)
            contents = ['2021-04-01 00:31:00.000 an event\n',
                        '2021-04-01 00:32:00.000 an event\n',
                        '2021-04-01 00:33:00.000 an event\n',
                        '2021-04-02 00:36:00.000 an event\n',
                        '2021-04-02 00:00:00.000 an event\n',
                        ]
            self._create_search_results(logfile, contents)
            checker = scenarios.YScenarioChecker()
            checker.load()
            self.assertEqual(len(checker.scenarios), 1)
            for scenario in checker.scenarios:
                for check in scenario.checks.values():
                    if check.name == 'logmatch':
                        self.assertTrue(check.result)

    def _create_search_results(self, path, contents):
        with open(path, 'w') as fd:
            for line in contents:
                fd.write(line)

        s = FileSearcher()
        s.add_search_term(SearchDef(r'^(\S+) (\S+) .+', tag='all'), path)
        return s.search().find_by_tag('all')

    def test_yaml_def_scenario_datetime(self):
        with tempfile.TemporaryDirectory() as dtmp:
            os.environ['DATA_ROOT'] = dtmp
            os.environ['PLUGIN_YAML_DEFS'] = dtmp
            os.environ['PLUGIN_NAME'] = 'myplugin'
            logfile = os.path.join(dtmp, 'foo.log')

            contents = ['2021-04-01 00:01:00.000 an event\n']
            results = self._create_search_results(logfile, contents)
            result = scenarios.ScenarioCheck.filter_by_period(results, 24, 1)
            self.assertEqual(len(result), 1)

            result = scenarios.ScenarioCheck.filter_by_period(results, 24, 2)
            self.assertEqual(len(result), 0)

            contents = ['2021-04-01 00:01:00.000 an event\n',
                        '2021-04-01 00:02:00.000 an event\n',
                        '2021-04-03 00:01:00.000 an event\n',
                        ]
            results = self._create_search_results(logfile, contents)
            result = scenarios.ScenarioCheck.filter_by_period(results, 24, 2)
            self.assertEqual(len(result), 2)

            contents = ['2021-04-01 00:00:00.000 an event\n',
                        '2021-04-01 00:01:00.000 an event\n',
                        '2021-04-01 00:02:00.000 an event\n',
                        '2021-04-02 00:00:00.000 an event\n',
                        '2021-04-02 00:01:00.000 an event\n',
                        ]
            results = self._create_search_results(logfile, contents)
            result = scenarios.ScenarioCheck.filter_by_period(results, 24, 4)
            self.assertEqual(len(result), 4)

            contents = ['2021-04-01 00:00:00.000 an event\n',
                        '2021-04-01 00:01:00.000 an event\n',
                        '2021-04-02 00:01:00.000 an event\n',
                        '2021-04-02 00:02:00.000 an event\n',
                        ]
            results = self._create_search_results(logfile, contents)
            result = scenarios.ScenarioCheck.filter_by_period(results, 24, 4)
            self.assertEqual(len(result), 0)

            contents = ['2021-04-01 00:00:00.000 an event\n',
                        '2021-04-01 00:01:00.000 an event\n',
                        '2021-04-02 02:00:00.000 an event\n',
                        '2021-04-03 01:00:00.000 an event\n',
                        '2021-04-04 02:00:00.000 an event\n',
                        '2021-04-05 02:00:00.000 an event\n',
                        '2021-04-06 01:00:00.000 an event\n',
                        ]
            results = self._create_search_results(logfile, contents)
            result = scenarios.ScenarioCheck.filter_by_period(results, 24, 3)
            self.assertEqual(len(result), 3)

    def test_fs_override_inheritance(self):
        """
        When a directory is used to group definitions and overrides are
        provided in a <dirname>.yaml file, we need to make sure those overrides
        do not supersceded overrides of the same type used by definitions in
        the same directory.
        """
        with tempfile.TemporaryDirectory() as dtmp:
            os.environ['DATA_ROOT'] = dtmp
            os.environ['PLUGIN_YAML_DEFS'] = dtmp
            os.environ['PLUGIN_NAME'] = 'myplugin'
            overrides = os.path.join(dtmp, 'mytype', 'myplugin', 'mytype.yaml')
            defs = os.path.join(dtmp, 'mytype', 'myplugin', 'defs.yaml')
            os.makedirs(os.path.dirname(overrides))

            with open(overrides, 'w') as fd:
                fd.write("requires:\n")
                fd.write("  property: foo\n")

            with open(defs, 'w') as fd:
                fd.write("foo: bar\n")

            expected = {'mytype': {
                            'requires': {
                                'property': 'foo'}},
                        'defs': {'foo': 'bar'}}
            self.assertEqual(ycheck.YDefsLoader('mytype').load_plugin_defs(),
                             expected)

            with open(defs, 'a') as fd:
                fd.write("requires:\n")
                fd.write("  apt: apackage\n")

            expected = {'mytype': {
                            'requires': {
                                'property': 'foo'}},
                        'defs': {
                            'foo': 'bar',
                            'requires': {
                                'apt': 'apackage'}}}
            self.assertEqual(ycheck.YDefsLoader('mytype').load_plugin_defs(),
                             expected)

    @mock.patch('core.plugins.openstack.OpenstackChecksBase')
    def test_requires_grouped(self, mock_plugin):
        mock_plugin.return_value = mock.MagicMock()
        r1 = {'property': 'core.plugins.openstack.OpenstackChecksBase.r1'}
        r2 = {'property': 'core.plugins.openstack.OpenstackChecksBase.r2'}
        r3 = {'property': 'core.plugins.openstack.OpenstackChecksBase.r3'}
        requires = {'requires': {'or': [r1, r2]}}

        mock_plugin.return_value.r1 = False
        mock_plugin.return_value.r2 = False
        group = YDefsSection('test', requires)
        self.assertFalse(group.leaf_sections[0].requires.passes)

        mock_plugin.return_value.r1 = True
        mock_plugin.return_value.r2 = False
        group = YDefsSection('test', requires)
        self.assertTrue(group.leaf_sections[0].requires.passes)

        mock_plugin.return_value.r1 = True
        mock_plugin.return_value.r2 = True
        group = YDefsSection('test', requires)
        self.assertTrue(group.leaf_sections[0].requires.passes)

        requires = {'requires': {'and': [r1, r2]}}

        mock_plugin.return_value.r1 = False
        mock_plugin.return_value.r2 = False
        group = YDefsSection('test', requires)
        self.assertFalse(group.leaf_sections[0].requires.passes)

        mock_plugin.return_value.r1 = True
        mock_plugin.return_value.r2 = False
        group = YDefsSection('test', requires)
        self.assertFalse(group.leaf_sections[0].requires.passes)

        mock_plugin.return_value.r1 = True
        mock_plugin.return_value.r2 = True
        group = YDefsSection('test', requires)
        self.assertTrue(group.leaf_sections[0].requires.passes)

        requires = {'requires': {'and': [r1, r2],
                                 'or': [r1, r2]}}

        mock_plugin.return_value.r1 = True
        mock_plugin.return_value.r2 = False
        group = YDefsSection('test', requires)
        self.assertFalse(group.leaf_sections[0].requires.passes)

        mock_plugin.return_value.r1 = True
        mock_plugin.return_value.r2 = True
        group = YDefsSection('test', requires)
        self.assertTrue(group.leaf_sections[0].requires.passes)

        requires = {'requires': {'and': [r1, r2],
                                 'or': [r1, r2]}}

        mock_plugin.return_value.r1 = True
        mock_plugin.return_value.r2 = False
        group = YDefsSection('test', requires)
        self.assertFalse(group.leaf_sections[0].requires.passes)

        requires = {'requires': {'and': [r3],
                                 'or': [r1, r2]}}

        mock_plugin.return_value.r1 = True
        mock_plugin.return_value.r2 = False
        mock_plugin.return_value.r3 = True
        group = YDefsSection('test', requires)
        self.assertTrue(group.leaf_sections[0].requires.passes)

    def test_bugs_handler_pkg_check(self):
        versions = [{'min-broken': '5.0', 'min-fixed': '5.2'},
                    {'min-broken': '4.0', 'min-fixed': '4.2'},
                    {'min-broken': '3.0', 'min-fixed': '3.2'}]
        self.assertTrue(bugs.YBugChecker()._package_has_bugfix('2.0',
                                                               versions))
        self.assertFalse(bugs.YBugChecker()._package_has_bugfix('3.0',
                                                                versions))
        self.assertFalse(bugs.YBugChecker()._package_has_bugfix('4.0',
                                                                versions))
        self.assertFalse(bugs.YBugChecker()._package_has_bugfix('5.0',
                                                                versions))
        self.assertTrue(bugs.YBugChecker()._package_has_bugfix('5.2',
                                                               versions))
        self.assertTrue(bugs.YBugChecker()._package_has_bugfix('5.3',
                                                               versions))
        self.assertTrue(bugs.YBugChecker()._package_has_bugfix('6.0',
                                                               versions))
