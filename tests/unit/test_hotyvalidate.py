import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from hotsos.core.config import HotSOSConfig
from tools.validation.hotyvalidate import HotYValidate, configure_defs_dir


class TestHotYValidate(unittest.TestCase):
    """Regression tests for standalone validator configuration."""

    def setUp(self):
        super().setUp()
        self.addCleanup(setattr, HotSOSConfig, 'plugin_yaml_defs',
                        HotSOSConfig.plugin_yaml_defs)
        HotSOSConfig.plugin_yaml_defs = None
        env = mock.patch.dict(os.environ, {}, clear=True)
        env.start()
        self.addCleanup(env.stop)

    def test_preserve_configured_defs(self):
        """Keep caller configuration ahead of environment overrides."""
        HotSOSConfig.plugin_yaml_defs = '/configured/defs'
        os.environ['HOTSOS_DEFS_DIR'] = '/override/defs'
        os.environ['HOTSOS_ROOT'] = '/hotsos'
        configure_defs_dir()
        self.assertEqual(HotSOSConfig.plugin_yaml_defs, '/configured/defs')

    def test_explicit_defs_override(self):
        """Prefer the explicit definitions directory over HOTSOS_ROOT."""
        os.environ['HOTSOS_DEFS_DIR'] = '/override/defs'
        os.environ['HOTSOS_ROOT'] = '/hotsos'
        configure_defs_dir()
        self.assertEqual(HotSOSConfig.plugin_yaml_defs, '/override/defs')

    def test_defs_override_without_root(self):
        """Allow an explicit definitions directory without HOTSOS_ROOT."""
        os.environ['HOTSOS_DEFS_DIR'] = '/override/defs'
        configure_defs_dir()
        self.assertEqual(HotSOSConfig.plugin_yaml_defs, '/override/defs')

    def test_root_fallback(self):
        """Derive the definitions directory when the override is empty."""
        os.environ['HOTSOS_DEFS_DIR'] = ''
        os.environ['HOTSOS_ROOT'] = '/hotsos'
        configure_defs_dir()
        self.assertEqual(HotSOSConfig.plugin_yaml_defs, '/hotsos/defs')

    def test_missing_configuration(self):
        """Reject unconfigured direct calls instead of skipping discovery."""
        validator = HotYValidate()
        for method in (configure_defs_dir,
                       validator.scenarios_check_mappings,
                       validator.scenarios_check_data_root_files):
            with self.subTest(method=method.__name__):
                with self.assertRaisesRegex(
                        RuntimeError,
                        'HOTSOS_ROOT or HOTSOS_DEFS_DIR must be set'):
                    method()
                self.assertIsNone(HotSOSConfig.plugin_yaml_defs)

    def test_imported_validation_methods_configure_discovery(self):
        """Initialize both imported entry points and honor target-name."""
        with tempfile.TemporaryDirectory() as root:
            defs = Path(root) / 'defs'
            scenarios = defs / 'scenarios' / 'kernel'
            tests = defs / 'tests' / 'scenarios' / 'kernel'
            scenarios.mkdir(parents=True)
            tests.mkdir(parents=True)
            (scenarios / 'example.yaml').write_text(
                'checks: {}\nconclusions: {}\n', encoding='utf-8')
            (tests / 'example_alt.yaml').write_text(
                'target-name: example.yaml\nraised-issues: {}\n',
                encoding='utf-8')

            validator = HotYValidate()
            for env in ({'HOTSOS_ROOT': root},
                        {'HOTSOS_DEFS_DIR': str(defs)}):
                for method in (validator.scenarios_check_mappings,
                               validator.scenarios_check_data_root_files):
                    with self.subTest(env=env, method=method.__name__):
                        HotSOSConfig.plugin_yaml_defs = None
                        with mock.patch.dict(os.environ, env, clear=True):
                            method()
                        self.assertEqual(HotSOSConfig.plugin_yaml_defs,
                                         str(defs))
                        self.assertEqual(
                            # pylint: disable-next=protected-access
                            validator._discover_tests(),
                            ([str(tests / 'example_alt.yaml')],
                             {str(scenarios / 'example.yaml'):
                              [str(tests / 'example_alt.yaml')]}))
