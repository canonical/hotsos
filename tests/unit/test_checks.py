import os
import tempfile

import mock
import yaml

from . import utils

from hotsos.core.config import setup_config, HotSOSConfig
from hotsos.core import checks
from hotsos.core import ycheck
from hotsos.core.ycheck import (
    YDefsSection,
    YPropertyCheck,
    bugs,
    events,
    scenarios
)
from hotsos.core.searchtools import FileSearcher, SearchDef


YAML_DEF_W_INPUT = """
pluginX:
  groupA:
    input:
      path: foo/bar1
    sectionA:
      artifactX:
        requires:
          apt: foo
"""

YAML_DEF_REQUIRES_APT = """
pluginX:
  groupA:
    requires:
      apt:
        mypackage:
          - min: '3.0'
            max: '3.2'
          - min: '4.0'
            max: '4.2'
          - min: '5.0'
            max: '5.2'
"""

YAML_DEF_REQUIRES_GROUPED = """
passdef1:
  requires:
    - apt: python3.8
    - and:
        - apt: systemd
      or:
        - apt: nova-compute
      not:
        - apt: blah
passdef2:
  requires:
    and:
      - apt: systemd
    or:
      - apt: nova-compute
    not:
      - apt: blah
faildef1:
  requires:
    - and:
        - apt: doo
        - apt: daa
      or:
        - apt: nova-compute
      not:
        - apt: blah
        - apt: nova-compute
faildef2:
  requires:
    - apt: python3.8
    - apt: python1.0
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
        requires:
          apt: foo
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
        requires:
          apt: foo
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

SCENARIO_CHECKS = r"""
myplugin:
  myscenario:
    checks:
      logmatch:
        input:
          path: foo.log
        expr: '^([0-9-]+)\S* (\S+) .+'
        check-parameters:
          min-results: 3
          search-period-hours: 24
      aptexists:
        requires:
          apt: nova-compute
      snapexists:
        requires:
          snap: core20
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
          type: hotsos.core.issues.SystemWarning
          message: log matched {num} times
          format-dict:
            num: '@checks.logmatch.expr.results:len'
      logandsnap:
        priority: 2
        decision:
            and:
                - logmatch
                - snapexists
        raises:
          type: hotsos.core.issues.SystemWarning
          message: log matched {num} times and snap exists
          format-dict:
            num: '@checks.logmatch.expr.results:len'
      logandsnapandservice:
        priority: 3
        decision:
            and:
                - logmatch
                - snapexists
                - serviceexists
        raises:
          type: hotsos.core.issues.SystemWarning
          message: log matched {num} times, snap and service exists
          format-dict:
            num: '@checks.logmatch.expr.results:len'
"""  # noqa


class TestChecks(utils.BaseTestCase):

    def setUp(self):
        # NOTE: remember that data_root is configured so helpers will always
        # use fake_data_root if possible. If you write a test that wants to
        # test scenario where no data root is set (i.e. no sosreport) you need
        # to unset it as part of the test.
        super().setUp()

    def test_APTPackageChecksBase_core_only(self):
        expected = {'systemd': '245.4-4ubuntu3.15',
                    'systemd-container': '245.4-4ubuntu3.15',
                    'systemd-sysv': '245.4-4ubuntu3.15',
                    'systemd-timesyncd': '245.4-4ubuntu3.15'}
        obj = checks.APTPackageChecksBase(["systemd"])
        self.assertEqual(obj.all, expected)
        # lookup package already loaded
        self.assertEqual(obj.get_version("systemd"), "245.4-4ubuntu3.15")
        # lookup package not already loaded
        self.assertEqual(obj.get_version("apt"), "2.0.6")

    def test_APTPackageChecksBase_all(self):
        expected = {'python3-systemd': '234-3build2',
                    'systemd': '245.4-4ubuntu3.15',
                    'systemd-container': '245.4-4ubuntu3.15',
                    'systemd-sysv': '245.4-4ubuntu3.15',
                    'systemd-timesyncd': '245.4-4ubuntu3.15'}
        obj = checks.APTPackageChecksBase(["systemd"], ["python3?-systemd"])
        self.assertEqual(obj.all, expected)

    def test_APTPackageChecksBase_formatted(self):
        expected = ['systemd 245.4-4ubuntu3.15',
                    'systemd-container 245.4-4ubuntu3.15',
                    'systemd-sysv 245.4-4ubuntu3.15',
                    'systemd-timesyncd 245.4-4ubuntu3.15']
        obj = checks.APTPackageChecksBase(["systemd"])
        self.assertEqual(obj.all_formatted, expected)

    def test_SnapPackageChecksBase(self):
        expected = {'core20': '20220114'}
        obj = checks.SnapPackageChecksBase(["core20"])
        self.assertEqual(obj.all, expected)
        # lookup package already loaded
        self.assertEqual(obj.get_version("core20"), "20220114")
        # lookup package not already loaded
        self.assertEqual(obj.get_version("lxd"), "4.22")

    def test_SnapPackageChecksBase_formatted(self):
        expected = ['core20 20220114']
        obj = checks.SnapPackageChecksBase(["core20"])
        self.assertEqual(obj.all_formatted, expected)

    @mock.patch('hotsos.core.ycheck.APTPackageChecksBase')
    @mock.patch.object(bugs, 'add_known_bug')
    def test_YBugChecker(self, mock_add_known_bug, mock_apt):
        bugs_found = []

        def fake_add_known_bug(id, _msg):
            bugs_found.append(id)

        mock_add_known_bug.side_effect = fake_add_known_bug
        setup_config(PLUGIN_NAME='openstack')
        mock_apt.return_value = mock.MagicMock()
        mock_apt.return_value.is_installed.return_value = True
        mock_apt.return_value.get_version.return_value = \
            '2:16.4.0-0ubuntu4~cloud0'
        # reset
        bugs_found = []
        obj = bugs.YBugChecker()
        obj()
        self.assertFalse('1927868' in bugs_found)

        mock_apt.return_value.get_version.return_value = \
            '2:16.4.0-0ubuntu2~cloud0'
        # reset
        bugs_found = []
        obj = bugs.YBugChecker()
        obj()
        self.assertTrue('1927868' in bugs_found)

        mock_apt.return_value.get_version.return_value = \
            '2:16.2.0-0ubuntu4~cloud0'
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
                                 os.path.join(HotSOSConfig.DATA_ROOT,
                                              'foo/bar1*'))

    def test_yaml_def_requires_grouped(self):
        mydef = YDefsSection('mydef',
                             yaml.safe_load(YAML_DEF_REQUIRES_GROUPED))
        tested = 0
        for entry in mydef.leaf_sections:
            if entry.name == 'passdef1':
                tested += 1
                self.assertTrue(entry.requires.passes)
            elif entry.name == 'passdef2':
                tested += 1
                self.assertTrue(entry.requires.passes)
            elif entry.name == 'faildef1':
                tested += 1
                self.assertFalse(entry.requires.passes)
            elif entry.name == 'faildef2':
                tested += 1
                self.assertFalse(entry.requires.passes)

        self.assertEqual(tested, 4)

    def test_yaml_def_section_input_override(self):
        plugin_checks = yaml.safe_load(YAML_DEF_W_INPUT_SUPERSEDED)
        for name, group in plugin_checks.get('pluginX').items():
            group = YDefsSection(name, group)
            for entry in group.leaf_sections:
                self.assertEqual(entry.input.path,
                                 os.path.join(HotSOSConfig.DATA_ROOT,
                                              'foo/bar2*'))

    def test_yaml_def_entry_input_override(self):
        plugin_checks = yaml.safe_load(YAML_DEF_W_INPUT_SUPERSEDED2)
        for name, group in plugin_checks.get('pluginX').items():
            group = YDefsSection(name, group)
            for entry in group.leaf_sections:
                self.assertEqual(entry.input.path,
                                 os.path.join(HotSOSConfig.DATA_ROOT,
                                              'foo/bar3*'))

    def test_yaml_def_entry_seq(self):
        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(DATA_ROOT=dtmp)
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
            setup_config(PLUGIN_YAML_DEFS=dtmp, PLUGIN_NAME='myplugin')
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

    @mock.patch('hotsos.core.issues.utils.add_issue')
    @mock.patch.object(ycheck, 'APTPackageChecksBase')
    def test_yaml_def_scenarios_no_issue(self, apt_check, add_issue):
        apt_check.is_installed.return_value = True
        setup_config(PLUGIN_NAME='juju')
        scenarios.YScenarioChecker()()
        self.assertFalse(add_issue.called)

    @mock.patch('hotsos.core.issues.utils.add_issue')
    def test_yaml_def_scenario_checks_false(self, mock_add_issue):
        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(PLUGIN_YAML_DEFS=dtmp, DATA_ROOT=dtmp,
                         PLUGIN_NAME='myplugin')
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

            # now run the scenarios
            checker()

        self.assertFalse(mock_add_issue.called)

    @mock.patch('hotsos.core.issues.utils.add_issue')
    def test_yaml_def_scenario_checks_requires(self, mock_add_issue):
        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(PLUGIN_YAML_DEFS=dtmp, PLUGIN_NAME='myplugin')
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

            self.assertEqual(checked, 4)

            # now run the scenarios
            checker()

        self.assertFalse(mock_add_issue.called)

    @mock.patch('hotsos.core.issues.utils.add_issue')
    def test_yaml_def_scenario_checks_expr(self, mock_add_issue):
        issues = []

        def fake_add_issue(issue):
            issues.append(issue)

        mock_add_issue.side_effect = fake_add_issue
        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(PLUGIN_YAML_DEFS=dtmp, DATA_ROOT=dtmp,
                         PLUGIN_NAME='myplugin')
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

            # now run the scenarios
            checker.run()

        self.assertTrue(mock_add_issue.called)
        msg = ("log matched 5 times")
        self.assertEqual([issue.msg for issue in issues], [msg])

    def _create_search_results(self, path, contents):
        with open(path, 'w') as fd:
            for line in contents:
                fd.write(line)

        s = FileSearcher()
        s.add_search_term(SearchDef(r'^(\S+) (\S+) .+', tag='all'), path)
        return s.search().find_by_tag('all')

    def test_yaml_def_scenario_datetime(self):
        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(PLUGIN_YAML_DEFS=dtmp, DATA_ROOT=dtmp,
                         PLUGIN_NAME='myplugin')
            logfile = os.path.join(dtmp, 'foo.log')

            contents = ['2021-04-01 00:01:00.000 an event\n']
            results = self._create_search_results(logfile, contents)
            result = YPropertyCheck.filter_by_period(results, 24, 1)
            self.assertEqual(len(result), 1)

            result = YPropertyCheck.filter_by_period(results, 24, 2)
            self.assertEqual(len(result), 0)

            contents = ['2021-04-01 00:01:00.000 an event\n',
                        '2021-04-01 00:02:00.000 an event\n',
                        '2021-04-03 00:01:00.000 an event\n',
                        ]
            results = self._create_search_results(logfile, contents)
            result = YPropertyCheck.filter_by_period(results, 24, 2)
            self.assertEqual(len(result), 2)

            contents = ['2021-04-01 00:00:00.000 an event\n',
                        '2021-04-01 00:01:00.000 an event\n',
                        '2021-04-01 00:02:00.000 an event\n',
                        '2021-04-02 00:00:00.000 an event\n',
                        '2021-04-02 00:01:00.000 an event\n',
                        ]
            results = self._create_search_results(logfile, contents)
            result = YPropertyCheck.filter_by_period(results, 24, 4)
            self.assertEqual(len(result), 4)

            contents = ['2021-04-01 00:00:00.000 an event\n',
                        '2021-04-01 00:01:00.000 an event\n',
                        '2021-04-02 00:01:00.000 an event\n',
                        '2021-04-02 00:02:00.000 an event\n',
                        ]
            results = self._create_search_results(logfile, contents)
            result = YPropertyCheck.filter_by_period(results, 24, 4)
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
            result = YPropertyCheck.filter_by_period(results, 24, 3)
            self.assertEqual(len(result), 3)

    def test_fs_override_inheritance(self):
        """
        When a directory is used to group definitions and overrides are
        provided in a <dirname>.yaml file, we need to make sure those overrides
        do not supersceded overrides of the same type used by definitions in
        the same directory.
        """
        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(PLUGIN_YAML_DEFS=dtmp, DATA_ROOT=dtmp,
                         PLUGIN_NAME='myplugin')
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

    @mock.patch('hotsos.core.plugins.openstack.OpenstackChecksBase')
    def test_requires_grouped(self, mock_plugin):
        mock_plugin.return_value = mock.MagicMock()
        r1 = {'property':
              'hotsos.core.plugins.openstack.OpenstackChecksBase.r1'}
        r2 = {'property':
              'hotsos.core.plugins.openstack.OpenstackChecksBase.r2'}
        r3 = {'property':
              'hotsos.core.plugins.openstack.OpenstackChecksBase.r3'}
        requires = {'requires': [{'or': [r1, r2]}]}

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

        requires = {'requires': [{'and': [r1, r2]}]}

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

        requires = {'requires': [{'and': [r1, r2],
                                  'or': [r1, r2]}]}

        mock_plugin.return_value.r1 = True
        mock_plugin.return_value.r2 = False
        group = YDefsSection('test', requires)
        self.assertFalse(group.leaf_sections[0].requires.passes)

        mock_plugin.return_value.r1 = True
        mock_plugin.return_value.r2 = True
        group = YDefsSection('test', requires)
        self.assertTrue(group.leaf_sections[0].requires.passes)

        requires = {'requires': [{'and': [r1, r2],
                                  'or': [r1, r2]}]}

        mock_plugin.return_value.r1 = True
        mock_plugin.return_value.r2 = False
        group = YDefsSection('test', requires)
        self.assertFalse(group.leaf_sections[0].requires.passes)

        requires = {'requires': [r1, {'and': [r3],
                                      'or': [r1, r2]}]}

        mock_plugin.return_value.r1 = True
        mock_plugin.return_value.r2 = False
        mock_plugin.return_value.r3 = True
        group = YDefsSection('test', requires)
        self.assertTrue(group.leaf_sections[0].requires.passes)

        requires = {'requires': [{'and': [r3],
                                  'or': [r1, r2]}]}

        mock_plugin.return_value.r1 = True
        mock_plugin.return_value.r2 = False
        mock_plugin.return_value.r3 = True
        group = YDefsSection('test', requires)
        self.assertTrue(group.leaf_sections[0].requires.passes)

        # same as prev test but with dict instead list
        requires = {'requires': {'and': [r3],
                                 'or': [r1, r2]}}

        mock_plugin.return_value.r1 = True
        mock_plugin.return_value.r2 = False
        mock_plugin.return_value.r3 = True
        group = YDefsSection('test', requires)
        self.assertTrue(group.leaf_sections[0].requires.passes)

    @mock.patch('hotsos.core.ycheck.APTPackageChecksBase')
    def test_yaml_def_requires_apt(self, mock_apt):
        tested = 0
        expected = {'2.0': False,
                    '3.0': True,
                    '3.1': True,
                    '4.0': True,
                    '5.0': True,
                    '5.2': True,
                    '5.3': False,
                    '6.0': False}
        mock_apt.return_value = mock.MagicMock()
        mock_apt.return_value.is_installed.return_value = True
        for ver, result in expected.items():
            mock_apt.return_value.get_version.return_value = ver
            mydef = YDefsSection('mydef',
                                 yaml.safe_load(YAML_DEF_REQUIRES_APT))
            for entry in mydef.leaf_sections:
                tested += 1
                self.assertEqual(entry.requires.passes, result)

        self.assertEqual(tested, len(expected))
