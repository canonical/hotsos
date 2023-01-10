import os

from hotsos.core.log import log
from hotsos.core.config import HotSOSConfig
from hotsos.core.factory import FactoryBase


class FileObj(object):

    def __init__(self, filename):
        self.filename = os.path.join(HotSOSConfig.data_root, filename)

    @property
    def mtime(self):
        if not os.path.exists(self.filename):
            log.debug("mtime %s - file not found", self.filename)
            return 0

        mt = os.path.getmtime(self.filename)
        log.debug("mtime %s=%s", self.filename, mt)
        return mt


class FileFactory(FactoryBase):
    """
    Factory to dynamically create FileObj objects using file path as input.

    FileObj objects are returned when a getattr() is done on this object using
    the path of the file.
    """

    def __getattr__(self, filename):
        return FileObj(filename)
