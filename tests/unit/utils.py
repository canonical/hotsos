import os
import importlib
import mock
import yaml

import shutil
import tempfile
import unittest

# disable for stestr otherwise output is much too verbose
from hotsos.core.log import log, logging, setup_logging
from hotsos.core.config import HotSOSConfig

from hotsos.core.issues import IssuesManager
from hotsos.core.ycheck.scenarios import YScenarioChecker

# Must be set prior to other imports
TESTS_DIR = os.environ["TESTS_DIR"]
DEFS_TESTS_DIR = os.path.join(os.environ['TESTS_DIR'], 'defs', 'tests')
DEFAULT_FAKE_ROOT = 'fake_data_root/openstack'
HotSOSConfig.data_root = os.path.join(TESTS_DIR, DEFAULT_FAKE_ROOT)
TEST_TEMPLATE_SCHEMA = set(['target-name', 'data-root', 'mock',
                            'raised-issues', 'raised-bugs'])


def find_all_templated_tests(path):
    for testdef in os.listdir(path):
        if testdef.endswith('.disabled'):
            continue

        defpath = os.path.join(path, testdef)
        if os.path.isdir(defpath):
            for subpath in find_all_templated_tests(defpath):
                yield subpath
        else:
            yield defpath


def load_templated_tests(path):
    """ Add templated tests to the runner.

    @param path: relative path to test templates we want to load under
                 defs/tests.
    """
    def _inner(cls):
        _path = os.path.join(DEFS_TESTS_DIR, path)
        for testdef in find_all_templated_tests(_path):
            tg = TemplatedTestGenerator(path, testdef)
            if hasattr(cls, tg.test_method_name):
                raise Exception("test name conflict for '{}' - "
                                "a test with this name already exists".
                                format(tg.test_method_name))

            setattr(cls, tg.test_method_name, tg.test_method)

        return cls

    return _inner


class TemplatedTest(object):

    def __init__(self, target_path, data_root, mocks, expected_bugs,
                 expected_issues):
        self.target_path = target_path
        self.data_root = data_root
        self.mocks = mocks
        self.expected_bugs = expected_bugs
        self.expected_issues = expected_issues

    def check_raised_bugs(self, test_inst, expected, actual):
        """
        Compare what was raised vs what was expected.

        @param expected: dict of types and msgs
        @param actual: list of dicts from issue manager
        """

        if not expected:
            test_inst.assertTrue('bugs-detected' not in actual)
            return

        actual = {item['id']: item['desc'] for item in actual['bugs-detected']}
        # first check issue types
        test_inst.assertEqual(expected.keys(), actual.keys())
        # then messages
        for bugurl in expected:
            test_inst.assertEqual(expected[bugurl], actual[bugurl])

    def check_raised_issues(self, test_inst, expected, actual):
        """
        Compare what was raised vs what was expected.

        @param expected: dict of types and msgs
        @param actual: list of dicts from issue manager
        """

        if not expected:
            test_inst.assertTrue('potential-issues' not in actual)
            return

        _expected = {}
        for itype, msgs in expected.items():
            if itype not in _expected:
                _expected[itype] = set()

            if type(msgs) == list:
                for msg in msgs:
                    _expected[itype].add(msg)
            else:
                _expected[itype].add(msgs)

        _actual = {}
        for item in actual['potential-issues']:
            if item['type'] not in _actual:
                _actual[item['type']] = set()

            _actual[item['type']].add(item['desc'])

        # first check issue types
        test_inst.assertEqual(_expected.keys(), _actual.keys())
        # then messages
        for itype in expected:
            test_inst.assertEqual(_expected[itype], _actual[itype])

    def __call__(self):
        @create_data_root(self.data_root.get('files'),
                          self.data_root.get('copy-from-original'))
        @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                    new=is_def_filter(self.target_path))
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
                for target, patch_params in self.mocks['patch.object'].items():
                    mod, _, cls_name = target.rpartition('.')
                    obj = getattr(importlib.import_module(mod), cls_name)
                    patch_args = patch_params.get('args', [])
                    patch_kwargs = patch_params.get('kwargs', {})
                    c = mock.patch.object(obj, *patch_args, **patch_kwargs)
                    patch_contexts.append(c)
                    c.start()

            try:
                YScenarioChecker()()
                raised_issues = IssuesManager().load_issues()
                raised_bugs = IssuesManager().load_bugs()
            finally:
                for c in patch_contexts:
                    c.stop()

            self.check_raised_bugs(test_inst, self.expected_bugs, raised_bugs)
            self.check_raised_issues(test_inst, self.expected_issues,
                                     raised_issues)

        return inner


class TemplatedTestGenerator(object):

    def __init__(self, test_defs_root, test_def_path):
        """
        @param test_defs_root: path under defs/tests where tests are located
        @param test_def_path: full path to test def.
        """
        self.test_defs_root = test_defs_root
        self.test_def_path = test_def_path

        if not os.path.exists(test_def_path):
            raise Exception("{} does not exist".format(test_def_path))

        self.testdef = yaml.safe_load(open(test_def_path)) or {}
        if not self.testdef or not os.path.exists(test_def_path):
            raise Exception("invalid test template at {}".
                            format(test_def_path))

        _diff = set(self.testdef.keys()).difference(TEST_TEMPLATE_SCHEMA)
        if _diff:
            raise Exception("invalid keys found in test template {}: {}".
                            format(test_def_path, _diff))

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
        name = self.test_sub_path.split('.')[0]
        name = name.replace('/', '_')
        return 'test_{}'.format(name)

    def _generate(self):
        """ Generate a test from a template. """
        data_root = self.testdef.get('data-root', {})
        mocks = self.testdef.get('mock', {})
        bugs = self.testdef.get('raised-bugs')
        issues = self.testdef.get('raised-issues')
        return TemplatedTest(self.target_path, data_root, mocks, bugs,
                             issues)()


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
            hour = "0{}".format(hour)
        for min in range(mins or 1):
            if min < 10:
                min = "0{}".format(min)
            for sec in range(secs or 1):
                if sec < 10:
                    sec = "0{}".format(sec)
                out += _template.format(hour=hour, min=min, sec=sec)

    return out


def is_def_filter(def_filename):
    """
    Filter hotsos.core.ycheck.YDefsLoader._is_def to only match a file with the
    given name. This permits a unit test to only run the ydef checks that are
    under test.

    Note that in order for directory globals to run def_filename must be a
    relative path that includes the parent directory name e.g. foo/bar.yaml
    where bar contains the checks and there is also a file called foo/foo.yaml
    that contains directory globals.
    """
    def inner(_inst, abs_path):
        log.debug("filter def: %s", def_filename)
        # filename may optionally have a parent dir which allows us to permit
        # directory globals to be run.
        parent_dir = os.path.dirname(def_filename)
        """ Ensure we only load/run the yaml def with the given name. """
        if parent_dir:
            log.debug("parent_dir=%s", parent_dir)
            # allow directory global to run
            base_dir = os.path.basename(os.path.dirname(abs_path))
            if base_dir != parent_dir:
                return False

            if os.path.basename(abs_path) == "{}.yaml".format(parent_dir):
                log.debug("files loaded so far=%s",
                          _inst.stats_num_files_loaded)
                assert _inst.stats_num_files_loaded < 2
                return True

        if abs_path.endswith(def_filename):
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

            with tempfile.TemporaryDirectory() as dtmp:
                for _file in copy_from_original or []:
                    src = os.path.join(HotSOSConfig.data_root, _file)
                    dst = os.path.join(dtmp, _file)
                    if not os.path.exists(os.path.dirname(dst)):
                        os.makedirs(os.path.dirname(dst))

                    shutil.copy(src, dst)

                for path, content in files_to_create.items():
                    path = os.path.join(dtmp, path)
                    if not os.path.exists(os.path.dirname(path)):
                        os.makedirs(os.path.dirname(path))

                    log.debug("creating test file %s", path)
                    with open(path, 'w') as fd:
                        fd.write(content)

                orig_data_root = HotSOSConfig.data_root
                HotSOSConfig.data_root = dtmp
                ret = f(*args, **kwargs)
                HotSOSConfig.data_root = orig_data_root
                return ret

        return create_files_inner2

    return create_files_inner1


class BaseTestCase(unittest.TestCase):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.global_tmp_dir = None
        self.plugin_tmp_dir = None
        self.hotsos_config = {'data_root':
                              os.path.join(TESTS_DIR, DEFAULT_FAKE_ROOT),
                              'plugin_name': 'testplugin',
                              'plugin_yaml_defs':
                              os.path.join(TESTS_DIR, 'defs'),
                              'part_name': 'testpart',
                              'global_tmp_dir': None,
                              'plugin_tmp_dir': None,
                              'use_all_logs': True,
                              'machine_readable': True}

    def part_output_to_actual(self, output):
        actual = {}
        for key, entry in output.items():
            actual[key] = entry.data

        return actual

    def setUp(self):
        self.maxDiff = None
        # ensure locale consistency wherever tests are run
        os.environ["LANG"] = 'C.UTF-8'
        # Always reset env globals
        HotSOSConfig.set(**self.hotsos_config)
        self.global_tmp_dir = tempfile.mkdtemp()
        self.plugin_tmp_dir = tempfile.mkdtemp(dir=self.global_tmp_dir)
        HotSOSConfig.global_tmp_dir = self.global_tmp_dir
        HotSOSConfig.plugin_tmp_dir = self.plugin_tmp_dir
        setup_logging()
        log.setLevel(logging.INFO)

    def tearDown(self):
        HotSOSConfig.reset()
        HotSOSConfig.set(**self.hotsos_config)
        shutil.rmtree(self.global_tmp_dir)
