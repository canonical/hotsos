import os
import shutil
import tarfile
import tempfile
from unittest import mock

import hotsos.core.root_manager
from hotsos.core.config import HotSOSConfig

from . import utils


class TestRootManager(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        self.tmpdir = tempfile.mktemp()
        self.sospath_unpacked = os.path.join(self.tmpdir, 'mysos')
        self.sospath_packed = self.sospath_unpacked + '.xz'
        self.create_sosreport(self.sospath_unpacked)

    def tearDown(self):
        shutil.rmtree(self.tmpdir)
        super().tearDown()

    def create_sosreport(self, sospath):
        os.makedirs(os.path.join(sospath, 'sos_commands'))
        tarroot = os.path.basename(sospath)
        with tarfile.open(sospath + '.xz', 'w:xz') as tar:
            tar.add(name=sospath, arcname=tarroot)

    def test_sos_data_root(self):
        path = self.sospath_packed
        with hotsos.core.root_manager.DataRootManager(path) as drm:
            basename = os.path.basename(self.sospath_unpacked)
            self.assertEqual(drm.name, 'sosreport {}'.
                             format(os.path.join(drm.tmpdir, basename)))
            self.assertEqual(drm.basename, basename)

    def test_fix_data_root(self):
        drm = hotsos.core.root_manager.DataRootManager(None)
        self.assertEqual(drm.data_root, '/')
        drm = hotsos.core.root_manager.DataRootManager('/')
        self.assertEqual(drm.data_root, '/')
        drm = hotsos.core.root_manager.DataRootManager(self.sospath_unpacked)
        self.assertEqual(drm.data_root, self.sospath_unpacked)
        drm = hotsos.core.root_manager.DataRootManager(self.sospath_packed)
        self.assertEqual(drm.data_root,
                         os.path.join(drm.tmpdir,
                                      os.path.basename(self.sospath_unpacked)))

    @mock.patch('hotsos.core.root_manager.tarfile.is_tarfile',
                lambda *args: False)
    def test_name(self):
        drm = hotsos.core.root_manager.DataRootManager('/')
        self.assertEqual(drm.name, 'localhost')
        path = os.path.join(self.tmpdir, 'foo/bar')
        os.makedirs(path)
        drm = hotsos.core.root_manager.DataRootManager(path)
        self.assertEqual(drm.name, 'sosreport {}'.format(path))

    @mock.patch('hotsos.core.root_manager.CLIHelper')
    @mock.patch('hotsos.core.root_manager.tarfile.is_tarfile',
                lambda *args: False)
    def test_basename(self, mock_cli):
        mock_cli.return_value.hostname.return_value = 'compute4'
        HotSOSConfig.data_root = '/'
        drm = hotsos.core.root_manager.DataRootManager('/')
        self.assertEqual(drm.basename, 'compute4')
        path = os.path.join(self.tmpdir, 'foo/bar')
        with self.assertRaises(Exception):
            drm = hotsos.core.root_manager.DataRootManager(path)
            self.assertEqual(drm.basename, 'bar')

        os.makedirs(path)
        drm = hotsos.core.root_manager.DataRootManager(path)
        self.assertEqual(drm.basename, 'bar')
