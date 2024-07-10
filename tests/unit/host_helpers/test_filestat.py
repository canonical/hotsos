import os

from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import filestat as host_file

from .. import utils


class TestFileStatHelper(utils.BaseTestCase):

    @utils.create_data_root({'foo': 'bar'})
    def test_filestat_factory(self):
        fpath = os.path.join(HotSOSConfig.data_root, 'foo')
        fileobj = host_file.FileFactory().foo
        self.assertEqual(fileobj.mtime, os.path.getmtime(fpath))

        fileobj = host_file.FileFactory().noexist
        self.assertEqual(fileobj.mtime, 0)
