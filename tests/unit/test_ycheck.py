import datetime
import os
import tempfile

from unittest import mock
import yaml

from . import utils

from hotsos.core.issues import IssuesManager
from hotsos.core.issues.utils import IssuesStore
from hotsos.core.config import HotSOSConfig
from hotsos.core.search import FileSearcher, SearchDef
from hotsos.core.host_helpers.config import SectionalConfigBase
from hotsos.core.ycheck import (
    events,
    scenarios,
)
from hotsos.core.ycheck.engine import (
    YDefsSection,
    YDefsLoader,
)
from hotsos.core.ycheck.events import CallbackHelper
from hotsos.core.ycheck.engine.properties.common import (
    YPropertyBase,
    cached_yproperty_attr,
)
from hotsos.core.ycheck.engine.properties.search import YPropertySearch


class TestProperty(YPropertyBase):

    @cached_yproperty_attr
    def myattr(self):
        return '123'

    @property
    def myotherattr(self):
        return '456'

    @property
    def always_true(self):
        return True

    @property
    def always_false(self):
        return False


class TestConfig(SectionalConfigBase):
    pass


class FakeServiceObjectManager(object):

    def __init__(self, start_times):
        self._start_times = start_times

    def __call__(self, name, state):
        return FakeServiceObject(name, state,
                                 start_time=self._start_times[name])


class FakeServiceObject(object):

    def __init__(self, name, state, start_time):
        self.name = name
        self.state = state
        self.start_time = start_time


def init_test_scenario(yaml_contents, set_data_root=True):
    """
    Create a temporary defs path with a scenario yaml under it.

    @param param yaml_contents: yaml contents of scenario def.
    @param param set_data_root: by default the data_root will point to a
                                temporary dir. Some tests may want to keep
                                the original one and can do that by setting
                                this to False.
    """
    def init_test_scenario_inner1(f):
        def init_test_scenario_inner2(*args, **kwargs):
            with tempfile.TemporaryDirectory() as dtmp:
                HotSOSConfig.plugin_yaml_defs = dtmp
                HotSOSConfig.plugin_name = 'myplugin'
                if set_data_root:
                    HotSOSConfig.data_root = dtmp
                yroot = os.path.join(dtmp, 'scenarios', 'myplugin')
                yfile = os.path.join(yroot, 'test.yaml')
                os.makedirs(os.path.dirname(yfile))
                open(yfile, 'w').write(yaml_contents)
                return f(*args, **kwargs)

        return init_test_scenario_inner2
    return init_test_scenario_inner1


YDEF_NESTED_LOGIC = """
checks:
  isTrue:
    requires:
      and:
        - property: tests.unit.test_ycheck.TestProperty.always_true
        - property:
            path: tests.unit.test_ycheck.TestProperty.always_false
            ops: [[not_]]
  isalsoTrue:
    requires:
      or:
        - property: tests.unit.test_ycheck.TestProperty.always_true
        - property: tests.unit.test_ycheck.TestProperty.always_false
  isstillTrue:
    requires:
      and:
        - property: tests.unit.test_ycheck.TestProperty.always_true
      or:
        - property: tests.unit.test_ycheck.TestProperty.always_true
        - property: tests.unit.test_ycheck.TestProperty.always_false
  isnotTrue:
    requires:
      and:
        - property: tests.unit.test_ycheck.TestProperty.always_true
      or:
        - property: tests.unit.test_ycheck.TestProperty.always_false
        - property: tests.unit.test_ycheck.TestProperty.always_false
conclusions:
  conc1:
    decision:
      and:
        - isTrue
        - isalsoTrue
      or:
        - isstillTrue
    raises:
      type: IssueTypeBase
      message: conc1
  conc2:
    decision:
      and:
        - isTrue
        - isnotTrue
      or:
        - isalsoTrue
    raises:
      type: IssueTypeBase
      message: conc2
  conc3:
    decision:
      not:
        - isnotTrue
      or:
        - isalsoTrue
    raises:
      type: IssueTypeBase
      message: conc3
"""


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
        altpackage:
          - min: '3.0'
            max: '3.2'
          - min: '4.0'
            max: '4.2'
          - min: '5.0'
            max: '5.2'
"""


YAML_DEF_REQUIRES_SYSTEMD_PASS_1 = """
pluginX:
  groupA:
    requires:
      systemd:
        ondemand: enabled
        nova-compute: enabled
"""


YAML_DEF_REQUIRES_SYSTEMD_STARTED_AFTER = """
pluginX:
  groupA:
    requires:
      systemd:
        openvswitch-switch:
          state: enabled
          started-after: neutron-openvswitch-agent
"""


YAML_DEF_REQUIRES_SYSTEMD_FAIL_1 = """
pluginX:
  groupA:
    requires:
      systemd:
        ondemand: enabled
        nova-compute: disabled
"""

YAML_DEF_REQUIRES_MAPPED = """
checks:
  is_exists_mapped:
    systemd: nova-compute
  is_exists_unmapped:
    requires:
      systemd: nova-compute
conclusions:
"""

YAML_DEF_REQUIRES_SYSTEMD_FAIL_2 = """
pluginX:
  groupA:
    requires:
      systemd:
        ondemand:
          state: enabled
        nova-compute:
          state: disabled
          op: eq
"""


YAML_DEF_REQUIRES_GROUPED = """
passdef1:
  requires:
    - path: sos_commands/networking
    - not:
        path: sos_commands/networking_foo
    - apt: python3.8
    - and:
        - apt:
            systemd:
              - min: '245.4-4ubuntu3.14'
                max: '245.4-4ubuntu3.15'
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
    - path: sos_commands/networking_foo
    - and:
        - apt: doo
        - apt: daa
      or:
        - apt: nova-compute
      not:
        - and:
            - apt: 'blah'
        - and:
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


SCENARIO_W_EXPR_LIST = r"""
input:
  path: {path}
checks:
  listsearch1:
    expr: ['hello y', 'hello x']
  listsearch2:
    search: ['hello y', 'hello x']
  listsearch3:
    search:
       expr: ['hello y', 'hello x']
conclusions:
  listsearch1worked:
    decision: listsearch1
    raises:
      type: SystemWarning
      message: yay list search
  listsearch2worked:
    decision: listsearch2
    raises:
      type: SystemWarning
      message: yay list search
  listsearch3worked:
    decision: listsearch3
    raises:
      type: SystemWarning
      message: yay list search
"""  # noqa


SCENARIO_W_ERROR = r"""
scenarioA:
  checks:
    property_no_error:
      property: tests.unit.test_ycheck.TestProperty.always_true
  conclusions:
    c1:
      decision: property_no_error
      raises:
        type: SystemWarning
        message: foo
scenarioB:
  checks:
    property_w_error:
      property: tests.unit.test_ycheck.TestProperty.i_dont_exist
  conclusions:
    c1:
      decision: property_w_error
      raises:
        type: SystemWarning
        message: foo
"""  # noqa


CONCLUSION_W_INVALID_BUG_RAISES = r"""
scenarioA:
  checks:
    property_no_error:
      property: tests.unit.test_ycheck.TestProperty.always_true
  conclusions:
    c1:
      decision: property_no_error
      raises:
        type: SystemWarning
        bug-id: 1234
        message: foo
scenarioB:
  checks:
    property_w_error:
      property: tests.unit.test_ycheck.TestProperty.always_true
  conclusions:
    c1:
      decision: property_no_error
      raises:
        type: LaunchpadBug
        message: foo
"""  # noqa


SCENARIO_CHECKS = r"""
checks:
  logmatch:
    input:
      path: foo.log
    expr: '^([0-9-]+)\S* (\S+) .+'
    constraints:
      min-results: 3
      search-period-hours: 24
      search-result-age-hours: 48
  property_true_shortform:
    requires:
      property:
        path: hotsos.core.plugins.system.system.SystemBase.virtualisation_type
  property_has_value_longform:
    requires:
      property:
        path: hotsos.core.plugins.system.system.SystemBase.virtualisation_type
        ops: [[eq, kvm], [truth], [not_], [not_]]
  apt_pkg_exists:
    requires:
      apt: nova-compute
  snap_pkg_exists:
    requires:
      snap: core20
  service_exists_short:
    requires:
      systemd: nova-compute
  service_exists_and_enabled:
    requires:
      systemd:
        nova-compute: enabled
  service_exists_not_enabled:
    requires:
      systemd:
        nova-compute:
          state: enabled
          op: ne
conclusions:
  justlog:
    priority: 1
    decision: logmatch
    raises:
      type: SystemWarning
      message: log matched {num} times
      format-dict:
        num: '@checks.logmatch.search.num_results'
  logandsnap:
    priority: 2
    decision:
      and:
        - logmatch
        - snap_pkg_exists
    raises:
      type: SystemWarning
      message: log matched {num} times and snap exists
      format-dict:
        num: '@checks.logmatch.search.num_results'
  logandsnapandservice:
    priority: 3
    decision:
      and:
        - logmatch
        - snap_pkg_exists
        - service_exists_short
        - service_exists_and_enabled
        - property_true_shortform
        - property_has_value_longform
    raises:
      type: SystemWarning
      message: log matched {num} times, snap and service exists
      format-dict:
        num: '@checks.logmatch.search.num_results'
"""  # noqa


CONFIG_SCENARIO = """
checks:
  cfg_is_bad:
    config:
      handler: tests.unit.test_ycheck.TestConfig
      path: test.conf
      assertions:
        - key: key1
          section: DEFAULT
          ops: [[lt, 102]]
        - key: key1
          section: DEFAULT
          ops: [[gt, 100]]
  cfg_is_bad2:
    config:
      handler: tests.unit.test_ycheck.TestConfig
      path: test.conf
      assertions:
        not:
          - key: key1
            section: DEFAULT
            ops: [[lt, 103]]
          - key: key1
            section: DEFAULT
            ops: [[gt, 101]]
conclusions:
  cfg_is_bad:
    decision: cfg_is_bad
    raises:
      type: SystemWarning
      message: cfg is bad
  cfg_is_bad2:
    decision: cfg_is_bad2
    raises:
      type: SystemWarning
      message: cfg is bad2
"""


VARS = """
vars:
  foo: 1000
  limit: 10
  bar: "two"
  frombadprop: '@tests.unit.idontexist'  # add to ensure lazy-loaded
  fromprop: '@tests.unit.test_ycheck.TestProperty.myattr'
  fromfact: '@hotsos.core.host_helpers.systemd.ServiceFactory.start_time_secs:snapd'
  fromfact2: '@hotsos.core.host_helpers.filestat.FileFactory.mtime:myfile.txt'
  fromsysctl: '@hotsos.core.host_helpers.sysctl.SYSCtlFactory:net.core.somaxconn'
  boolvar: false
checks:
  aptcheck:
    apt: nova-compute
  is_foo_lt:
    varops: [[$foo], [lt, $limit]]
  is_foo_gt:
    varops: [[$foo], [gt, $limit]]
  isbar:
    varops: [[$bar], [ne, ""]]
  fromprop:
    varops: [[$fromprop], [eq, "123"]]
  fromfact:
    varops: [[$fromfact], [gt, 1644446300]]
  fromfact2:
    varops: [[$fromfact2], [eq, 0]]
  fromsysctl:
    varops: [[$fromsysctl], [eq, '4096']]
  boolvar:
    varops: [[$boolvar], [truth], [not_]]
conclusions:
  aptcheck:
    decision: aptcheck
    raises:
      type: SystemWarning
      message: "{name}={version}"
      format-dict:
        name: '@checks.aptcheck.requires.package'
        version: '@checks.aptcheck.requires.version'
  is_foo_gt:
    decision: is_foo_gt
    raises:
      type: SystemWarning
      message: it's foo gt! ({varname}={varval})
      format-dict:
        varname: '@checks.is_foo_gt.requires.name'
        varval: '@checks.is_foo_gt.requires.value'
  is_foo_lt:
    decision: is_foo_lt
    raises:
      type: SystemWarning
      message: it's foo lt! ({varname}={varval})
      format-dict:
        varname: '@checks.is_foo_lt.requires.name'
        varval: '@checks.is_foo_lt.requires.value'
  isbar:
    decision: isbar
    raises:
      type: SystemWarning
      message: it's bar! ({varname}={varval})
      format-dict:
        varname: '@checks.isbar.requires.name'
        varval: '@checks.isbar.requires.value'
  fromprop:
    decision:
      and: [fromprop, boolvar, fromfact, fromfact2, fromsysctl]
    raises:
      type: SystemWarning
      message: fromprop! ({varname}={varval})
      format-dict:
        varname: '@checks.fromprop.requires.name'
        varval: '@checks.fromprop.requires.value'
"""  # noqa


# this set of checks should cover the variations of logical op groupings that
# will not process items beyond the first that returns False which is the
# default for any AND operation since a single False makes the group result the
# same.
LOGIC_TEST = """
vars:
  # this one will resolve as False
  v1: '@tests.unit.test_ycheck.TestProperty.always_false'
  # this one will raise an ImportError
  v2: '@tests.unit.test_ycheck.TestProperty.doesntexist'
checks:
  # the second item in each group must be one that if evaluated will raise an
  # error.
  chk_and:
    and:
      - varops: [[$v1], [truth]]
      - varops: [[$v2], [not_]]
  chk_nand:
    nand:
      - varops: [[$v1], [not_]]
      - varops: [[$v2], [not_]]
  chk_not:
    not:
      - varops: [[$v1], [not_]]
      - varops: [[$v2], [not_]]
  chk_default_and:
    - varops: [[$v1], [truth]]
    - varops: [[$v2], [not_]]
conclusions:
  conc1:
    decision:
       or:
         - chk_and
         - chk_nand
         - chk_not
         - chk_default_and
    raises:
      type: SystemWarning
      message: >-
        This should never get raised since all checks should be
        returning False and the first false result in each check's logical
        group should result in further items not being executed.
"""

NESTED_LOGIC_TEST_W_ISSUE = """
vars:
  bool_true: true
checks:
  chk_pass1:
    and:
      - varops: [[$bool_true], [truth]]
      - not:
          varops: [[$bool_true], [not_]]
  chk_pass2:
    or:
      - and:
          - varops: [[$bool_true], [truth]]
          - varops: [[$bool_true], [not_]]
      - and:
          - varops: [[$bool_true], [truth]]
          - varops: [[$bool_true], [truth]]
      - varops: [[$bool_true], [truth]]
  chk_pass3:
    or:
      - varops: [[$bool_true], [truth]]
      - varops: [[$bool_true], [truth]]
conclusions:
  conc1:
    decision: [chk_pass1, chk_pass2, chk_pass3]
    raises:
      type: SystemWarning
      message:
"""


NESTED_LOGIC_TEST_NO_ISSUE = """
vars:
  bool_true: true
checks:
  chk_fail1:
    and:
      - varops: [[$bool_true], [truth]]
      - not:
          varops: [[$bool_true], [truth]]
  chk_fail2:
    or:
      - and:
          - varops: [[$bool_true], [not_]]
          - varops: [[$bool_true], [not_]]
      - and:
          - varops: [[$bool_true], [not_]]
          - varops: [[$bool_true], [not_]]
      - varops: [[$bool_true], [not_]]
conclusions:
  conc1:
    decision:
      or: [chk_fail1, chk_fail2]
    raises:
      type: SystemWarning
      message:
"""


class TestYamlChecks(utils.BaseTestCase):

    def test_yproperty_attr_cache(self):
        p = TestProperty()
        self.assertEqual(getattr(p.cache, '__yproperty_attr__myattr'), None)
        self.assertEqual(p.myattr, '123')
        self.assertEqual(getattr(p.cache, '__yproperty_attr__myattr'), '123')
        self.assertEqual(p.myattr, '123')
        self.assertEqual(p.myotherattr, '456')

    def test_yaml_def_group_input(self):
        plugin_checks = yaml.safe_load(YAML_DEF_W_INPUT).get('pluginX')
        for name, group in plugin_checks.items():
            group = YDefsSection(name, group)
            for entry in group.leaf_sections:
                self.assertEqual(entry.input.paths,
                                 [os.path.join(HotSOSConfig.data_root,
                                               'foo/bar1*')])

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
                self.assertEqual(entry.input.paths,
                                 [os.path.join(HotSOSConfig.data_root,
                                               'foo/bar2*')])

    def test_yaml_def_entry_input_override(self):
        plugin_checks = yaml.safe_load(YAML_DEF_W_INPUT_SUPERSEDED2)
        for name, group in plugin_checks.get('pluginX').items():
            group = YDefsSection(name, group)
            for entry in group.leaf_sections:
                self.assertEqual(entry.input.paths,
                                 [os.path.join(HotSOSConfig.data_root,
                                               'foo/bar3*')])

    @utils.create_data_root({'data.txt': 'hello\nbrave\nworld\n',
                             'events/myplugin/mygroup.yaml':
                             YAML_DEF_EXPR_TYPES.format(path='data.txt')})
    def test_yaml_def_entry_seq(self):
        _yaml = YAML_DEF_EXPR_TYPES.format(path=os.path.basename('data.txt'))
        plugin_checks = yaml.safe_load(_yaml).get('myplugin')
        for name, group in plugin_checks.items():
            group = YDefsSection(name, group)
            data_file = os.path.join(HotSOSConfig.data_root, 'data.txt')
            for entry in group.leaf_sections:
                self.assertEqual(entry.input.paths,
                                 ['{}*'.format(data_file)])

        test_self = self
        match_count = {'count': 0}
        callbacks_called = {}
        HotSOSConfig.plugin_yaml_defs = HotSOSConfig.data_root
        HotSOSConfig.plugin_name = 'myplugin'
        EVENTCALLBACKS = CallbackHelper()

        class MyEventHandler(events.YEventCheckerBase):
            def __init__(self):
                super().__init__(EVENTCALLBACKS,
                                 yaml_defs_group='mygroup',
                                 searchobj=FileSearcher())

            @EVENTCALLBACKS.callback(event_group='mygroup')
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

            @EVENTCALLBACKS.callback(event_group='mygroup')
            def my_passthrough_search(self, event):
                # expected to be passthough results (i.e. raw)
                callbacks_called[event.name] = True
                tag = '{}-start'.format(event.search_tag)
                start_results = event.results.find_by_tag(tag)
                test_self.assertEqual(start_results[0].get(0), 'hello')

            @EVENTCALLBACKS.callback(event_group='mygroup',
                                     event_names=['my-pass-search',
                                                  'my-fail-search1',
                                                  'my-fail-search2'])
            def my_standard_search_common(self, event):
                callbacks_called[event.name] = True
                test_self.assertEqual(event.results[0].get(0), 'hello')

            def __call__(self):
                self.run_checks()

        MyEventHandler()()
        self.assertEqual(match_count['count'], 3)
        self.assertEqual(list(callbacks_called.keys()),
                         ['my-sequence-search',
                          'my-passthrough-search',
                          'my-pass-search'])

    @init_test_scenario(SCENARIO_W_EXPR_LIST.
                        format(path=os.path.basename('data.txt')))
    @utils.create_data_root({'data.txt': 'hello x\n'})
    def test_yaml_def_expr_list(self):
        scenarios.YScenarioChecker()()
        issues = list(IssuesStore().load().values())
        self.assertEqual(len(issues[0]), 3)
        i_types = [i['type'] for i in issues[0]]
        self.assertEqual(sorted(i_types),
                         sorted(['SystemWarning', 'SystemWarning',
                                 'SystemWarning']))
        for issue in issues[0]:
            msg = ("yay list search")
            self.assertEqual(issue['desc'], msg)

    @mock.patch('hotsos.core.ycheck.engine.properties.requires.types.apt.'
                'APTPackageHelper')
    def test_yaml_def_scenarios_no_issue(self, apt_check):
        apt_check.is_installed.return_value = True
        HotSOSConfig.plugin_name = 'juju'
        scenarios.YScenarioChecker()()
        self.assertEqual(IssuesManager().load_issues(), {})

    @init_test_scenario(SCENARIO_CHECKS)
    @utils.create_data_root({'foo.log': '2021-04-01 00:31:00.000 an event\n',
                             'uptime': (' 16:19:19 up 17:41,  2 users, '
                                        ' load average: 3.58, 3.27, 2.58'),
                             'sos_commands/date/date':
                                 'Thu Feb 10 16:19:17 UTC 2022'})
    def test_yaml_def_scenario_checks_false(self):
        checker = scenarios.YScenarioChecker()
        checker.load()
        self.assertEqual(len(checker.scenarios), 1)
        for scenario in checker.scenarios:
            for check in scenario.checks.values():
                self.assertFalse(check.result)

        # now run the scenarios
        checker()

        self.assertEqual(IssuesManager().load_issues(), {})

    @init_test_scenario(SCENARIO_CHECKS, set_data_root=False)
    def test_yaml_def_scenario_checks_requires(self):
        checker = scenarios.YScenarioChecker()
        checker.load()
        self.assertEqual(len(checker.scenarios), 1)
        checked = 0
        for scenario in checker.scenarios:
            for check in scenario.checks.values():
                if check.name == 'apt_pkg_exists':
                    checked += 1
                    self.assertTrue(check.result)
                elif check.name == 'snap_pkg_exists':
                    checked += 1
                    self.assertTrue(check.result)
                elif check.name == 'service_exists_and_enabled':
                    checked += 1
                    self.assertTrue(check.result)
                elif check.name == 'service_exists_not_enabled':
                    checked += 1
                    self.assertFalse(check.result)

        self.assertEqual(checked, 4)

        # now run the scenarios
        checker()

        self.assertEqual(IssuesManager().load_issues(), {})

    @mock.patch('hotsos.core.ycheck.engine.properties.search.CLIHelper')
    @init_test_scenario(SCENARIO_CHECKS)
    @utils.create_data_root({'foo.log':
                             ('2021-04-01 00:31:00.000 an event\n'
                              '2021-04-01 00:32:00.000 an event\n'
                              '2021-04-01 00:33:00.000 an event\n'
                              '2021-04-02 00:00:00.000 an event\n'
                              '2021-04-02 00:36:00.000 an event\n'),
                             'uptime': (' 16:19:19 up 17:41,  2 users, '
                                        ' load average: 3.58, 3.27, 2.58'),
                             'sos_commands/date/date':
                                 'Thu Mar 31 16:19:17 UTC 2021'})
    def test_yaml_def_scenario_checks_expr(self, mock_cli):
        mock_cli.return_value = mock.MagicMock()
        mock_cli.return_value.date.return_value = "2021-04-03 00:00:00"
        checker = scenarios.YScenarioChecker()
        checker.load()
        self.assertEqual(len(checker.scenarios), 1)
        for scenario in checker.scenarios:
            for check in scenario.checks.values():
                if check.name == 'logmatch':
                    self.assertTrue(check.result)

        # now run the scenarios
        checker.run()

        msg = ("log matched 4 times")
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual([issue['desc'] for issue in issues], [msg])

    def _create_search_results(self, path, contents=None):
        if contents:
            with open(path, 'w') as fd:
                for line in contents:
                    fd.write(line)

        s = FileSearcher()
        s.add_search_term(SearchDef(r'^(\S+) (\S+) .+', tag='all'), path)
        return s.search().find_by_tag('all')

    def test_get_datetime_from_result(self):
        result = mock.MagicMock()
        result.get.side_effect = lambda idx: _result.get(idx)

        _result = {1: '2022-01-06', 2: '12:34:56.123'}
        ts = YPropertySearch.get_datetime_from_result(result)
        self.assertEqual(ts, datetime.datetime(2022, 1, 6, 12, 34, 56, 123000))

        _result = {1: '2022-01-06', 2: '12:34:56'}
        ts = YPropertySearch.get_datetime_from_result(result)
        self.assertEqual(ts, datetime.datetime(2022, 1, 6, 12, 34, 56))

        _result = {1: '2022-01-06'}
        ts = YPropertySearch.get_datetime_from_result(result)
        self.assertEqual(ts, datetime.datetime(2022, 1, 6, 0, 0))

        _result = {1: '2022-01-06 12:34:56.123'}
        ts = YPropertySearch.get_datetime_from_result(result)
        self.assertEqual(ts, datetime.datetime(2022, 1, 6, 12, 34, 56, 123000))

        _result = {1: '2022-01-06 12:34:56'}
        ts = YPropertySearch.get_datetime_from_result(result)
        self.assertEqual(ts, datetime.datetime(2022, 1, 6, 12, 34, 56))

        _result = {1: '2022-01-06'}
        ts = YPropertySearch.get_datetime_from_result(result)
        self.assertEqual(ts, datetime.datetime(2022, 1, 6, 0, 0))

        _result = {1: '2022-01-06', 2: 'foo'}
        ts = YPropertySearch.get_datetime_from_result(result)
        self.assertEqual(ts, datetime.datetime(2022, 1, 6, 0, 0))

        _result = {1: 'foo'}
        ts = YPropertySearch.get_datetime_from_result(result)
        self.assertEqual(ts, None)

    @mock.patch('hotsos.core.ycheck.engine.properties.search.CLIHelper')
    @utils.create_data_root({'foo.log': '2022-01-06 00:00:00.000 an event\n'})
    def test_yaml_def_scenario_result_filters_by_age(self, mock_cli):
        mock_cli.return_value = mock.MagicMock()
        mock_cli.return_value.date.return_value = "2022-01-07 00:00:00"
        HotSOSConfig.plugin_yaml_defs = HotSOSConfig.data_root
        HotSOSConfig.plugin_name = 'myplugin'

        s = FileSearcher()
        path = os.path.join(HotSOSConfig.data_root, 'foo.log')
        s.add_search_term(SearchDef(r'^(\S+) (\S+) .+', tag='all'), path)
        results = s.search().find_by_tag('all')

        result = YPropertySearch.filter_by_age(results, 48)
        self.assertEqual(len(result), 1)

        result = YPropertySearch.filter_by_age(results, 24)
        self.assertEqual(len(result), 1)

        result = YPropertySearch.filter_by_age(results, 23)
        self.assertEqual(len(result), 0)

    def test_yaml_def_scenario_result_filters_by_period(self):
        with tempfile.TemporaryDirectory() as dtmp:
            HotSOSConfig.set(plugin_yaml_defs=dtmp, data_root=dtmp,
                             plugin_name='myplugin')
            logfile = os.path.join(dtmp, 'foo.log')

            contents = ['2021-04-01 00:01:00.000 an event\n']
            results = self._create_search_results(logfile, contents)
            result = YPropertySearch.filter_by_period(results, 24)
            self.assertEqual(len(result), 1)

            contents = ['2021-04-01 00:01:00.000 an event\n',
                        '2021-04-01 00:02:00.000 an event\n',
                        '2021-04-03 00:01:00.000 an event\n',
                        ]
            results = self._create_search_results(logfile, contents)
            result = YPropertySearch.filter_by_period(results, 24)
            self.assertEqual(len(result), 2)

            contents = ['2021-04-01 00:00:00.000 an event\n',
                        '2021-04-01 00:01:00.000 an event\n',
                        '2021-04-01 00:02:00.000 an event\n',
                        '2021-04-02 00:00:00.000 an event\n',
                        '2021-04-02 00:01:00.000 an event\n',
                        ]
            results = self._create_search_results(logfile, contents)
            result = YPropertySearch.filter_by_period(results, 24)

            contents = ['2021-04-01 00:00:00.000 an event\n',
                        '2021-04-01 00:01:00.000 an event\n',
                        '2021-04-02 00:01:00.000 an event\n',
                        '2021-04-02 00:02:00.000 an event\n',
                        ]
            results = self._create_search_results(logfile, contents)
            result = YPropertySearch.filter_by_period(results, 24)
            self.assertEqual(len(result), 2)

            contents = ['2021-04-01 00:00:00.000 an event\n',
                        '2021-04-01 00:01:00.000 an event\n',
                        '2021-04-02 02:00:00.000 an event\n',
                        '2021-04-03 01:00:00.000 an event\n',
                        '2021-04-04 02:00:00.000 an event\n',
                        '2021-04-05 02:00:00.000 an event\n',
                        '2021-04-06 01:00:00.000 an event\n',
                        ]
            results = self._create_search_results(logfile, contents)
            result = YPropertySearch.filter_by_period(results, 24)
            self.assertEqual(len(result), 4)

    @utils.create_data_root({'mytype/myplugin/defs.yaml':
                             'foo: bar\n',
                             'mytype/myplugin/mytype.yaml':
                             'requires:\n  property: foo\n'})
    def test_fs_override_inheritance(self):
        """
        When a directory is used to group definitions and overrides are
        provided in a <dirname>.yaml file, we need to make sure those overrides
        do not supersceded overrides of the same type used by definitions in
        the same directory.
        """
        HotSOSConfig.set(plugin_yaml_defs=HotSOSConfig.data_root,
                         plugin_name='myplugin')
        expected = {'mytype': {
                        'requires': {
                            'property': 'foo'}},
                    'defs': {'foo': 'bar'}}
        self.assertEqual(YDefsLoader('mytype').plugin_defs,
                         expected)

    @utils.create_data_root({'mytype/myplugin/defs.yaml':
                             'requires:\n  apt: apackage\n',
                             'mytype/myplugin/mytype.yaml':
                             'requires:\n  property: foo\n'})
    def test_fs_override_inheritance2(self):
        """
        When a directory is used to group definitions and overrides are
        provided in a <dirname>.yaml file, we need to make sure those overrides
        do not supersceded overrides of the same type used by definitions in
        the same directory.
        """
        HotSOSConfig.set(plugin_yaml_defs=HotSOSConfig.data_root,
                         plugin_name='myplugin')
        expected = {'mytype': {
                        'requires': {
                            'property': 'foo'}},
                    'defs': {
                        'requires': {
                            'apt': 'apackage'}}}
        self.assertEqual(YDefsLoader('mytype').plugin_defs,
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

        results = []
        for leaf in group.leaf_sections:
            self.assertEqual(len(leaf.requires), 1)
            for _requires in leaf.requires:
                for op in _requires:
                    for item in op:
                        for rtype in item:
                            for entry in rtype:
                                results.append(entry())

            self.assertFalse(leaf.requires.passes)

        self.assertFalse(group.leaf_sections[0].requires.passes)
        self.assertEqual(len(results), 2)
        self.assertEqual(results, [False, False])

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

    @mock.patch('hotsos.core.ycheck.engine.properties.requires.types.apt.'
                'APTPackageHelper')
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

    def test_yaml_def_requires_systemd_pass(self):
        mydef = YDefsSection('mydef',
                             yaml.safe_load(YAML_DEF_REQUIRES_SYSTEMD_PASS_1))
        for entry in mydef.leaf_sections:
            self.assertTrue(entry.requires.passes)

    def test_yaml_def_requires_systemd_fail(self):
        mydef = YDefsSection('mydef',
                             yaml.safe_load(YAML_DEF_REQUIRES_SYSTEMD_FAIL_1))
        for entry in mydef.leaf_sections:
            self.assertFalse(entry.requires.passes)

        mydef = YDefsSection('mydef',
                             yaml.safe_load(YAML_DEF_REQUIRES_SYSTEMD_FAIL_2))
        for entry in mydef.leaf_sections:
            self.assertFalse(entry.requires.passes)

    def test_yaml_def_requires_systemd_started_after_pass(self):
        current = datetime.datetime.now()
        with mock.patch('hotsos.core.host_helpers.systemd.SystemdService',
                        FakeServiceObjectManager({
                            'neutron-openvswitch-agent':
                                current,
                            'openvswitch-switch':
                                current + datetime.timedelta(seconds=120)})):
            content = yaml.safe_load(YAML_DEF_REQUIRES_SYSTEMD_STARTED_AFTER)
            mydef = YDefsSection('mydef', content)
            for entry in mydef.leaf_sections:
                self.assertTrue(entry.requires.passes)

    def test_yaml_def_requires_systemd_started_after_fail(self):
        current = datetime.datetime.now()
        with mock.patch('hotsos.core.host_helpers.systemd.SystemdService',
                        FakeServiceObjectManager({'neutron-openvswitch-agent':
                                                  current,
                                                  'openvswitch-switch':
                                                  current})):
            content = yaml.safe_load(YAML_DEF_REQUIRES_SYSTEMD_STARTED_AFTER)
            mydef = YDefsSection('mydef', content)
            for entry in mydef.leaf_sections:
                self.assertFalse(entry.requires.passes)

        with mock.patch('hotsos.core.host_helpers.systemd.SystemdService',
                        FakeServiceObjectManager({
                            'neutron-openvswitch-agent': current,
                            'openvswitch-switch':
                                current + datetime.timedelta(seconds=119)})):
            content = yaml.safe_load(YAML_DEF_REQUIRES_SYSTEMD_STARTED_AFTER)
            mydef = YDefsSection('mydef', content)
            for entry in mydef.leaf_sections:
                self.assertFalse(entry.requires.passes)

    @init_test_scenario(YDEF_NESTED_LOGIC)
    def test_yaml_def_nested_logic(self):
        scenarios.YScenarioChecker()()
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual(sorted([issue['desc'] for issue in issues]),
                         sorted(['conc1', 'conc3']))

    @init_test_scenario(YAML_DEF_REQUIRES_MAPPED, set_data_root=False)
    def test_yaml_def_mapped_overrides(self):
        checker = scenarios.YScenarioChecker()
        checker.load()
        self.assertEqual(len(checker.scenarios), 1)
        for scenario in checker.scenarios:
            self.assertEqual(len(scenario.checks), 2)
            for check in scenario.checks.values():
                self.assertTrue(check.result)

    @mock.patch('hotsos.core.ycheck.scenarios.log')
    @mock.patch('hotsos.core.ycheck.engine.properties.requires.requires.log')
    @mock.patch('hotsos.core.ycheck.engine.properties.requires.common.log')
    @mock.patch('hotsos.core.ycheck.engine.properties.common.log')
    @init_test_scenario(SCENARIO_W_ERROR)
    def test_failed_scenario_caught(self, mock_log1, mock_log2, mock_log3,
                                    mock_log4):
        scenarios.YScenarioChecker()()

        # Check caught exception logs
        args = ('failed to import and call property %s',
                'tests.unit.test_ycheck.TestProperty.i_dont_exist')
        mock_log1.exception.assert_called_with(*args)
        args = ('requires.%s.result raised the following',
                'YRequirementTypeProperty')
        mock_log2.exception.assert_called_with(*args)
        args = ('exception caught during run_collection:',)
        mock_log3.exception.assert_called_with(*args)
        args = ('caught exception when running scenario %s:', 'scenarioB')
        mock_log4.exception.assert_called_with(*args)

        issues = list(IssuesStore().load().values())
        self.assertEqual(len(issues[0]), 2)
        i_types = [i['type'] for i in issues[0]]
        self.assertEqual(sorted(i_types),
                         sorted(['SystemWarning',
                                 'HotSOSScenariosWarning']))
        for issue in issues[0]:
            if issue['type'] == 'HotSOSScenariosWarning':
                msg = ("One or more scenarios failed to run (scenarioB) - "
                       "run hotsos in debug mode (--debug) to get more "
                       "detail")
                self.assertEqual(issue['desc'], msg)

    @init_test_scenario(CONFIG_SCENARIO)
    def test_config_scenario_fail(self):
        cfg = os.path.join(HotSOSConfig.data_root, 'test.conf')
        contents = ['[DEFAULT]\nkey1 = 101\n']
        with open(cfg, 'w') as fd:
            for line in contents:
                fd.write(line)

        scenarios.YScenarioChecker()()
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual([issue['desc'] for issue in issues],
                         ['cfg is bad', 'cfg is bad2'])

    @init_test_scenario(CONFIG_SCENARIO)
    def test_config_scenario_pass(self):
        cfg = os.path.join(HotSOSConfig.data_root, 'test.conf')
        contents = ['[DEFAULT]\nkey1 = 102\n']
        with open(cfg, 'w') as fd:
            for line in contents:
                fd.write(line)

        scenarios.YScenarioChecker()()
        issues = list(IssuesStore().load().values())
        self.assertEqual(len(issues), 0)

    @mock.patch('hotsos.core.ycheck.scenarios.log')
    @mock.patch('hotsos.core.ycheck.engine.properties.conclusions.'
                'ScenarioException')
    @init_test_scenario(CONCLUSION_W_INVALID_BUG_RAISES)
    def test_raises_w_invalid_types(self, mock_exc, mock_log):
        mock_exc.side_effect = Exception
        scenarios.YScenarioChecker()()

        # Check caught exception logs
        args = ('caught exception when running scenario %s:', 'scenarioB')
        mock_log.exception.assert_called_with(*args)

        mock_exc.assert_called_with("both bug-id (current=1234) and bug type "
                                    "(current=issue) required in order to "
                                    "raise a bug")
        issues = list(IssuesStore().load().values())
        self.assertEqual(len(issues[0]), 1)
        i_types = [i['type'] for i in issues[0]]
        self.assertEqual(sorted(i_types),
                         sorted(['HotSOSScenariosWarning']))
        for issue in issues[0]:
            if issue['type'] == 'HotSOSScenariosWarning':
                msg = ("One or more scenarios failed to run (scenarioA, "
                       "scenarioB) - run hotsos in debug mode (--debug) to "
                       "get more detail")
                self.assertEqual(issue['desc'], msg)

    @init_test_scenario(VARS, set_data_root=False)
    def test_vars(self):
        scenarios.YScenarioChecker()()
        issues = list(IssuesStore().load().values())
        self.assertEqual(len(issues[0]), 4)
        msgs = []
        for issue in issues[0]:
            msgs.append(issue['desc'])

        self.assertEqual(sorted(msgs),
                         sorted(["nova-compute=2:21.2.3-0ubuntu1",
                                 "it's foo gt! ($foo=1000)",
                                 "it's bar! ($bar=two)",
                                 "fromprop! ($fromprop=123)"]))

    @init_test_scenario(LOGIC_TEST)
    def test_logical_collection_and_with_fail(self):
        scenarios.YScenarioChecker()()
        issues = list(IssuesStore().load().values())
        self.assertEqual(len(issues), 0)

    @init_test_scenario(NESTED_LOGIC_TEST_NO_ISSUE)
    def test_logical_collection_nested_no_issue(self):
        scenarios.YScenarioChecker()()
        issues = list(IssuesStore().load().values())
        self.assertEqual(len(issues), 0)

    @init_test_scenario(NESTED_LOGIC_TEST_W_ISSUE)
    def test_logical_collection_nested_w_issue(self):
        scenarios.YScenarioChecker()()
        issues = list(IssuesStore().load().values())
        self.assertEqual(len(issues), 1)
