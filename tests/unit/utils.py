import importlib
import os
import re
import shutil
import sys
import tempfile
import unittest
from unittest import mock
from dataclasses import dataclass, field

import yaml
from hotsos.core.config import HotSOSConfig
from hotsos.core.issues import IssuesManager
# disable for stestr otherwise output is much too verbose
from hotsos.core.log import log, logging, LoggingManager
from hotsos.core.ycheck.scenarios import YScenarioChecker
from hotsos.core.ycheck.common import GlobalSearcher
from hotsos.core.exceptions import (
    NameAlreadyRegisteredError,
    ExpectationNotMetError,
    InvalidFileFormatError
)

# Must be set prior to other imports
TESTS_DIR = os.environ["TESTS_DIR"]
HOTSOS_ROOT = os.environ["HOTSOS_ROOT"]
DEFS_DIR = os.path.join(HOTSOS_ROOT, 'defs')
DEFS_TESTS_DIR = os.path.join(DEFS_DIR, 'tests')
DEFAULT_FAKE_ROOT = 'fake_data_root/openstack'
HotSOSConfig.data_root = os.path.join(TESTS_DIR, DEFAULT_FAKE_ROOT)
TEST_TEMPLATE_SCHEMA = set(['target-name', 'data-root', 'mock',
                            'raised-issues', 'raised-bugs'])


def find_all_templated_tests(path):
    """
    Generator to recursively find all templates (files) under path.

    @return: path to test.
    """
    if not os.path.exists(path):
        log.info("templated tests dir not found: %s", path)
        return

    for testdef in os.listdir(path):
        if testdef.endswith(('.disabled', '.swp')):
            continue

        defpath = os.path.join(path, testdef)
        if os.path.isdir(defpath):
            yield from find_all_templated_tests(defpath)
        else:
            yield defpath


def load_templated_tests(path):
    """ Add templated tests to the runner.

    @param path: relative path to test templates we want to load under
                 defs/tests.
    """
    def _inner(cls):
        count = 0
        _path = os.path.join(DEFS_TESTS_DIR, path)
        for testdef in find_all_templated_tests(_path):
            tg = TemplatedTestGenerator(path, testdef)
            if hasattr(cls, tg.test_method_name):
                raise NameAlreadyRegisteredError(
                    f"a test with name '{tg.test_method_name}'"
                    " already exists")

            count += 1
            setattr(cls, tg.test_method_name, tg.test_method)

        if os.environ.get('TESTS_LOG_LEVEL_DEBUG', 'no') == 'yes':
            sys.stderr.write(f"[test template loader] loaded {count} "
                             f"templated test(s) from {path}\n")
        return cls

    return _inner


@dataclass(frozen=True)
class TemplatedTest():
    """
    Helper for working with templated tests i.e. Unit tests written in yaml
    that are then loaded, converted into unittest tests and run.

    This class implements the functionality to process the test results.
    """

    target_path: str
    data_root: dict
    sub_root: str
    mocks: dict = field(default_factory=lambda: {})
    expected_bugs: dict = field(default_factory=lambda: {})
    expected_issues: dict = field(default_factory=lambda: {})

    def __post_init__(self):
        if not os.path.exists(self.target_scenario_path):
            raise FileNotFoundError("Scenario file "
                                    f"{self.target_scenario_path}"
                                    " not found!")

    @property
    def target_scenario_path(self):
        return os.path.join(
            DEFS_DIR,
            self.sub_root,
            self.target_path
        )

    @staticmethod
    def check_raised_bugs(test_inst, expected, actual):
        """
        Compare what was raised vs what was expected.

        @param expected: dict of types and msgs
        @param actual: list of dicts from issue manager
        """

        if not expected:
            test_inst.assertNotIn('bugs-detected', actual)
            return

        if 'bugs-detected' not in actual:
            raise ExpectationNotMetError(
                "test expects one or more bugs to have "
                "been raised but did not find any.")

        _actual = {}
        for item in actual['bugs-detected']:
            _actual[item['id']] = item['message']

        # first check issue types
        test_inst.assertEqual(expected.keys(), _actual.keys())
        # then messages
        for bugurl in expected:
            test_inst.assertEqual(expected[bugurl], _actual[bugurl])

    @staticmethod
    def check_raised_issues(test_inst, expected, actual):
        """
        Compare what was raised vs what was expected.

        @param expected: dict of types and msgs
        @param actual: list of dicts from issue manager
        """

        if not expected:
            test_inst.assertNotIn('potential-issues', actual)
            return
        if 'potential-issues' not in actual:
            raise ExpectationNotMetError(
                "test expects one or more issues to have "
                "been raised did not find any.")
        _expected = {}
        for itype, items in expected.items():
            if itype not in _expected:
                _expected[itype] = set()

            if isinstance(items, list):
                for item in items:
                    _expected[itype].add(item)
            else:
                _expected[itype].add(items)

        _actual = {}
        for item in actual['potential-issues']:
            if item['type'] not in _actual:
                _actual[item['type']] = set()

            _actual[item['type']].add(item['message'])

        # first check issue types
        test_inst.assertEqual(_expected.keys(), _actual.keys())
        # then messages
        for itype in expected:
            test_inst.assertEqual(_expected[itype], _actual[itype])

    def __call__(self):
        @create_data_root(self.data_root.get('files'),
                          self.data_root.get('copy-from-original'))
        @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                    new=is_def_filter(self.target_path,
                                      self.sub_root))
        def inner(test_inst):
            patch_contexts = []
            if 'patch' in self.mocks:
                for target, patch_params in self.mocks['patch'].items():
                    patch_args = patch_params.get('args', [])
                    patch_kwargs = patch_params.get('kwargs', {})
                    c = mock.patch(target, *patch_args, **patch_kwargs)
                    patch_contexts.append(c)
                    c.start()

            if 'patch.object' in self.mocks:
                for target, patch_params in \
                        self.mocks['patch.object'].items():
                    mod, _, cls_name = target.rpartition('.')
                    obj = getattr(importlib.import_module(mod), cls_name)
                    patch_args = patch_params.get('args', [])
                    patch_kwargs = patch_params.get('kwargs', {})
                    c = mock.patch.object(obj, *patch_args, **patch_kwargs)
                    patch_contexts.append(c)
                    c.start()

            log.debug("running scenario under test")
            try:
                with GlobalSearcher() as searcher:
                    YScenarioChecker(searcher).run()

                raised_issues = IssuesManager().load_issues()
                raised_bugs = IssuesManager().load_bugs()
            finally:
                for c in patch_contexts:
                    c.stop()

            self.check_raised_bugs(
                test_inst,
                self.expected_bugs,
                raised_bugs
            )
            self.check_raised_issues(
                test_inst,
                self.expected_issues,
                raised_issues
            )

        return inner


class TemplatedTestGenerator():
    """
    Helper for working with templated tests i.e. Unit tests written in yaml
    that are then loaded, converted into unittest tests and run.
    """
    def __init__(self, test_defs_root, test_def_path):
        """
        @param test_defs_root: path under defs/tests where tests are located
        @param test_def_path: full path to test def.
        """
        self.test_defs_root = test_defs_root
        self.test_def_path = test_def_path

        if not os.path.exists(test_def_path):
            raise FileNotFoundError(f"{test_def_path} does not exist")

        with open(test_def_path, encoding='utf-8') as fd:
            self.testdef = yaml.safe_load(fd) or {}

        if not self.testdef:
            raise InvalidFileFormatError(
                f"invalid test template at {test_def_path}")

        _diff = set(self.testdef.keys()).difference(TEST_TEMPLATE_SCHEMA)
        if _diff:
            raise KeyError("invalid keys found in test template "
                           f"{test_def_path}: {_diff}")

        self.test_method = self._generate()

    @property
    def test_sub_path(self):
        """ Test def file path. """
        _path = os.path.join(DEFS_TESTS_DIR, self.test_defs_root)
        return self.test_def_path.partition(_path)[2].lstrip('/')

    @property
    def target_path(self):
        """ Target path with filename replaced with target-name if provided."""

        if self.testdef.get('target-name'):
            return os.path.join(os.path.dirname(self.test_sub_path),
                                self.testdef.get('target-name'))

        return self.test_sub_path

    @property
    def test_method_name(self):
        """ Test method name uses the original name. """
        name = os.path.splitext(self.test_sub_path)[0]
        replace_char = '_'
        chars_to_replace = ('/', '.')
        for char in chars_to_replace:
            name = name.replace(char, replace_char)
        return f'test_yscenario_{name}'

    def _generate(self):
        """ Generate a test from a template. """
        return TemplatedTest(
            target_path=self.target_path,
            sub_root=self.test_defs_root,
            data_root=self.testdef.get("data-root", {}),
            mocks=self.testdef.get("mock", {}),
            expected_bugs=self.testdef.get("raised-bugs"),
            expected_issues=self.testdef.get("raised-issues"),
        )()


def expand_log_template(template, hours=None, mins=None, secs=None,
                        lstrip=False):
    """
    Expand a given template log sequence using a sequence of hours/mins/secs.

    @param lstrip: optionally lstrip() the template before using it.
    """
    out = ""
    if lstrip:
        _template = template.lstrip()
    else:
        _template = template

    for hour in range(hours or 1):
        if hour < 10:
            hour = f"0{hour}"
        for minute in range(mins or 1):
            if minute < 10:
                minute = f"0{minute}"
            for sec in range(secs or 1):
                if sec < 10:
                    sec = f"0{sec}"
                out += _template.format(hour=hour, minute=minute, sec=sec)

    return out


def is_def_filter(def_path, sub_root):
    """
    Filter hotsos.core.ycheck.YDefsLoader._is_def to only match a file with the
    given name. This permits a unit test to only run the ydef checks that are
    under test.

    Note that in order for directory globals to run def_path must be a
    relative path that includes the parent directory name e.g. foo/bar.yaml
    where bar contains the checks and there is also a file called foo/foo.yaml
    that contains directory globals.

    @param def_path: path to yaml def relative to plugin defs root
    @param sub_root: plugin test defs root
    """
    def inner(_inst, abs_path):
        log.debug("filter def: %s (%s)", def_path, abs_path)
        if not abs_path.endswith(def_path) or sub_root not in abs_path:
            return False

        # filename may optionally have a parent dir which allows us to permit
        # directory globals to be run.
        parent_dir = os.path.dirname(def_path)
        # Ensure we only load/run the yaml def with the given name.
        if parent_dir:
            log.debug("parent_dir=%s", parent_dir)

            # strip down to relative path
            _root_dir = os.path.join(HotSOSConfig.plugin_yaml_defs, sub_root)
            _rel_path = re.sub(_root_dir, '', abs_path).lstrip('/')
            base_dir = os.path.dirname(_rel_path)
            if not base_dir:
                # if path is a file with no dirs it must be a match.
                return True

            if base_dir != parent_dir:
                return False

            if os.path.basename(abs_path) == f"{parent_dir}.yaml":
                log.debug("files loaded so far=%s",
                          _inst.stats_num_files_loaded)
                assert _inst.stats_num_files_loaded < 2
                return True

        log.debug("abs_path=%s", abs_path)
        if abs_path.endswith(def_path):
            log.debug("files loaded so far=%s",
                      _inst.stats_num_files_loaded)
            assert _inst.stats_num_files_loaded < 2
            return True

        return False

    return inner


def create_data_root(files_to_create, copy_from_original=None):
    """
    Decorator helper to create any number of files with provided content within
    a temporary data_root.

    @param files_to_create: a dictionary of <filename>: <contents> pairs.
    @param copy_from_original: a list of files to copy from the original
                                     data root into this test one.
    """

    def create_files_inner1(f):
        def create_files_inner2(*args, **kwargs):
            if files_to_create is None:
                return f(*args, **kwargs)

            _copy_from_original = copy_from_original or []
            # This almost always needs to exist otherwise hotsos.core.search
            # will fail to create a search constraints object.
            date_path = 'sos_commands/date/date'
            if (date_path not in files_to_create and
                    date_path not in _copy_from_original):
                _copy_from_original.append(date_path)

            with tempfile.TemporaryDirectory() as dtmp:
                for path in _copy_from_original:
                    src = os.path.join(HotSOSConfig.data_root, path)
                    dst = os.path.join(dtmp, path)
                    if not os.path.exists(os.path.dirname(dst)):
                        os.makedirs(os.path.dirname(dst))

                    if os.path.isfile(src):
                        shutil.copy(src, dst)
                    else:
                        shutil.copytree(src, dst)

                log_artifacts = os.environ.get('TESTS_LOG_TEST_ARTIFACTS',
                                               'no') == 'yes'

                for path, content in files_to_create.items():
                    path = os.path.join(dtmp, path)
                    if not os.path.exists(os.path.dirname(path)):
                        os.makedirs(os.path.dirname(path))

                    log.debug("creating test file %s", path)
                    if log_artifacts:
                        log.debug("test file contents\n%s", "\n".join(
                            [f'{path}: {line}'
                             for line in content.split("\n")]))

                    with open(path, 'w', encoding='utf-8') as fd:
                        fd.write(content)

                orig_data_root = HotSOSConfig.data_root
                HotSOSConfig.data_root = dtmp
                ret = f(*args, **kwargs)
                HotSOSConfig.data_root = orig_data_root
                return ret

        return create_files_inner2

    return create_files_inner1


def global_search_context(f):
    def global_search_context_inner(inst, *args, **kwargs):
        with GlobalSearcher() as searcher:
            return f(inst, searcher, *args, **kwargs)

    return global_search_context_inner


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
                yfile = os.path.join(yroot, f'{sname}.yaml')
                os.makedirs(os.path.dirname(yfile))
                with open(yfile, 'w', encoding='utf-8') as fd:
                    fd.write(yaml_contents)
                return f(*args, **kwargs)

        return init_test_scenario_inner2
    return init_test_scenario_inner1


class BaseTestCase(unittest.TestCase):
    """ Custom TestCase to be used by all tests. """
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.global_tmp_dir = None
        self.plugin_tmp_dir = None
        self.hotsos_config = {'data_root':
                              os.path.join(TESTS_DIR, DEFAULT_FAKE_ROOT),
                              'plugin_name': 'testplugin',
                              'plugin_yaml_defs':
                              os.path.join(HOTSOS_ROOT, 'defs'),
                              'templates_path':
                              os.path.join(HOTSOS_ROOT, 'templates'),
                              'part_name': 'testpart',
                              'global_tmp_dir': None,
                              'plugin_tmp_dir': None,
                              'use_all_logs': True,
                              'machine_readable': True,
                              'debug_mode': True}

    @staticmethod
    def part_output_to_actual(output):
        actual = {}
        for key, entry in output.items():
            actual[key] = entry.data

        return actual

    def setUp(self):
        self.maxDiff = None  # pylint: disable=invalid-name
        # ensure locale consistency wherever tests are run
        os.environ["LANG"] = 'C.UTF-8'
        # Always reset env globals
        HotSOSConfig.set(**self.hotsos_config)
        if not self.global_tmp_dir:
            self.global_tmp_dir = tempfile.mkdtemp()
            self.plugin_tmp_dir = tempfile.mkdtemp(dir=self.global_tmp_dir)
            HotSOSConfig.global_tmp_dir = self.global_tmp_dir
            HotSOSConfig.plugin_tmp_dir = self.plugin_tmp_dir

        if os.environ.get('TESTS_LOG_LEVEL_DEBUG', 'no') == 'yes':
            LoggingManager().start()
        else:
            HotSOSConfig.debug_log_levels['searchkit'] = 'WARNING'
            LoggingManager().start(level=logging.WARNING)

    def _addDuration(self, *args, **kwargs):  # pylint: disable=invalid-name
        """ Python >=3.12 needs subclasses of unittest.TestCase to implement
        this in order to record times and execute any cleanup actions once
        a test completes regardless of success. Otherwise it emits a warning.
        This generic implementation helps suppress it and possibly others in
        the future. """

    def tearDown(self):
        LoggingManager().stop()
        HotSOSConfig.reset()
        HotSOSConfig.set(**self.hotsos_config)
        shutil.rmtree(self.global_tmp_dir)
