import os
import sys
import tempfile

import unittest
from unittest import mock

import hotsos.cli


class TestCLI(unittest.TestCase):

    def test_get_hotsos_root(self):
        with mock.patch.object(sys, 'argv', ['/usr/bin/hotsos', '1', '2']):
            self.assertEqual(hotsos.cli.get_hotsos_root(), '/usr/bin')

    def test_get_version_exists(self):
        with mock.patch.dict(os.environ,
                             {'SNAP_REVISION': 'edge'}):
            self.assertEqual(hotsos.cli.get_version(), 'edge')

    def test_get_version(self):
        self.assertEqual(hotsos.cli.get_version(), 'development')

    def test_get_repo_info(self):
        with tempfile.TemporaryDirectory() as workdir:
            with open(os.path.join(workdir, 'repo-info'), 'w',
                      encoding='utf-8') as fd:
                fd.write('some version\n')
            with mock.patch.dict(os.environ,
                                 {'REPO_INFO_PATH': f'{workdir}/repo-info'}):
                repo_info = hotsos.cli.get_repo_info()
        self.assertEqual(repo_info, 'some version')

    def test_fix_data_root(self):
        self.assertEqual(hotsos.cli.fix_data_root(None), '/')
        self.assertEqual(hotsos.cli.fix_data_root('/'), '/')
        self.assertEqual(hotsos.cli.fix_data_root('some/path'), 'some/path/')

    def test_get_analysis_target(self):
        self.assertEqual(hotsos.cli.get_analysis_target('/'), 'localhost')
        self.assertEqual(hotsos.cli.get_analysis_target('some/path/'),
                         'sosreport some/path/')

    def test_get_prefix(self):
        self.assertEqual(hotsos.cli.get_prefix(data_root='/foo/bar'), 'bar')
        self.assertEqual(hotsos.cli.get_prefix(data_root='/'), 'compute4')
