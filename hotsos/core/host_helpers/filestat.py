import os

from hotsos.core.config import HotSOSConfig
from hotsos.core.factory import FactoryBase
from hotsos.core.log import log


class FileObj():

    def __init__(self, filename):
        self.filename = os.path.join(HotSOSConfig.data_root, filename)

    @property
    def exists(self):
        if os.path.exists(self.filename):
            return True

        return False

    @property
    def mtime(self):
        if not self.exists:
            log.debug("mtime %s - file not found", self.filename)
            return 0

        mt = os.path.getmtime(self.filename)
        log.debug("mtime %s=%s", self.filename, mt)
        return mt

    @property
    def size(self):
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
