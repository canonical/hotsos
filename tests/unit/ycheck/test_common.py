from pathlib import Path
from unittest import mock

from hotsos.core.config import HotSOSConfig
from hotsos.core.exceptions import InvalidFileFormatError
from hotsos.core.ycheck.common import GlobalSearcherPreloaderBase
from hotsos.core.ycheck.engine.common import (
    load_test_def,
    resolve_target_scenario_path,
)

from .. import utils


class TestScenarioTestDefinitions(utils.BaseTestCase):
    """Tests for loading scenario tests and resolving their targets."""

    def setUp(self):
        super().setUp()
        self.defs = Path(self.plugin_tmp_dir) / 'defs'
        HotSOSConfig.plugin_yaml_defs = str(self.defs)
        self.tests_root = self.defs / 'tests' / 'scenarios'
        self.test_path = self.tests_root / 'kernel' / 'nested' / 'test.yaml'
        self.test_path.parent.mkdir(parents=True)

    def test_load_valid_mapping(self):
        """Return a mapping with recognized top-level keys."""
        self.test_path.write_text('raised-issues: {}\n', encoding='utf-8')
        self.assertEqual(load_test_def(self.test_path), {'raised-issues': {}})

    def test_reject_non_mapping_and_empty_templates(self):
        """Reject scalars, sequences and empty templates consistently."""
        for content in ('', '{}', 'null', '[]', '[raised-issues]',
                        '- {raised-issues: {}}', 'raised-issues', '42',
                        'true', 'false', '0'):
            with self.subTest(content=content):
                self.test_path.write_text(content, encoding='utf-8')
                with self.assertRaisesRegex(InvalidFileFormatError,
                                            'expected a non-empty mapping'):
                    load_test_def(self.test_path)

    def test_reject_unknown_keys(self):
        """Preserve schema validation for mapping keys."""
        self.test_path.write_text('unknown-key: {}\n', encoding='utf-8')
        with self.assertRaisesRegex(KeyError, 'invalid keys'):
            load_test_def(self.test_path)

    def test_missing_template(self):
        """Report a missing template before loading YAML."""
        with self.assertRaises(FileNotFoundError):
            load_test_def(self.test_path)

    def test_resolve_nested_target(self):
        """Map nested tests with and without a target-name override."""
        target_dir = self.defs / 'scenarios' / 'kernel' / 'nested'
        for testdef, name in (({}, 'test.yaml'),
                              ({'target-name': None}, 'test.yaml'),
                              ({'target-name': 'other.yaml'}, 'other.yaml')):
            with self.subTest(testdef=testdef):
                self.assertEqual(
                    resolve_target_scenario_path(self.test_path, testdef),
                    str(target_dir / name))

    def test_resolve_loaded_target(self):
        """Load the template when the caller does not supply a mapping."""
        self.test_path.write_text('target-name: other.yaml\n',
                                  encoding='utf-8')
        self.assertEqual(
            resolve_target_scenario_path(self.test_path),
            str(self.defs / 'scenarios' / 'kernel' / 'nested' / 'other.yaml'))

    def test_normalize_test_path(self):
        """Normalize internal parent components without changing the target."""
        test_path = self.test_path.parent / '..' / 'nested' / 'test.yaml'
        self.assertEqual(
            resolve_target_scenario_path(test_path, {}),
            resolve_target_scenario_path(self.test_path, {}))

    def test_reject_paths_outside_tests(self):
        """Reject escapes and sibling-prefix paths before reading a file."""
        paths = (
            self.defs / 'outside.yaml',
            self.tests_root / '..' / 'outside.yaml',
            self.defs / 'tests' / 'scenarios-other' / 'test.yaml',
            self.tests_root,
            'relative/test.yaml',
        )
        with mock.patch(
                'hotsos.core.ycheck.engine.common.load_test_def') as load:
            for path in paths:
                with self.subTest(path=path):
                    with self.assertRaisesRegex(ValueError, 'test path must'):
                        resolve_target_scenario_path(path)
            load.assert_not_called()

    def test_reject_invalid_target_names(self):
        """Reject traversal, absolute paths and non-basename overrides."""
        for name in ('', '.', '..', '../other.yaml', '/other.yaml',
                     'nested/other.yaml', 'nested/../other.yaml',
                     'other.yaml/', r'..\other.yaml', 'bad\0name',
                     [], {}, 42, False):
            with self.subTest(name=name):
                with self.assertRaisesRegex(ValueError,
                                            'target-name must be'):
                    resolve_target_scenario_path(
                        self.test_path, {'target-name': name})


class TestYcheckCommon(utils.BaseTestCase):
    """
    Tests common ycheck functionality.
    """

    def test_skip_filtered(self):
        """ Test skip_filtered with various prefix/path combos. """
        pf = 'a.b.c'
        p = 'a.b.c.d'
        self.assertFalse(GlobalSearcherPreloaderBase.skip_filtered(pf, p))
        pf = 'a.b.c.e'
        self.assertTrue(GlobalSearcherPreloaderBase.skip_filtered(pf, p))
        pf = 'a.b.c'
        p = 'a.b'
        self.assertTrue(GlobalSearcherPreloaderBase.skip_filtered(pf, p))
        pf = 'a.b.*'
        p = 'a.b.c'
        self.assertFalse(GlobalSearcherPreloaderBase.skip_filtered(pf, p))
