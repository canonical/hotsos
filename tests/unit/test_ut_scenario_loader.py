import os
import tempfile
import uuid
from unittest import mock

from hotsos.core.config import HotSOSConfig

from . import utils


class ScenarioTestsBase(utils.BaseTestCase):
    pass


class FakeTemplatedTestGenerator():

    @property
    def test_method_name(self):
        return str(uuid.uuid4())

    @property
    def test_method(self):
        return 'can be anything'


FAKE_SCENARIO = """
vars:
  v1: 1000
checks:
  gt1k:
    varops: [[$v1], [gt, 1000]]
  lt1k:
    varops: [[$v1], [lt, 1000]]
conclusions:
  iseq1k:
    decision:
      not:
        - gt1k
        - lt1k
    raises:
      type: SystemWarning
      message: it's equal!
"""

FAKE_TEST_W_TARGET = """
target-name: {}
raised-bugs:
raised-issues:
  SystemWarning: it's equal!
"""

FAKE_TEST = """
raised-bugs:
raised-issues:
  SystemWarning: it's equal!
"""


class TestScenarioTestLoader(ScenarioTestsBase):

    @staticmethod
    def create_scenarios(path, levels=1):
        _path = os.path.join(path, 'scenarios', HotSOSConfig.plugin_name)
        for lvl in range(1, levels + 1):
            _path = os.path.join(_path, str(lvl))
            os.makedirs(_path)

            scenario_name_templates = [
                'myscenario{}.yaml',
                'myscenario.with.many.dots.{}.yaml',
                'myscenario_noextension{}',
                'myscenario{}alt.yaml'
            ]

            for scenario_name_template in scenario_name_templates:
                scenario_name = scenario_name_template.format(lvl)
                with open(os.path.join(_path, scenario_name), 'w') as fd:
                    fd.write(FAKE_SCENARIO)

    @staticmethod
    def create_tests(path, levels=1):
        _path = os.path.join(path, 'tests/scenarios', HotSOSConfig.plugin_name)
        for lvl in range(1, levels + 1):
            _path = os.path.join(_path, str(lvl))
            os.makedirs(_path)

            test_files_without_target = [
                'myscenario{}.yaml',
                'myscenario.with.many.dots.{}.yaml',
                'myscenario_noextension{}'
            ]

            test_files_with_target = [
                'myscenario{}alt.yaml'
            ]

            for name_template in test_files_without_target:
                file_name = name_template.format(lvl)
                with open(os.path.join(_path, file_name), 'w') as fd:
                    fd.write(FAKE_TEST)

            for name_template in test_files_with_target:
                file_name = name_template.format(lvl)
                with open(os.path.join(_path, file_name), 'w') as fd:
                    fd.write(FAKE_TEST_W_TARGET)

    def test_check_test_names(self):
        with tempfile.TemporaryDirectory() as dtmp:
            self.create_tests(dtmp, levels=1)
            self.create_scenarios(dtmp, levels=1)
            with mock.patch.object(utils, 'DEFS_DIR', dtmp),\
                 mock.patch.object(utils, 'DEFS_TESTS_DIR', dtmp + '/tests'):

                @utils.load_templated_tests('scenarios/testplugin')
                class MyTests(ScenarioTestsBase):
                    pass

                a = MyTests()
                tests = [x for x in dir(a) if x.startswith("test_")]
                self.assertEqual(len(tests), 4)

                self.assertTrue("test_yscenario_1_myscenario_with_many_dots_1"
                                in tests)
                self.assertTrue("test_yscenario_1_myscenario1" in tests)
                self.assertTrue("test_yscenario_1_myscenario1alt" in tests)
                self.assertTrue("test_yscenario_1_myscenario_noextension1"
                                in tests)

    def test_find_all_templated_tests(self):
        with tempfile.TemporaryDirectory() as dtmp:
            paths = []
            self.create_tests(dtmp, levels=3)
            for path in utils.find_all_templated_tests(dtmp):
                paths.append(path)

            plugin_path = 'tests/scenarios/testplugin'

            expected = [
                '1/myscenario1.yaml',
                '1/myscenario1alt.yaml',
                '1/myscenario.with.many.dots.1.yaml',
                '1/myscenario_noextension1',
                '1/2/myscenario2.yaml',
                '1/2/myscenario2alt.yaml',
                '1/2/myscenario.with.many.dots.2.yaml',
                '1/2/myscenario_noextension2',
                '1/2/3/myscenario3.yaml',
                '1/2/3/myscenario3alt.yaml',
                '1/2/3/myscenario.with.many.dots.3.yaml',
                '1/2/3/myscenario_noextension3'
            ]

            expected = [os.path.join(dtmp, plugin_path, x) for x in expected]

            self.assertEqual(sorted(paths), sorted(expected))

    @mock.patch.object(utils, 'TemplatedTestGenerator')
    def test_load_templated_tests_single(self, mock_test_gen):
        mock_test_gen.return_value = FakeTemplatedTestGenerator()
        with tempfile.TemporaryDirectory() as dtmp:
            self.create_tests(dtmp)
            with mock.patch.object(utils, 'DEFS_TESTS_DIR',
                                   os.path.join(dtmp, 'tests')):
                class FakeTests():

                    @utils.load_templated_tests('scenarios/testplugin/1')
                    @staticmethod
                    def faketest():
                        pass

                FakeTests().faketest()
                plugin_path = 'tests/scenarios/testplugin'
                s1 = os.path.join(dtmp, plugin_path, '1/myscenario1.yaml')
                calls = [mock.call('scenarios/testplugin/1', s1)]
                mock_test_gen.assert_has_calls(calls)

    @mock.patch.object(utils, 'TemplatedTestGenerator')
    def test_load_templated_tests_multi(self, mock_test_gen):
        mock_test_gen.return_value = FakeTemplatedTestGenerator()
        with tempfile.TemporaryDirectory() as dtmp:
            self.create_tests(dtmp, levels=3)
            with mock.patch.object(utils, 'DEFS_TESTS_DIR', dtmp + '/tests'):
                @utils.load_templated_tests('scenarios/testplugin/1')
                class FakeTests():  # pylint: disable=W0612
                    pass

                plugin_path = 'tests/scenarios/testplugin'
                s1 = os.path.join(dtmp, plugin_path,
                                  '1/myscenario1.yaml')
                s1alt = os.path.join(dtmp, plugin_path,
                                     '1/myscenario1alt.yaml')
                s2 = os.path.join(dtmp, plugin_path,
                                  '1/2/myscenario2.yaml')
                s2alt = os.path.join(dtmp, plugin_path,
                                     '1/2/myscenario2alt.yaml')
                s3 = os.path.join(dtmp, plugin_path,
                                  '1/2/3/myscenario3.yaml')
                s3alt = os.path.join(dtmp, plugin_path,
                                     '1/2/3/myscenario3alt.yaml')
                calls = [mock.call('scenarios/testplugin/1',
                                   os.path.join(dtmp, s1)),
                         mock.call('scenarios/testplugin/1',
                                   os.path.join(dtmp, s1alt)),
                         mock.call('scenarios/testplugin/1',
                                   os.path.join(dtmp, s2)),
                         mock.call('scenarios/testplugin/1',
                                   os.path.join(dtmp, s2alt)),
                         mock.call('scenarios/testplugin/1',
                                   os.path.join(dtmp, s3)),
                         mock.call('scenarios/testplugin/1',
                                   os.path.join(dtmp, s3alt))]
                mock_test_gen.assert_has_calls(calls, any_order=True)

    def test_is_def_filter(self):
        with tempfile.TemporaryDirectory() as dtmp:
            self.create_scenarios(dtmp, levels=3)
            self.create_tests(dtmp, levels=3)

            with open(os.path.join(dtmp, 'test1.yaml'),
                      'w') as fd:
                fd.write(FAKE_SCENARIO)
            with mock.patch.object(utils, 'DEFS_TESTS_DIR', dtmp):
                utils.TemplatedTest(
                    os.path.join(dtmp, 'test1.yaml'),
                    {}, [], [], [], '/')()(self)

    def test_scenarios(self):
        with tempfile.TemporaryDirectory() as dtmp,\
             mock.patch.object(utils, 'DEFS_DIR', dtmp),\
             mock.patch.object(utils, 'DEFS_TESTS_DIR', dtmp + '/tests'):
            self.create_scenarios(dtmp, levels=5)
            self.create_tests(dtmp, levels=5)
            orig_config = HotSOSConfig.CONFIG
            try:
                HotSOSConfig.plugin_yaml_defs = dtmp
                HotSOSConfig.global_tmp_dir = dtmp
                HotSOSConfig.plugin_tmp_dir = dtmp

                @utils.load_templated_tests('scenarios/testplugin')
                class MyTests(ScenarioTestsBase):
                    pass

                MyTests().test_yscenario_1_myscenario1()  # noqa, pylint: disable=E1101
                MyTests().test_yscenario_1_myscenario1alt() # noqa, # pylint: disable=E1101
                MyTests().test_yscenario_1_2_myscenario2()  # noqa, pylint: disable=E1101
                MyTests().test_yscenario_1_2_myscenario2alt()  # noqa, pylint: disable=E1101
                MyTests().test_yscenario_1_2_3_myscenario3()  # noqa, pylint: disable=E1101
                MyTests().test_yscenario_1_2_3_myscenario3alt()  # noqa, pylint: disable=E1101
                MyTests().test_yscenario_1_2_3_4_myscenario4()  # noqa, pylint: disable=E1101
                MyTests().test_yscenario_1_2_3_4_myscenario4alt()  # noqa, pylint: disable=E1101
                MyTests().test_yscenario_1_2_3_4_5_myscenario5()  # noqa, pylint: disable=E1101
                MyTests().test_yscenario_1_2_3_4_5_myscenario5alt()  # noqa, pylint: disable=E1101

                raised = False
                try:
                    MyTests().test_1_2_3_4_5_myscenario100()
                except AttributeError:
                    raised = True

                self.assertTrue(raised)
            finally:
                HotSOSConfig.set(**orig_config)

    def test_scenarios_deep(self):
        with tempfile.TemporaryDirectory() as dtmp,\
             mock.patch.object(utils, 'DEFS_DIR', dtmp),\
             mock.patch.object(utils, 'DEFS_TESTS_DIR', dtmp + '/tests'):
            self.create_scenarios(dtmp, levels=5)
            self.create_tests(dtmp, levels=5)
            orig_config = HotSOSConfig.CONFIG
            try:
                HotSOSConfig.plugin_yaml_defs = dtmp
                HotSOSConfig.global_tmp_dir = dtmp
                HotSOSConfig.plugin_tmp_dir = dtmp

                @utils.load_templated_tests('scenarios/testplugin/'
                                            '1/2/3/4/5')
                class MyTests(ScenarioTestsBase):
                    pass

                MyTests().test_yscenario_myscenario5()  # pylint: disable=E1101
                MyTests().test_yscenario_myscenario5alt()  # noqa, pylint: disable=E1101

                raised = False
                try:
                    MyTests().test_1_myscenario1()
                except AttributeError:
                    raised = True

                self.assertTrue(raised)
            finally:
                HotSOSConfig.set(**orig_config)

    def test_scenarios_no_such_target(self):
        with tempfile.TemporaryDirectory() as dtmp,\
             mock.patch.object(utils, 'DEFS_DIR', dtmp),\
             mock.patch.object(utils, 'DEFS_TESTS_DIR', dtmp + '/tests'):
            self.create_tests(dtmp, levels=5)
            # Do not create scenarios intentionally
            with self.assertRaises(FileNotFoundError):
                @utils.load_templated_tests('scenarios/testplugin/'
                                            '1/2/3/4/5')
                class MyTests(ScenarioTestsBase):
                    pass
                MyTests()
