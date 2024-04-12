import os
import tempfile
from unittest import mock

from propertree.propertree2 import OverrideRegistry
from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers.config import SectionalConfigBase
from hotsos.core.issues import IssuesManager
from hotsos.core.issues.utils import IssuesStore
from hotsos.core.search import FileSearcher, SearchDef
from hotsos.core.ycheck import scenarios
from hotsos.core.ycheck.engine.properties.search import YPropertySearch
from hotsos.core.ycheck.engine.properties.conclusions import (
    YPropertyConclusion,
)

from . import utils


class TestProperty(object):

    @property
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

    def __call__(self, name, state, has_instances):
        return FakeServiceObject(name, state, has_instances,
                                 start_time=self._start_times[name])


class FakeServiceObject(object):

    def __init__(self, name, state, has_instances, start_time):
        self.name = name
        self.state = state
        self.start_time = start_time
        self.has_instances = has_instances


def init_test_scenario(yaml_contents, scenario_name=None):
    """
    Create a temporary defs path with a scenario yaml under it.

    @param param yaml_contents: yaml contents of scenario def.
    """
    def init_test_scenario_inner1(f):
        def init_test_scenario_inner2(*args, **kwargs):
            with tempfile.TemporaryDirectory() as dtmp:
                HotSOSConfig.plugin_yaml_defs = dtmp
                HotSOSConfig.plugin_name = 'myplugin'
                yroot = os.path.join(dtmp, 'scenarios', 'myplugin',
                                     'scenariogroup')
                sname = scenario_name or 'test'
                yfile = os.path.join(yroot, '{}.yaml'.format(sname))
                os.makedirs(os.path.dirname(yfile))
                with open(yfile, 'w') as fd:
                    fd.write(yaml_contents)
                return f(*args, **kwargs)

        return init_test_scenario_inner2
    return init_test_scenario_inner1


YDEF_NESTED_LOGIC = """
checks:
  isTrue:
    requires:
      and:
        - property: tests.unit.test_ycheck_scenarios.TestProperty.always_true
        - property:
            path: tests.unit.test_ycheck_scenarios.TestProperty.always_false
            ops: [[not_]]
  isalsoTrue:
    requires:
      or:
        - property: tests.unit.test_ycheck_scenarios.TestProperty.always_true
        - property: tests.unit.test_ycheck_scenarios.TestProperty.always_false
  isstillTrue:
    requires:
      and:
        - property: tests.unit.test_ycheck_scenarios.TestProperty.always_true
      or:
        - property: tests.unit.test_ycheck_scenarios.TestProperty.always_true
        - property: tests.unit.test_ycheck_scenarios.TestProperty.always_false
  isnotTrue:
    requires:
      and:
        - property: tests.unit.test_ycheck_scenarios.TestProperty.always_true
      or:
        - property: tests.unit.test_ycheck_scenarios.TestProperty.always_false
        - property: tests.unit.test_ycheck_scenarios.TestProperty.always_false
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


CONCLUSION_PRIORITY_1 = """
checks:
  testcheck:
    property: tests.unit.test_ycheck_scenarios.TestProperty.always_true
conclusions:
  conc1:
    priority: 1
    decision:
      - testcheck
    raises:
      type: IssueTypeBase
      message: conc1
  conc2:
    priority: 2
    decision:
      - testcheck
    raises:
      type: IssueTypeBase
      message: conc2
  conc3:
    priority: 3
    decision:
      - testcheck
    raises:
      type: IssueTypeBase
      message: conc3
"""

CONCLUSION_PRIORITY_2 = """
checks:
  testcheck:
    property: tests.unit.test_ycheck_scenarios.TestProperty.always_true
conclusions:
  conc1:
    priority: 1
    decision:
      - testcheck
    raises:
      type: IssueTypeBase
      message: conc1
  conc2:
    decision:
      - testcheck
    raises:
      type: IssueTypeBase
      message: conc2
  conc3:
    decision:
      - testcheck
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

YAML_DEF_REQUIRES_PEBBLE_FAIL = """
pluginX:
  groupA:
    requires:
      pebble:
        foo:
          state: active
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


SCENARIO_W_SEQ_SEARCH = r"""
input:
  path: {path}
checks:
  seqsearch1:
    start: "it's the start"
    body: ".+"
    end: "it's the end"
  seqsearch2:
    start: "it's the start"
    end: "it's the end"
conclusions:
  seqsearchworked:
    decision:
      - seqsearch1
      - seqsearch2
    raises:
      type: SystemWarning
      message: yay seq searches worked!
"""  # noqa


SCENARIO_W_ERROR = r"""
scenarioA:
  checks:
    property_no_error:
      property: tests.unit.test_ycheck_scenarios.TestProperty.always_true
  conclusions:
    c1:
      decision: property_no_error
      raises:
        type: SystemWarning
        message: foo
scenarioB:
  checks:
    property_w_error:
      property: tests.unit.test_ycheck_scenarios.TestProperty.i_dont_exist
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
      property: tests.unit.test_ycheck_scenarios.TestProperty.always_true
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
      property: tests.unit.test_ycheck_scenarios.TestProperty.always_true
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
    expr: '(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}\.\d{3}) (\S+) \S+'
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
      message: log matched {num} times ({group})
      format-dict:
        num: '@checks.logmatch.search.num_results'
        group: '@checks.logmatch.search.results_group_2:comma_join'
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
      handler: tests.unit.test_ycheck_scenarios.TestConfig
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
      handler: tests.unit.test_ycheck_scenarios.TestConfig
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
  fromprop: '@tests.unit.test_ycheck_scenarios.TestProperty.myattr'
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
        varname: '@checks.is_foo_gt.requires.input_ref'
        varval: '@checks.is_foo_gt.requires.input_value'
  is_foo_lt:
    decision: is_foo_lt
    raises:
      type: SystemWarning
      message: it's foo lt! ({varname}={varval})
      format-dict:
        varname: '@checks.is_foo_lt.requires.input_ref'
        varval: '@checks.is_foo_lt.requires.input_value'
  isbar:
    decision: isbar
    raises:
      type: SystemWarning
      message: it's bar! ({varname}={varval})
      format-dict:
        varname: '@checks.isbar.requires.input_ref'
        varval: '@checks.isbar.requires.input_value'
  fromprop:
    decision:
      and: [fromprop, boolvar, fromfact, fromfact2, fromsysctl]
    raises:
      type: SystemWarning
      message: fromprop! ({varname}={varval})
      format-dict:
        varname: '@checks.fromprop.requires.input_ref'
        varval: '@checks.fromprop.requires.input_value'
"""  # noqa


# this set of checks should cover the variations of logical op groupings that
# will not process items beyond the first that returns False which is the
# default for any AND operation since a single False makes the group result the
# same.
LOGIC_TEST = """
vars:
  # this one will resolve as False
  v1: '@tests.unit.test_ycheck_scenarios.TestProperty.always_false'
  # this one will raise an ImportError
  v2: '@tests.unit.test_ycheck_scenarios.TestProperty.doesntexist'
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
    - varops: [[$v2], [not_]]
    - varops: [[$v1], [truth]]
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

DPKG_L = """
ii  openssh-server                       1:8.2p1-4ubuntu0.4                                   amd64        secure shell (SSH) server, for secure access from remote machines
"""  # noqa


class TestYamlScenarios(utils.BaseTestCase):

    @init_test_scenario(SCENARIO_W_EXPR_LIST.
                        format(path=os.path.basename('data.txt')))
    @utils.create_data_root({'data.txt': 'hello x\n'})
    def test_yaml_def_expr_list(self):
        scenarios.YScenarioChecker().load_and_run()
        issues = list(IssuesStore().load().values())
        self.assertEqual(len(issues[0]), 3)
        i_types = [i['type'] for i in issues[0]]
        self.assertEqual(sorted(i_types),
                         sorted(['SystemWarning', 'SystemWarning',
                                 'SystemWarning']))
        for issue in issues[0]:
            msg = "yay list search"
            self.assertEqual(issue['message'], msg)

    @init_test_scenario(SCENARIO_W_SEQ_SEARCH.
                        format(path=os.path.basename('data.txt')))
    @utils.create_data_root({'data.txt': ("blah blah\nit's the start\nblah "
                                          "blah\nit's the end")})
    def test_yaml_def_seq_search(self):
        scenarios.YScenarioChecker().load_and_run()
        issues = list(IssuesStore().load().values())
        self.assertEqual(len(issues[0]), 1)
        i_types = [i['type'] for i in issues[0]]
        self.assertEqual(i_types, ['SystemWarning',])
        for issue in issues[0]:
            msg = "yay seq searches worked!"
            self.assertEqual(issue['message'], msg)

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
        checker.load_and_run()

        self.assertEqual(IssuesManager().load_issues(), {})

    @init_test_scenario(SCENARIO_CHECKS)
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
        checker.load_and_run()

        self.assertEqual(IssuesManager().load_issues(), {})

    @init_test_scenario(SCENARIO_CHECKS)
    @utils.create_data_root({'foo.log':
                             ('2021-03-29 00:31:00.000 an event\n'
                              '2021-03-30 00:32:00.000 an event\n'
                              '2021-03-30 00:33:00.000 an event\n'
                              '2021-03-30 00:00:00.000 an event\n'
                              '2021-03-30 00:36:00.000 an event\n'),
                             'uptime': (' 16:19:19 up 17:41,  2 users, '
                                        ' load average: 3.58, 3.27, 2.58'),
                             'sos_commands/date/date':
                                 'Thu Mar 31 16:19:17 UTC 2021'})
    def test_yaml_def_scenario_checks_expr(self):
        checker = scenarios.YScenarioChecker()
        checker.load()
        self.assertEqual(len(checker.scenarios), 1)
        for scenario in checker.scenarios:
            for check in scenario.checks.values():
                if check.name == 'logmatch':
                    self.assertTrue(check.result)

        # now run the scenarios
        checker.run()

        msg = ("log matched 4 times (00:00:00.000, 00:32:00.000, "
               "00:33:00.000, 00:36:00.000)")
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual([issue['message'] for issue in issues], [msg])

    def _create_search_results(self, path, contents=None):
        if contents:
            with open(path, 'w') as fd:
                for line in contents:
                    fd.write(line)

        s = FileSearcher()
        s.add(SearchDef(r'^(\S+) (\S+) .+', tag='all'), path)
        return s.run().find_by_tag('all')

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
            self.assertEqual(len(result), 1)

            contents = ['2021-04-01 00:00:00.000 an event\n',
                        '2021-04-01 00:01:00.000 an event\n',
                        '2021-04-01 00:02:00.000 an event\n',
                        '2021-04-02 00:00:00.000 an event\n',
                        '2021-04-02 00:01:00.000 an event\n',
                        ]
            results = self._create_search_results(logfile, contents)
            result = YPropertySearch.filter_by_period(results, 24)
            self.assertEqual(len(result), 4)

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
            self.assertEqual(len(result), 2)

    @init_test_scenario(YDEF_NESTED_LOGIC)
    def test_yaml_def_nested_logic(self):
        scenarios.YScenarioChecker().load_and_run()
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual(sorted([issue['message'] for issue in issues]),
                         sorted(['conc1', 'conc3']))

    @init_test_scenario(YAML_DEF_REQUIRES_MAPPED)
    def test_yaml_def_mapped_overrides(self):
        checker = scenarios.YScenarioChecker()
        checker.load()
        self.assertEqual(len(checker.scenarios), 1)
        for scenario in checker.scenarios:
            self.assertEqual(len(scenario.checks), 2)
            for check in scenario.checks.values():
                self.assertTrue(check.result)

    @mock.patch('hotsos.core.ycheck.scenarios.log')
    @mock.patch('hotsos.core.ycheck.engine.properties.checks.log')
    @mock.patch('hotsos.core.ycheck.engine.properties.conclusions.log')
    @mock.patch('hotsos.core.ycheck.engine.properties.requires.requires.log')
    @mock.patch('hotsos.core.ycheck.engine.properties.requires.common.log')
    @mock.patch('hotsos.core.ycheck.engine.properties.common.log')
    @init_test_scenario(SCENARIO_W_ERROR)
    def test_failed_scenario_caught(self, mock_log1, mock_log2, _mock_log3,
                                    mock_log4, mock_log5, mock_log6):
        scenarios.YScenarioChecker().load_and_run()

        # Check caught exception logs
        args = ('failed to import and call property %s',
                'tests.unit.test_ycheck_scenarios.TestProperty.i_dont_exist')
        mock_log1.exception.assert_called_with(*args)

        args = ('requires.%s.result raised the following',
                'YRequirementTypeProperty')
        mock_log2.error.assert_called_with(*args)

        # mock_log3 gets an AttributeError as arg so dont test.

        args = ('something went wrong when executing decision',)
        mock_log4.exception.assert_called_with(*args)
        args = ('something went wrong while executing check %s',
                'property_w_error')
        mock_log5.exception.assert_called_with(*args)
        args = ('caught exception when running scenario %s:', 'scenarioB')
        mock_log6.exception.assert_called_with(*args)

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
                self.assertEqual(issue['message'], msg)

    @init_test_scenario(CONFIG_SCENARIO)
    @utils.create_data_root({'test.conf': '[DEFAULT]\nkey1 = 101\n'})
    def test_config_scenario_fail(self):
        scenarios.YScenarioChecker().load_and_run()
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual([issue['message'] for issue in issues],
                         ['cfg is bad', 'cfg is bad2'])

    @init_test_scenario(CONFIG_SCENARIO)
    @utils.create_data_root({'test.conf': '[DEFAULT]\nkey1 = 102\n'})
    def test_config_scenario_pass(self):
        scenarios.YScenarioChecker().load_and_run()
        issues = list(IssuesStore().load().values())
        self.assertEqual(len(issues), 0)

    @mock.patch('hotsos.core.ycheck.engine.properties.conclusions.log')
    @mock.patch('hotsos.core.ycheck.scenarios.log')
    @mock.patch('hotsos.core.ycheck.engine.properties.conclusions.'
                'ScenarioException')
    @init_test_scenario(CONCLUSION_W_INVALID_BUG_RAISES)
    def test_raises_w_invalid_types(self, mock_exc, mock_log, mock_log2):
        mock_exc.side_effect = Exception
        scenarios.YScenarioChecker().load_and_run()

        # Check caught exception logs
        args = ('caught exception when running scenario %s:', 'scenarioB')
        mock_log.exception.assert_called_with(*args)

        args = ('something went wrong when executing decision',)
        mock_log2.exception.assert_called_with(*args)

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
                self.assertEqual(issue['message'], msg)

    @init_test_scenario(VARS)
    def test_vars(self):
        scenarios.YScenarioChecker().load_and_run()
        issues = list(IssuesStore().load().values())
        self.assertEqual(len(issues[0]), 4)
        msgs = []
        for issue in issues[0]:
            msgs.append(issue['message'])

        self.assertEqual(sorted(msgs),
                         sorted(["nova-compute=2:21.2.3-0ubuntu1",
                                 "it's foo gt! ($foo=1000)",
                                 "it's bar! ($bar=two)",
                                 "fromprop! ($fromprop=123)"]))

    @mock.patch('propertree.propertree2.log')
    @mock.patch('hotsos.core.ycheck.scenarios.log')
    @mock.patch('hotsos.core.ycheck.engine.properties.conclusions.log')
    @mock.patch('hotsos.core.ycheck.engine.properties.checks.log')
    @mock.patch('hotsos.core.ycheck.engine.properties.requires.requires.log')
    @mock.patch('hotsos.core.ycheck.engine.properties.requires.common.log')
    @mock.patch('hotsos.core.ycheck.engine.properties.common.log')
    @init_test_scenario(LOGIC_TEST)
    def test_logical_collection_and_with_fail(self, mock_log1, mock_log2,
                                              _mock_log3, mock_log4,
                                              mock_log5, mock_log6,
                                              _mock_log7):
        scenarios.YScenarioChecker().load_and_run()
        expected = [
            (mock_log1,
             ('failed to import and call property %s',
              'tests.unit.test_ycheck_scenarios.TestProperty.doesntexist'),
            'exception'),
            (mock_log2,
             ('requires.%s.result raised the following', 'YPropertyVarOps'),
            'error'),
            # we can't test mock_log3 because it passes in an AttributeError
            (mock_log4, ('something went wrong while executing check %s',
                         'chk_nand'),
            'exception'),
            (mock_log5, ('something went wrong when executing decision',),
            'exception'),
            (mock_log6,
             ('caught exception when running scenario %s:', 'test'),
            'exception')]

        for logger, args, level in expected:
            getattr(logger, level).assert_called_with(*args)

        issues = list(IssuesStore().load().values())
        self.assertEqual(len(issues), 1)
        i_types = [i['type'] for i in issues[0]]
        self.assertEqual(sorted(i_types),
                         sorted(['HotSOSScenariosWarning']))
        for issue in issues[0]:
            if issue['type'] == 'HotSOSScenariosWarning':
                msg = ("One or more scenarios failed to run (test) - "
                       "run hotsos in debug mode (--debug) to get more "
                       "detail")
                self.assertEqual(issue['message'], msg)

    @init_test_scenario(NESTED_LOGIC_TEST_NO_ISSUE)
    def test_logical_collection_nested_no_issue(self):
        scenarios.YScenarioChecker().load_and_run()
        issues = list(IssuesStore().load().values())
        self.assertEqual(len(issues), 0)

    @init_test_scenario(NESTED_LOGIC_TEST_W_ISSUE)
    def test_logical_collection_nested_w_issue(self):
        scenarios.YScenarioChecker().load_and_run()
        issues = list(IssuesStore().load().values())
        self.assertEqual(len(issues), 1)

    @init_test_scenario(NESTED_LOGIC_TEST_W_ISSUE, 'myscenario')
    def test_scenarios_filter_none(self):
        sc = scenarios.YScenarioChecker()
        sc.load()
        self.assertEqual([s.name for s in sc.scenarios], ['myscenario'])

    @init_test_scenario(NESTED_LOGIC_TEST_W_ISSUE, 'myscenario')
    def test_scenarios_filter_myscenario(self):
        HotSOSConfig.scenario_filter = 'myplugin.scenariogroup.myscenario'
        sc = scenarios.YScenarioChecker()
        sc.load()
        self.assertEqual([s.name for s in sc.scenarios], ['myscenario'])

    @init_test_scenario(NESTED_LOGIC_TEST_W_ISSUE, 'myscenario')
    def test_scenarios_filter_nonexistent(self):
        HotSOSConfig.scenario_filter = 'blahblah'
        sc = scenarios.YScenarioChecker()
        sc.load()
        self.assertEqual([s.name for s in sc.scenarios], [])

    @init_test_scenario(CONCLUSION_PRIORITY_1, 'myscenario')
    def test_conclusion_priority_exec_highest(self):
        called = []

        class YPropertyConclusionTest(YPropertyConclusion):
            _override_autoregister = False

            def reached(self, *args, **kwargs):
                called.append(self.name)
                return super().reached(*args, **kwargs)

        OverrideRegistry.unregister([YPropertyConclusion])
        try:
            OverrideRegistry.register([YPropertyConclusionTest])
            scenarios.YScenarioChecker().load_and_run()
        finally:
            OverrideRegistry.unregister([YPropertyConclusionTest])
            OverrideRegistry.register([YPropertyConclusion])

        self.assertEqual(called, ['conc3'])

    @init_test_scenario(CONCLUSION_PRIORITY_2, 'myscenario')
    def test_conclusion_priority_exec_all_same(self):
        called = []

        class YPropertyConclusionTest(YPropertyConclusion):
            _override_autoregister = False

            def reached(self, *args, **kwargs):
                called.append(self.name)
                return super().reached(*args, **kwargs)

        OverrideRegistry.unregister([YPropertyConclusion])
        try:
            OverrideRegistry.register([YPropertyConclusionTest])
            scenarios.YScenarioChecker().load_and_run()
        finally:
            OverrideRegistry.unregister([YPropertyConclusionTest])
            OverrideRegistry.register([YPropertyConclusion])

        self.assertEqual(called, ['conc1', 'conc2', 'conc3'])
