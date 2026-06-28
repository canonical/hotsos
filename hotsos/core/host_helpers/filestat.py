import os

from hotsos.core.config import HotSOSConfig
from hotsos.core.factory import FactoryBase
from hotsos.core.log import log


class FileObj():
    """ Helper to enable querying filesystem entries. """
    def __init__(self, filename):
        self.filename = os.path.join(HotSOSConfig.data_root, filename)

    @property
    def exists(self):
        """ Return True if the file exists on disk. """
        if os.path.exists(self.filename):
            return True

        return False

    @property
    def mtime(self):
        """ Return the file modification time, or 0 if missing. """
        if not self.exists:
            log.debug("mtime %s - file not found", self.filename)
            return 0

        mt = os.path.getmtime(self.filename)
        log.debug("mtime %s=%s", self.filename, mt)
        return mt

    @property
    def size(self):
        """ Return the file size in bytes, or -1 if missing. """
        if not os.path.exists(self.filename):
            log.debug("size %s - file not found", self.filename)
            return -1

        size = os.path.getsize(self.filename)
        log.debug("size %s=%d", self.filename, size)
        return size


class FileFactory(FactoryBase):
    """
    Factory to dynamically create FileObj objects using file path as input.

    FileObj objects are returned when a getattr() is done on this object using
    the path of the file.
    """

    def __getattr__(self, filename):
        return FileObj(filename)
