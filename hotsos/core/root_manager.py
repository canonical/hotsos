import os
import shutil
import sys
import tarfile
import tempfile
from functools import cached_property

from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import CLIHelper
from hotsos.core.log import log


class DataRootManager():
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
        except PermissionError:
            os.system(f'chmod -R 777 {self.tmpdir}')
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
                rootdir = tar.firstmember.name.partition('/')[0]
                target = os.path.join(self.tmpdir, rootdir)
                if not os.path.exists(target):
                    sys.stdout.write(f"INFO: extracting sosreport {path} to "
                                     "{target}\n")
                    try:
                        tar.extractall(self.tmpdir)
                    # We really do want to catch all here since we don't care
                    # why it failed but don't want to fail hard if it does.
                    except Exception:  # pylint: disable=W0718
                        log.exception("error occured while unpacking "
                                      "sosreport:")
                        # some members might fail to extract e.g. permission
                        # denied but we dont want that to cause the whole run
                        # to fail so we just log a message and ignore them.
                        tar.errorlevel = 0
                        sys.stdout.write("INFO: one or more members failed to "
                                         "extract - disabling error mode and "
                                         "continuing extraction (which will "
                                         "be incomplete as a result)\n")
                        tar.extractall(self.tmpdir)
                else:
                    sys.stdout.write(f"INFO: target {target} already exists - "
                                     "skipping unpack\n")

            return target

        raise Exception(f"invalid data root '{path}'")

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

        return f'sosreport {self.data_root}'

    @property
    def basename(self):
        path = self.data_root
        if path == '/':
            if HotSOSConfig.data_root != self.data_root:
                raise Exception(f"HotSOSConfig.data_root != {self.data_root}")

            return CLIHelper().hostname()

        return os.path.basename(path.rstrip('/'))
