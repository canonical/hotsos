
# Definitions for ycheck_scenarios tests, put here to address the
# too-many-lines (1000 lines) per file pylint limit.

YDEF_NESTED_LOGIC = """
checks:
  isTrue:
    requires:
      and:
        - property: tests.unit.ycheck.test_scenarios.TestProperty.always_true
        - property:
            path: tests.unit.ycheck.test_scenarios.TestProperty.always_false
            ops: [[not_]]
  isalsoTrue:
    requires:
      or:
        - property: tests.unit.ycheck.test_scenarios.TestProperty.always_true
        - property: tests.unit.ycheck.test_scenarios.TestProperty.always_false
  isstillTrue:
    requires:
      and:
        - property: tests.unit.ycheck.test_scenarios.TestProperty.always_true
      or:
        - property: tests.unit.ycheck.test_scenarios.TestProperty.always_true
        - property: tests.unit.ycheck.test_scenarios.TestProperty.always_false
  isnotTrue:
    requires:
      and:
        - property: tests.unit.ycheck.test_scenarios.TestProperty.always_true
      or:
        - property: tests.unit.ycheck.test_scenarios.TestProperty.always_false
        - property: tests.unit.ycheck.test_scenarios.TestProperty.always_false
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
    property: tests.unit.ycheck.test_scenarios.TestProperty.always_true
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
    property: tests.unit.ycheck.test_scenarios.TestProperty.always_true
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


YAML_DEF_REQUIRES_MAPPED = """
checks:
  is_exists_mapped:
    systemd: nova-compute
  is_exists_unmapped:
    requires:
      systemd: nova-compute
conclusions:
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
      property: tests.unit.ycheck.test_scenarios.TestProperty.always_true
  conclusions:
    c1:
      decision: property_no_error
      raises:
        type: SystemWarning
        message: foo
scenarioB:
  checks:
    property_w_error:
      property: tests.unit.ycheck.test_scenarios.TestProperty.i_dont_exist
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
      property: tests.unit.ycheck.test_scenarios.TestProperty.always_true
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
      property: tests.unit.ycheck.test_scenarios.TestProperty.always_true
  conclusions:
    c1:
      decision: property_no_error
      raises:
        type: LaunchpadBug
        message: foo
scenarioC:
  checks:
    property_w_error:
      property: tests.unit.ycheck.test_scenarios.TestProperty.always_true
  conclusions:
    c1:
      decision: property_no_error
      raises:
        type: UbuntuCVE
        message: foo
scenarioD:
  checks:
    property_w_error:
      property: tests.unit.ycheck.test_scenarios.TestProperty.always_true
  conclusions:
    c1:
      decision: property_no_error
      raises:
        cve-id: 123
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
      handler: tests.unit.ycheck.test_scenarios.TestConfig
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
      handler: tests.unit.ycheck.test_scenarios.TestConfig
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
  fromprop: '@tests.unit.ycheck.test_scenarios.TestProperty.myattr'
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
  v1: '@tests.unit.ycheck.test_scenarios.TestProperty.always_false'
  # this one will raise an ImportError
  v2: '@tests.unit.ycheck.test_scenarios.TestProperty.doesntexist'
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
