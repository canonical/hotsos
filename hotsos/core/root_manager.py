import os
import shutil
import sys
import tarfile
import tempfile
from functools import cached_property

from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import CLIHelper


class DataRootManager(object):
    TYPE_HOST = 0
    TYPE_SOSREPORT = 1

    def __init__(self, path, sos_unpack_dir=None):
        self.path = path
        self.sos_unpack_dir = sos_unpack_dir

    @cached_property
    def tmpdir(self):
        if self.sos_unpack_dir is None:
            return tempfile.mkdtemp()

        return self.sos_unpack_dir

    def __enter__(self):
        return self

    def __exit__(self, *args):
        """
        Ensure that temporary data is deleted. Sosreports sometimes contain
        data that does not have permissions to be deleted so it is sometimes
        necessary to bump permissions and try again.
        """
        if self.sos_unpack_dir is not None:
            return

        try:
            shutil.rmtree(self.tmpdir)
        except Exception:
            os.system('chmod -R 777 {}'.format(self.tmpdir))
            shutil.rmtree(self.tmpdir)

    @cached_property
    def data_root(self):
        """
        Return data root path to be used by all plugins.

        If the user provided a path that is a sosreport archive (tar etc) then
        we unpack it to a temporary location that is deleted when we are
        finished.
        """
        path = self.path
        if not path:
            path = '/'

        if self._type(path) != self.TYPE_SOSREPORT:
            if path[-1] != '/':
                # Ensure trailing slash
                path += '/'

            return path

        if os.path.isdir(path):
            return path

        if tarfile.is_tarfile(path):
            with tarfile.open(path) as tar:
                target = os.path.join(self.tmpdir,
                                      os.path.basename(tar.firstmember.name))
                if not os.path.exists(target):
                    sys.stdout.write("INFO: extracting sosreport {} to {}\n".
                                     format(path, target))
                    tar.extractall(self.tmpdir)
                else:
                    sys.stdout.write("INFO: target {} already exists - "
                                     "skipping unpack\n".format(target))

            return target

        raise Exception("invalid data root '{}'".format(path))

    def _type(self, path):
        if path == '/':
            return self.TYPE_HOST

        return self.TYPE_SOSREPORT

    @property
    def type(self):
        return self._type(self.data_root)

    @property
    def name(self):
        """ A helpful name given to this data root. """
        if self.type == self.TYPE_HOST:
            return 'localhost'

        return 'sosreport {}'.format(self.data_root)

    @property
    def basename(self):
        path = self.data_root
        if path == '/':
            if HotSOSConfig.data_root != self.data_root:
                raise Exception("HotSOSConfig.data_root != {}".
                                format(self.data_root))

            return CLIHelper().hostname()

        return os.path.basename(path.rstrip('/'))
