#!/usr/bin/python3
import logging
import os
import tempfile
from functools import cached_property

from hotsos.core.config import HotSOSConfig

log = logging.getLogger('hotsos')


class LoggingManager(object):

    def __init__(self):
        self.delete_temp_file = True

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *args, **kwargs):
        self.stop()

        # Allow raise
        return False

    @property
    def _format(self):
        return ("%(asctime)s.%(msecs)03d %(process)d %(levelname)s %(name)s "
                "[-] %(message)s")

    @cached_property
    def _handler(self):
        if HotSOSConfig.debug_mode:
            return logging.StreamHandler()

        return logging.FileHandler(self.temp_log_path)

    @cached_property
    def temp_log_path(self):
        return tempfile.mktemp(suffix='hotsos.log')

    def setup_deps_loggers(self, level):
        # Set logging level for dependencies
        logging.getLogger('searchkit').setLevel(level=level)
        logging.getLogger('searchkit').addHandler(self._handler)
        # NOTE: dont set log level here as it is controlled using env var
        logging.getLogger('propertree').addHandler(self._handler)

    def start(self, level=logging.DEBUG):
        log.setLevel(level)
        if log.hasHandlers():
            return

        self._handler.setFormatter(logging.Formatter(self._format))
        log.addHandler(self._handler)
        self.setup_deps_loggers(level)

    def stop(self):
        if os.path.exists(self.temp_log_path) and self.delete_temp_file:
            log.debug("removing temporary log file %s", self.temp_log_path)
            os.remove(self.temp_log_path)
