import abc
import os

import yaml
from hotsos.core.config import HotSOSConfig
from hotsos.core.exceptions import InvalidFileFormatError
from hotsos.core.log import log

SCENARIOS_SUBDIR = 'scenarios'
TESTS_SUBDIR = 'tests'

# Set of keys allowed at the top level of a templated scenario test yaml.
TEST_TEMPLATE_SCHEMA = frozenset({'target-name', 'data-root', 'mock',
                                  'raised-issues', 'raised-bugs'})


def get_defs_dir():
    """
    Return the currently configured yaml defs root as an absolute,
    normalised path (or None if the option has not been set yet).

    Resolved on every call so that changes to HotSOSConfig made after this
    module has been imported (e.g. during test setup) are honoured.
    """
    defs = HotSOSConfig.plugin_yaml_defs
    if not defs:
        return None
    return os.path.abspath(os.path.normpath(defs))


def get_defs_tests_dir():
    """
    Return <defs>/tests as an absolute path (or None if defs is not set).
    """
    defs = get_defs_dir()
    return os.path.join(defs, TESTS_SUBDIR) if defs else None


def load_test_def(abs_path):
    """
    Load a templated-test yaml file and validate its top-level schema.

    @param abs_path: absolute path to the test yaml.
    @return: parsed dict.
    @raises FileNotFoundError: if abs_path does not exist.
    @raises InvalidFileFormatError: if the yaml is not a non-empty mapping.
    @raises yaml.YAMLError: if the file contains malformed yaml.
    @raises KeyError: if the yaml contains unknown top-level keys.
    """
    if not os.path.exists(abs_path):
        raise FileNotFoundError(f"{abs_path} does not exist")

    with open(abs_path, encoding='utf-8') as fd:
        testdef = yaml.safe_load(fd)

    if not isinstance(testdef, dict) or not testdef:
        raise InvalidFileFormatError(
            f"invalid test template at {abs_path}: expected a non-empty "
            "mapping")

    diff = set(testdef).difference(TEST_TEMPLATE_SCHEMA)
    if diff:
        raise KeyError(
            f"invalid keys found in test template {abs_path}: {diff}")

    return testdef


def resolve_target_scenario_path(test_abs_path, testdef=None):
    """
    Return the absolute path of the scenario yaml targeted by a templated
    test file.

    The mapping is:
      <defs>/tests/scenarios/<rel>  ->  <defs>/scenarios/<rel>
    where <rel> is the test path relative to <defs>/tests/scenarios,
    with the basename optionally replaced by the test's 'target-name'
    field, which must be a non-empty basename (not a path).

    @param test_abs_path: absolute path to the test yaml (must live under
                          <defs>/tests/scenarios).
    @param testdef: optionally the already-loaded test dict, to avoid
                    reading the file twice.
    @raises ValueError: if the test path is not absolute or is outside the
                        scenario-test directory, or target-name is invalid.
    """
    tests_root = get_defs_tests_dir()
    defs_dir = get_defs_dir()
    if not tests_root or not defs_dir:
        raise RuntimeError(
            "HotSOSConfig.plugin_yaml_defs is not set; cannot resolve "
            "target scenario path")

    tests_scenarios_root = os.path.join(tests_root, SCENARIOS_SUBDIR)
    if not os.path.isabs(test_abs_path):
        raise ValueError(f"test path must be absolute: {test_abs_path}")

    test_abs_path = os.path.normpath(test_abs_path)
    if (os.path.commonpath([tests_scenarios_root, test_abs_path])
            != tests_scenarios_root
            or test_abs_path == tests_scenarios_root):
        raise ValueError(
            f"test path must be under {tests_scenarios_root}: {test_abs_path}")

    rel = os.path.relpath(test_abs_path, tests_scenarios_root)

    if testdef is None:
        testdef = load_test_def(test_abs_path)

    target_name = testdef.get('target-name')
    if target_name is not None:
        if (not isinstance(target_name, str)
                or target_name in ('', '.', '..')
                or '/' in target_name or '\\' in target_name
                or '\0' in target_name):
            raise ValueError(
                f"target-name must be a non-empty basename: {target_name!r}")
        rel = os.path.join(os.path.dirname(rel), target_name)

    return os.path.join(defs_dir, SCENARIOS_SUBDIR, rel)


class YDefsLoader():
    """ Load yaml definitions with support for file discovery and
    filtering.
    """

    def __init__(self, ytype, filter_path=None):
        """
        @param ytype: the type of defs we are loading i.e. defs/<ytype>
        @param filter_path: optional path filter for YAML content
        """
        self.ytype = ytype
        self._loaded_defs = None
        self.stats_num_files_loaded = 0
        self.filter_path = filter_path

    @staticmethod
    def _walk(path):
        """Yield absolute paths of every file under path recursively.

        No filtering is applied by the walker itself; callers are
        responsible for filtering yielded paths as needed.
        """
        for root, _dirs, files in os.walk(path):
            for name in files:
                yield os.path.join(root, name)

    @staticmethod
    def _is_def(abs_path):
        return abs_path.endswith('.yaml')

    @staticmethod
    def _get_yname(path):
        return os.path.basename(path).partition('.yaml')[0]

    def _get_defs_recursive(self, path):
        """ Recursively load yaml files beneath a directory into
        a nested dict. """
        defs = {}
        # Process immediate children first
        for entry in os.listdir(path):
            abs_path = os.path.join(path, entry)
            if os.path.isdir(abs_path):
                subdefs = self._get_defs_recursive(abs_path)
                if subdefs:
                    defs[os.path.basename(abs_path)] = subdefs
            elif self._is_def(abs_path):
                # Process yaml files using shared filtering logic
                if self._get_yname(abs_path) == os.path.basename(path):
                    with open(abs_path, encoding='utf-8') as fd:
                        log.debug("applying dir globals %s", entry)
                        defs.update(yaml.safe_load(fd.read()) or {})

                    # NOTE: these files do not count towards the total loaded
                    # since they are only supposed to contain directory-level
                    # globals that apply to other definitions in or below this
                    # directory.
                    continue

                with open(abs_path, encoding='utf-8') as fd:
                    self.stats_num_files_loaded += 1
                    _content = yaml.safe_load(fd.read()) or {}
                    defs[self._get_yname(abs_path)] = _content

        return defs

    def _apply_filter(self, loaded):
        """
        If a path filter has been provided, exclude any/all properties that
        are not descendants of that path.
        """
        if not self.filter_path:
            return loaded

        groups = self.filter_path.split('.')
        for i, subgroup in enumerate(groups):
            if i == 0:
                loaded = {subgroup: loaded[subgroup]}
            else:
                prev = groups[i - 1]
                loaded[prev] = {subgroup: loaded[prev][subgroup]}

        return loaded

    @property
    def plugin_defs(self):
        """ Load yaml defs for the current plugin and type. """
        log.debug('loading %s definitions for plugin=%s', self.ytype,
                  HotSOSConfig.plugin_name)

        if self._loaded_defs:
            return self._loaded_defs

        path = os.path.join(HotSOSConfig.plugin_yaml_defs, self.ytype,
                            HotSOSConfig.plugin_name)
        # reset
        self.stats_num_files_loaded = 0
        if os.path.isdir(path):
            loaded = self._get_defs_recursive(path)
            log.debug("YDefsLoader: plugin %s loaded %s file(s)",
                      HotSOSConfig.plugin_name, self.stats_num_files_loaded)
            # only return if we loaded actual definitions (not just globals)
            if self.stats_num_files_loaded:
                loaded = self._apply_filter(loaded)
                self._loaded_defs = loaded
                return loaded

        return {}

    @staticmethod
    def find_files_recursively(path, file_filter=None):
        """ Find files under path without loading them.

        Only YAML (.yaml) files are yielded; every other file (including
        editor/disabled artefacts such as *.swp and *.disabled, which do not
        end in .yaml) is skipped. Callers that want to further narrow the
        result should pass a file_filter, which is applied on top of the
        yaml-only filter.

        @param path: absolute directory to search.
        @param file_filter: optional callable taking an absolute file path
                            and returning True to skip the file.
        """
        if not path or not os.path.isdir(path):
            log.debug("search path not found: %s", path)
            return
        for abs_path in YDefsLoader._walk(path):
            # Skip all non-yaml files as well as any file rejected by the
            # optional caller-provided filter.
            if (YDefsLoader._default_scenario_file_filter(abs_path)
                    or (file_filter is not None and file_filter(abs_path))):
                continue
            yield abs_path

    @staticmethod
    def _default_scenario_file_filter(abs_path):
        """Filter everything but .yaml files."""
        return not YDefsLoader._is_def(abs_path)

    @staticmethod
    def get_scenario_files(subpath=None, file_filter=None):
        """ Find all scenario definition YAML files.

        @param subpath: optional path relative to <defs>/scenarios to
                        narrow the search to.
        @param file_filter: optional extra callable(abs_path)->bool filter,
                            returning True to skip the file (exclude).
        """
        defs_dir = get_defs_dir()
        if not defs_dir:
            return
        base = os.path.join(defs_dir, SCENARIOS_SUBDIR)

        if subpath:
            norm_subpath = os.path.normpath(subpath)

            if (os.path.isabs(norm_subpath) or norm_subpath == '..'
                    or norm_subpath.startswith('..' + os.sep)):
                raise ValueError(
                    f"subpath must be relative to {base}: {subpath}")

            target = os.path.join(base, norm_subpath)
        else:
            target = base
        yield from YDefsLoader.find_files_recursively(target, file_filter)

    @staticmethod
    def get_scenario_test_files(subpath=None, file_filter=None):
        """ Find all scenario test YAML files.

        @param subpath: optional path relative to <defs>/tests to narrow
                        the search to (e.g. 'scenarios/kernel'). Kept
                        relative to <defs>/tests (not <defs>/tests/scenarios)
        @param file_filter: optional extra callable(abs_path)->bool filter,
                            returning True to skip the file (exclude).
        """
        tests_dir = get_defs_tests_dir()
        if not tests_dir:
            return
        target = os.path.join(tests_dir, subpath) if subpath else tests_dir
        yield from YDefsLoader.find_files_recursively(target, file_filter)


class YHandlerBase():
    """
    Base class for all YAML handler types e.g. scenario and event handlers.
    """
    def __init__(self, global_searcher, *args, **kwargs):
        self.global_searcher = global_searcher
        super().__init__(*args, **kwargs)

    @abc.abstractmethod
    def run(self):
        """ Process operations. """
