import os
import tempfile
from unittest import mock

from propertree.propertree2 import OverrideRegistry
from hotsos.core.config import HotSOSConfig
from hotsos.core.exceptions import NotYetInitializedError
from hotsos.core.host_helpers.config import IniConfigBase
from hotsos.core.issues import IssuesManager
from hotsos.core.issues.utils import IssuesStore
from hotsos.core.search import ExtraSearchConstraints, FileSearcher, SearchDef
from hotsos.core.ycheck import scenarios
from hotsos.core.ycheck.engine.properties.checks import (
    YPropertyChecks,
)
from hotsos.core.ycheck.engine.properties.conclusions import (
    YPropertyConclusion,
)

from .. import utils
from . import test_scenarios_data as test_data

# pylint: disable=duplicate-code


class TestProperty():
    """ Test Property """
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


class TestConfig(IniConfigBase):
    """ Test config """


class TestYamlScenariosPreLoad(utils.BaseTestCase):
    """
    Tests scenarios search pre-load functionality.
    """
    @utils.init_test_scenario(test_data.SCENARIO_W_EXPR_LIST.
                              format(path='data.txt'))
    @utils.global_search_context
    def test_scenario_search_preload(self, global_searcher):
        spl = scenarios.ScenariosSearchPreloader(global_searcher)
        self.assertEqual(len(list(spl.scenarios)), 1)
        self.assertEqual([s.name for s in spl.scenarios], ['test'])
        checks = list(spl.scenarios)[0].checks
        # raises error because not yet initialised
        self.assertRaises(NotYetInitializedError, lambda: list(checks))
        spl.run()
        # is now initialised so no more error
        self.assertEqual(len(list(checks)), 3)
        for scenario in spl.scenarios:
            self.assertTrue(isinstance(scenario.checks, YPropertyChecks))
            check_names = [c.name for c in scenario.checks]
            self.assertListEqual(check_names, ['listsearch1', 'listsearch2',
                                               'listsearch3'])


class TestYamlScenarios(utils.BaseTestCase):  # noqa, pylint: disable=too-many-public-methods
    """
    Tests scenarios functionality.
    """
    @utils.init_test_scenario(test_data.SCENARIO_W_EXPR_LIST.
                              format(path=os.path.basename('data.txt')))
    @utils.create_data_root({'data.txt': 'hello x\n'})
    @utils.global_search_context
    def test_yaml_def_expr_list(self, global_searcher):
        scenarios.YScenarioChecker(global_searcher).run()
        issues = list(IssuesStore().load().values())
        self.assertEqual(len(issues[0]), 3)
        i_types = [i['type'] for i in issues[0]]
        self.assertEqual(sorted(i_types),
                         sorted(['SystemWarning', 'SystemWarning',
                                 'SystemWarning']))
        for issue in issues[0]:
            msg = "yay list search"
            self.assertEqual(issue['message'], msg)

    @utils.init_test_scenario(test_data.SCENARIO_W_SEQ_SEARCH.
                              format(path=os.path.basename('data.txt')))
    @utils.create_data_root({'data.txt': ("blah blah\nit's the start\nblah "
                                          "blah\nit's the end")})
    @utils.global_search_context
    def test_yaml_def_seq_search(self, global_searcher):
        scenarios.YScenarioChecker(global_searcher).run()
        issues = list(IssuesStore().load().values())
        self.assertEqual(len(issues[0]), 1)
        i_types = [i['type'] for i in issues[0]]
        self.assertEqual(i_types, ['SystemWarning',])
        for issue in issues[0]:
            msg = "yay seq searches worked!"
            self.assertEqual(issue['message'], msg)

    @utils.init_test_scenario(test_data.SCENARIO_CHECKS)
    @utils.create_data_root({'foo.log': '2021-04-01 00:31:00.000 an event\n',
                             'uptime': (' 16:19:19 up 17:41,  2 users, '
                                        ' load average: 3.58, 3.27, 2.58'),
                             'sos_commands/date/date':
                                 'Thu Feb 10 16:19:17 UTC 2022'})
    @utils.global_search_context
    def test_yaml_def_scenario_checks_false(self, global_searcher):
        checker = scenarios.YScenarioChecker(global_searcher)
        checker.load()
        self.assertEqual(len(checker.scenarios), 1)
        for scenario in checker.scenarios:
            for check in scenario.checks.values():
                self.assertFalse(check.result)

        # now run the scenarios
        checker.run(load=False)

        self.assertEqual(IssuesManager().load_issues(), {})

    @utils.init_test_scenario(test_data.SCENARIO_CHECKS)
    @utils.global_search_context
    def test_yaml_def_scenario_checks_requires(self, global_searcher):
        checker = scenarios.YScenarioChecker(global_searcher)
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
        checker.run(load=False)

        self.assertEqual(IssuesManager().load_issues(), {})

    @utils.init_test_scenario(test_data.SCENARIO_CHECKS)
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
    @utils.global_search_context
    def test_yaml_def_scenario_checks_expr(self, global_searcher):
        checker = scenarios.YScenarioChecker(global_searcher)
        checker.load()
        self.assertEqual(len(checker.scenarios), 1)
        for scenario in checker.scenarios:
            for check in scenario.checks.values():
                if check.name == 'logmatch':
                    self.assertTrue(check.result)

        # now run the scenarios
        checker.run(load=False)

        msg = ("log matched 4 times (00:00:00.000, 00:32:00.000, "
               "00:33:00.000, 00:36:00.000)")
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual([issue['message'] for issue in issues], [msg])

    @staticmethod
    def _create_search_results(path, contents=None):
        if contents:
            with open(path, 'w', encoding='utf-8') as fd:
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
            result = ExtraSearchConstraints.filter_by_period(results, 24)
            self.assertEqual(len(result), 1)

            contents = ['2021-04-01 00:01:00.000 an event\n',
                        '2021-04-01 00:02:00.000 an event\n',
                        '2021-04-03 00:01:00.000 an event\n',
                        ]
            results = self._create_search_results(logfile, contents)
            result = ExtraSearchConstraints.filter_by_period(results, 24)
            self.assertEqual(len(result), 1)

            contents = ['2021-04-01 00:00:00.000 an event\n',
                        '2021-04-01 00:01:00.000 an event\n',
                        '2021-04-01 00:02:00.000 an event\n',
                        '2021-04-02 00:00:00.000 an event\n',
                        '2021-04-02 00:01:00.000 an event\n',
                        ]
            results = self._create_search_results(logfile, contents)
            result = ExtraSearchConstraints.filter_by_period(results, 24)
            self.assertEqual(len(result), 4)

            contents = ['2021-04-01 00:00:00.000 an event\n',
                        '2021-04-01 00:01:00.000 an event\n',
                        '2021-04-02 00:01:00.000 an event\n',
                        '2021-04-02 00:02:00.000 an event\n',
                        ]
            results = self._create_search_results(logfile, contents)
            result = ExtraSearchConstraints.filter_by_period(results, 24)
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
            result = ExtraSearchConstraints.filter_by_period(results, 24)
            self.assertEqual(len(result), 2)

    @utils.init_test_scenario(test_data.YDEF_NESTED_LOGIC)
    @utils.global_search_context
    def test_yaml_def_nested_logic(self, global_searcher):
        scenarios.YScenarioChecker(global_searcher).run()
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual(sorted([issue['message'] for issue in issues]),
                         sorted(['conc1', 'conc3']))

    @utils.init_test_scenario(test_data.YAML_DEF_REQUIRES_MAPPED)
    @utils.global_search_context
    def test_yaml_def_mapped_overrides(self, global_searcher):
        checker = scenarios.YScenarioChecker(global_searcher)
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
    @utils.init_test_scenario(test_data.SCENARIO_W_ERROR)
    @utils.global_search_context
    # pylint: disable-next=too-many-arguments
    def test_failed_scenario_caught(self, global_searcher, mock_log1,
                                    mock_log2, _mock_log3,
                                    mock_log4, mock_log5, mock_log6):
        scenarios.YScenarioChecker(global_searcher).run()

        # Check caught exception logs
        args = ('failed to import and call property %s',
                'tests.unit.ycheck.test_scenarios.TestProperty.i_dont_exist')
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

    @utils.init_test_scenario(test_data.CONFIG_SCENARIO)
    @utils.create_data_root({'test.conf': '[DEFAULT]\nkey1 = 101\n'})
    @utils.global_search_context
    def test_config_scenario_fail(self, global_searcher):
        scenarios.YScenarioChecker(global_searcher).run()
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual([issue['message'] for issue in issues],
                         ['cfg is bad', 'cfg is bad2'])

    @utils.init_test_scenario(test_data.CONFIG_SCENARIO)
    @utils.create_data_root({'test.conf': '[DEFAULT]\nkey1 = 102\n'})
    @utils.global_search_context
    def test_config_scenario_pass(self, global_searcher):
        scenarios.YScenarioChecker(global_searcher).run()
        issues = list(IssuesStore().load().values())
        self.assertEqual(len(issues), 0)

    @mock.patch('hotsos.core.ycheck.engine.properties.conclusions.log')
    @mock.patch('hotsos.core.ycheck.scenarios.log')
    @mock.patch('hotsos.core.ycheck.engine.properties.conclusions.'
                'ScenarioException')
    @utils.init_test_scenario(test_data.CONCLUSION_W_INVALID_BUG_RAISES)
    @utils.global_search_context
    def test_raises_w_invalid_types(self, global_searcher, mock_exc, mock_log,
                                    mock_log2):
        mock_exc.side_effect = Exception
        scenarios.YScenarioChecker(global_searcher).run()

        # Check caught exception logs
        args = ('caught exception when running scenario %s:', 'scenarioD')
        mock_log.exception.assert_called_with(*args)

        args = ('something went wrong when executing decision',)
        mock_log2.exception.assert_called_with(*args)

        mock_exc.assert_called_with("both cve-id/bug-id (current=1234) and "
                                    "bug type (current=issue) required in "
                                    "order to raise a bug")
        issues = list(IssuesStore().load().values())
        self.assertEqual(len(issues[0]), 1)
        i_types = [i['type'] for i in issues[0]]
        self.assertEqual(sorted(i_types),
                         sorted(['HotSOSScenariosWarning']))
        for issue in issues[0]:
            if issue['type'] == 'HotSOSScenariosWarning':
                msg = ("One or more scenarios failed to run (scenarioA, "
                       "scenarioB, scenarioC, scenarioD) - run hotsos in "
                       "debug mode (--debug) to get more detail")
                self.assertEqual(issue['message'], msg)

    @utils.init_test_scenario(test_data.VARS)
    @utils.global_search_context
    def test_vars(self, global_searcher):
        scenarios.YScenarioChecker(global_searcher).run()
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
    @utils.init_test_scenario(test_data.LOGIC_TEST)
    @utils.global_search_context
    # pylint: disable-next=too-many-arguments
    def test_logical_collection_and_with_fail(self, global_searcher, mock_log1,
                                              mock_log2, _mock_log3, mock_log4,
                                              mock_log5, mock_log6,
                                              _mock_log7):
        scenarios.YScenarioChecker(global_searcher).run()
        expected = [
            (mock_log1,
             ('failed to import and call property %s',
              'tests.unit.ycheck.test_scenarios.TestProperty.doesntexist'),
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

    @utils.init_test_scenario(test_data.NESTED_LOGIC_TEST_NO_ISSUE)
    @utils.global_search_context
    def test_logical_collection_nested_no_issue(self, global_searcher):
        scenarios.YScenarioChecker(global_searcher).run()
        issues = list(IssuesStore().load().values())
        self.assertEqual(len(issues), 0)

    @utils.init_test_scenario(test_data.NESTED_LOGIC_TEST_W_ISSUE)
    @utils.global_search_context
    def test_logical_collection_nested_w_issue(self, global_searcher):
        scenarios.YScenarioChecker(global_searcher).run()
        issues = list(IssuesStore().load().values())
        self.assertEqual(len(issues), 1)

    @utils.init_test_scenario(test_data.NESTED_LOGIC_TEST_W_ISSUE,
                              'myscenario')
    @utils.global_search_context
    def test_scenarios_filter_none(self, global_searcher):
        sc = scenarios.YScenarioChecker(global_searcher)
        sc.load()
        self.assertEqual([s.name for s in sc.scenarios], ['myscenario'])

    @utils.init_test_scenario(test_data.NESTED_LOGIC_TEST_W_ISSUE,
                              'myscenario')
    @utils.global_search_context
    def test_scenarios_filter_myscenario(self, global_searcher):
        HotSOSConfig.scenario_filter = ('myplugin.scenariogroup.subgroup.'
                                        'myscenario')
        sc = scenarios.YScenarioChecker(global_searcher)
        sc.load()
        self.assertEqual([s.name for s in sc.scenarios], ['myscenario'])

    @utils.init_test_scenario(test_data.NESTED_LOGIC_TEST_W_ISSUE,
                              'myscenario')
    @utils.global_search_context
    def test_scenarios_filter_myscenario_regex(self, global_searcher):
        HotSOSConfig.scenario_filter = 'myplugin.scenariogroup.subgroup.*'
        sc = scenarios.YScenarioChecker(global_searcher)
        sc.load()
        self.assertEqual([s.name for s in sc.scenarios], ['myscenario'])

    @utils.init_test_scenario(test_data.NESTED_LOGIC_TEST_W_ISSUE,
                              'myscenario')
    @utils.global_search_context
    def test_scenarios_filter_nonexistent(self, global_searcher):
        HotSOSConfig.scenario_filter = 'blahblah'
        sc = scenarios.YScenarioChecker(global_searcher)
        sc.load()
        self.assertEqual([s.name for s in sc.scenarios], [])

    @utils.init_test_scenario(test_data.CONCLUSION_PRIORITY_1, 'myscenario')
    @utils.global_search_context
    def test_conclusion_priority_exec_highest(self, global_searcher):
        called = []

        class YPropertyConclusionTest(YPropertyConclusion):
            """ Test YProperty """
            override_autoregister = False

            def reached(self, *args, **kwargs):
                called.append(self.name)
                return super().reached(*args, **kwargs)

        OverrideRegistry.unregister([YPropertyConclusion])
        try:
            OverrideRegistry.register([YPropertyConclusionTest])
            scenarios.YScenarioChecker(global_searcher).run()
        finally:
            OverrideRegistry.unregister([YPropertyConclusionTest])
            OverrideRegistry.register([YPropertyConclusion])

        self.assertEqual(called, ['conc3'])

    @utils.init_test_scenario(test_data.CONCLUSION_PRIORITY_2, 'myscenario')
    @utils.global_search_context
    def test_conclusion_priority_exec_all_same(self, global_searcher):
        called = []

        class YPropertyConclusionTest(YPropertyConclusion):
            """ Test YProperty """
            override_autoregister = False

            def reached(self, *args, **kwargs):
                called.append(self.name)
                return super().reached(*args, **kwargs)

        OverrideRegistry.unregister([YPropertyConclusion])
        try:
            OverrideRegistry.register([YPropertyConclusionTest])
            scenarios.YScenarioChecker(global_searcher).run()
        finally:
            OverrideRegistry.unregister([YPropertyConclusionTest])
            OverrideRegistry.register([YPropertyConclusion])

        self.assertEqual(called, ['conc1', 'conc2', 'conc3'])
