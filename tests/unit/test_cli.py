import contextlib
import io
import os
import sys
import tempfile
from unittest import mock

import distro
import hotsos.cli
from hotsos.core.config import HotSOSConfig

from . import utils


class TestCLI(utils.BaseTestCase):
    """ Unit tests for HotSOS cli. """

    def _run_cli(self, args, euid, exit_code=0):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with mock.patch.object(sys, 'argv', ['hotsos'] + args), \
                mock.patch('hotsos.cli.os.geteuid', return_value=euid), \
                mock.patch('hotsos.cli.init_config') as init_config, \
                mock.patch('hotsos.cli.run_client') as run_client, \
                contextlib.redirect_stdout(stdout), \
                contextlib.redirect_stderr(stderr):
            builder = run_client.return_value.get_builder.return_value
            builder.to.return_value = ''
            with self.assertRaises(SystemExit) as exc:
                hotsos.cli.main()

            self.assertEqual(exc.exception.code, exit_code)

        return stdout.getvalue(), stderr.getvalue(), init_config, run_client

    def test_live_host_without_root_warns(self):
        """Warn but proceed with non-root live-host analysis."""
        for args in ([], ['/'], ['/.'], ['--quiet'], ['--force']):
            with self.subTest(args=args):
                with mock.patch('hotsos.cli.is_snap', return_value=False):
                    _, stderr, init_config, run_client = self._run_cli(
                        args, euid=1000)
                self.assertIn('WARNING', stderr)
                self.assertIn('should be run as root', stderr)
                self.assertIn('sudo', stderr)
                init_config.assert_called_once()
                run_client.assert_called_once()

    def test_live_host_as_root(self):
        """Allow live-host analysis with effective root privileges."""
        with mock.patch('hotsos.cli.is_snap', return_value=False):
            _, stderr, init_config, run_client = self._run_cli(
                ['--quiet'], euid=0)
        self.assertEqual(stderr, '')
        init_config.assert_called_once()
        run_client.assert_called_once()

    def test_sosreport_without_root(self):
        """Allow sosreport analysis without root privileges."""
        _, stderr, init_config, run_client = self._run_cli(
            ['--quiet', HotSOSConfig.data_root], euid=1000)
        self.assertEqual(stderr, '')
        init_config.assert_called_once()
        run_client.assert_called_once()

    def test_informational_options_without_root(self):
        """Allow informational options without root privileges."""
        for option in ('--help', '--version', '--list-plugins'):
            with self.subTest(option=option):
                with mock.patch('hotsos.cli.is_snap', return_value=False):
                    stdout, stderr, _, run_client = self._run_cli(
                        [option], euid=1000)
                self.assertTrue(stdout)
                self.assertEqual(stderr, '')
                run_client.assert_not_called()

    def test_get_hotsos_root(self):
        """Test hotsos root path extraction from sys.argv."""
        with mock.patch.object(sys, 'argv', ['/usr/bin/hotsos', '1', '2']):
            self.assertEqual(hotsos.cli.get_hotsos_root(), '/usr/bin')

    def test_get_version_exists(self):
        """Test version retrieval from SNAP_REVISION env var."""
        with mock.patch.dict(os.environ,
                             {'SNAP_REVISION': 'edge'}):
            self.assertEqual(hotsos.cli.get_version(), 'edge')

    def test_is_not_snap(self):
        """Test is_snap returns False without SNAP_NAME."""
        self.assertFalse(hotsos.cli.is_snap())

    def test_is_snap(self):
        """Test is_snap returns True with SNAP_NAME set."""
        with mock.patch.dict(os.environ, {'SNAP_NAME': 'hotsos'}):
            self.assertTrue(hotsos.cli.is_snap())

    def test_get_os_id(self):
        """Test OS id retrieval via distro module."""
        with mock.patch.object(distro, 'id', return_value='ubuntu-test'):
            self.assertEqual(hotsos.cli.get_os_id(), 'ubuntu-test')

    def test_get_os_version(self):
        """Test OS version retrieval via distro module."""
        with mock.patch.object(distro, 'version', return_value='22.04'):
            self.assertEqual(hotsos.cli.get_os_version(), 22.04)

    @staticmethod
    def test_is_os_version_supported_in_snap():
        """Test OS version check exits for unsupported snaps."""
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
        """Test templates path resolution for pypi install."""
        with tempfile.TemporaryDirectory() as workdir:
            d_templates_path = os.path.join(workdir, 'templates')
            os.makedirs(d_templates_path)
            with mock.patch('importlib.resources.path') as path:
                path.return_value.__enter__.return_value = d_templates_path
                templates_path = hotsos.cli.get_templates_path()

            self.assertEqual(templates_path, d_templates_path)

    def test_get_defs_path_pypi(self):
        """Test defs path resolution for pypi install."""
        with tempfile.TemporaryDirectory() as workdir:
            d_defs_path = os.path.join(workdir, 'defs')
            os.makedirs(d_defs_path)
            with mock.patch('importlib.resources.path') as path:
                path.return_value.__enter__.return_value = d_defs_path
                defs_path = hotsos.cli.get_defs_path()

            self.assertEqual(defs_path, d_defs_path)

    def test_get_repo_info_snap(self):
        """Test repo info retrieval from REPO_INFO_PATH."""
        with tempfile.TemporaryDirectory() as workdir:
            f_repo_info = os.path.join(workdir, 'repo-info')
            with open(f_repo_info, 'w', encoding='utf-8') as fd:
                fd.write('some version\n')

            with mock.patch.dict(os.environ, {'REPO_INFO_PATH': f_repo_info}):
                repo_info = hotsos.cli.get_repo_info()

        self.assertEqual(repo_info, 'some version')

    def test_get_repo_info_pypi(self):
        """Test repo info retrieval for pypi install."""
        with tempfile.TemporaryDirectory() as workdir:
            f_repo_info = os.path.join(workdir, 'repo-info')
            with open(f_repo_info, 'w', encoding='utf-8') as fd:
                fd.write('some version\n')

            with mock.patch('importlib.resources.path') as path:
                path.return_value.__enter__.return_value = f_repo_info
                repo_info = hotsos.cli.get_repo_info()

        self.assertEqual(repo_info, 'some version')
