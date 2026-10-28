import importlib.metadata
import os
import tempfile
from unittest import mock

from hotsos.client import HotSOSSummary
from hotsos.core.config import HotSOSConfig

from . import utils


class TestHotSOSSummary(utils.BaseTestCase):
    """ Unit tests for the hotsos plugin summary. """

    @staticmethod
    def _touch(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as fd:
            fd.write('{}\n')

    def test_summary(self):
        """Test hotsos summary includes defs counts and dependencies."""
        with tempfile.TemporaryDirectory() as dtmp:
            for path in ['events/p1/p1.yaml',  # globals, not counted
                         'events/p1/e1.yaml',
                         'events/p1/sub/sub.yaml',
                         'events/p1/sub/e2.yaml',
                         'events/p1/e3.yaml.disabled',
                         'events/p2/e1.yaml',
                         'scenarios/p1/s1.yaml',
                         'scenarios/p2/p2.yaml',
                         'scenarios/p2/s2.yaml',
                         'scenarios/p2/s3.yaml']:
                self._touch(os.path.join(dtmp, path))

            HotSOSConfig.plugin_yaml_defs = dtmp
            HotSOSConfig.hotsos_version = '1.0'
            with mock.patch.object(importlib.metadata, 'version',
                                   side_effect=lambda pkg: f'{pkg}-ver'):
                actual = HotSOSSummary().summary

        self.assertEqual(actual,
                         {'version': '1.0',
                          'repo-info': None,
                          'events': {'p1': 2, 'p2': 1},
                          'scenarios': {'p1': 1, 'p2': 2},
                          'dpkg': ['propertree propertree-ver',
                                   'searchkit searchkit-ver']})

    def test_count_defs_unconfigured(self):
        """No definitions directory produces an empty plugin mapping."""
        HotSOSConfig.plugin_yaml_defs = None
        self.assertEqual(HotSOSSummary._count_defs('events'), {})
        self.assertEqual(HotSOSSummary._count_defs('scenarios'), {})

    def test_summary_deps_not_found(self):
        """Test dpkg section omitted if dependency versions are unknown."""
        with mock.patch.object(importlib.metadata, 'version',
                               side_effect=importlib.metadata.
                               PackageNotFoundError):
            actual = HotSOSSummary().summary

        self.assertNotIn('dpkg', actual)
        self.assertGreater(sum(actual['events'].values()), 0)
        self.assertGreater(sum(actual['scenarios'].values()), 0)
