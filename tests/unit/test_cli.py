import os
import sys
import tempfile
from unittest import mock

import distro
import hotsos.cli

from . import utils


class TestCLI(utils.BaseTestCase):
    """ Unit tests for HotSOS cli. """

    def test_get_hotsos_root(self):
        with mock.patch.object(sys, 'argv', ['/usr/bin/hotsos', '1', '2']):
            self.assertEqual(hotsos.cli.get_hotsos_root(), '/usr/bin')

    def test_get_version_exists(self):
        with mock.patch.dict(os.environ,
                             {'SNAP_REVISION': 'edge'}):
            self.assertEqual(hotsos.cli.get_version(), 'edge')

    def test_get_version(self):
        self.assertEqual(hotsos.cli.get_version(), 'development')

    def test_is_not_snap(self):
        self.assertFalse(hotsos.cli.is_snap())

    def test_is_snap(self):
        with mock.patch.dict(os.environ, {'SNAP_NAME': 'hotsos'}):
            self.assertTrue(hotsos.cli.is_snap())

    def test_get_os_id(self):
        with mock.patch.object(distro, 'id', return_value='ubuntu-test'):
            self.assertEqual(hotsos.cli.get_os_id(), 'ubuntu-test')

    def test_get_os_version(self):
        with mock.patch.object(distro, 'version', return_value='22.04'):
            self.assertEqual(hotsos.cli.get_os_version(), 22.04)

    @staticmethod
    def test_is_os_version_supported_in_snap():
        with mock.patch.object(sys, 'exit') as mock_exit:
            with mock.patch.dict(os.environ, {'SNAP_NAME': 'hotsos'}):
                with mock.patch.object(distro, 'id',
                                       return_value='ubuntu-test'):
                    hotsos.cli.exit_if_os_version_not_supported_in_snap()
                with mock.patch.object(distro, 'id',
                                       return_value='ubuntu'):
                    with mock.patch.object(distro, 'version',
                                           return_value='20.04'):
                        hotsos.cli.exit_if_os_version_not_supported_in_snap()
                    with mock.patch.object(distro, 'version',
                                           return_value='18.04'):
                        hotsos.cli.exit_if_os_version_not_supported_in_snap()
            mock_exit.assert_has_calls([mock.call(1), mock.call(2)])

    def test_get_templates_path_pypi(self):
        with tempfile.TemporaryDirectory() as workdir:
            d_templates_path = os.path.join(workdir, 'templates')
            os.makedirs(d_templates_path)
            with mock.patch('importlib.resources.path') as path:
                path.return_value.__enter__.return_value = d_templates_path
                templates_path = hotsos.cli.get_templates_path()

            self.assertEqual(templates_path, d_templates_path)

    def test_get_defs_path_pypi(self):
        with tempfile.TemporaryDirectory() as workdir:
            d_defs_path = os.path.join(workdir, 'defs')
            os.makedirs(d_defs_path)
            with mock.patch('importlib.resources.path') as path:
                path.return_value.__enter__.return_value = d_defs_path
                defs_path = hotsos.cli.get_defs_path()

            self.assertEqual(defs_path, d_defs_path)

    def test_get_repo_info_snap(self):
        with tempfile.TemporaryDirectory() as workdir:
            f_repo_info = os.path.join(workdir, 'repo-info')
            with open(f_repo_info, 'w', encoding='utf-8') as fd:
                fd.write('some version\n')

            with mock.patch.dict(os.environ, {'REPO_INFO_PATH': f_repo_info}):
                repo_info = hotsos.cli.get_repo_info()

        self.assertEqual(repo_info, 'some version')

    def test_get_repo_info_pypi(self):
        with tempfile.TemporaryDirectory() as workdir:
            f_repo_info = os.path.join(workdir, 'repo-info')
            with open(f_repo_info, 'w', encoding='utf-8') as fd:
                fd.write('some version\n')

            with mock.patch('importlib.resources.path') as path:
                path.return_value.__enter__.return_value = f_repo_info
                repo_info = hotsos.cli.get_repo_info()

        self.assertEqual(repo_info, 'some version')
