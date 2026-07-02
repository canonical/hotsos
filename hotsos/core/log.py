#!/usr/bin/python3
import logging
import os
import tempfile
from functools import cached_property

from hotsos.core.config import HotSOSConfig

log = logging.getLogger('hotsos')


class LoggingManager():
    """
    Context manager to manage logging config during the execution of HotSOS.
    """
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
        return ("%(asctime)s %(process)d %(levelname)s %(name)s "
                "[-] %(message)s")

    @cached_property
    def _handler(self):
        if HotSOSConfig.debug_mode:
            return logging.StreamHandler()

        return logging.FileHandler(self.temp_log_path)

    @cached_property
    def temp_log_path(self):
        """ Return path to a temporary log file. """
        return tempfile.mktemp(suffix='hotsos.log')

    def setup_deps_loggers(self):
        """ Configure log handlers and levels for dependencies. """
        # Set logging level for dependencies
        for dep in ['searchkit', 'propertree']:
            logger = logging.getLogger(dep)
            while logger.hasHandlers():
                logger.removeHandler(logger.handlers[0])

            logger.addHandler(self._handler)
            level = HotSOSConfig.debug_log_levels.get(dep, 'WARNING')
            logger.setLevel(level=level)

    def start(self, level=logging.DEBUG):
        """ Initialise the root logger with handler and format. """
        log.setLevel(level)
        if log.hasHandlers():
            return

        self._handler.setFormatter(logging.Formatter(self._format))
        log.addHandler(self._handler)
        self.setup_deps_loggers()

    def stop(self):
        """ Remove the temporary log file if configured. """
        if os.path.exists(self.temp_log_path) and self.delete_temp_file:
            log.debug("removing temporary log file %s", self.temp_log_path)
            os.remove(self.temp_log_path)
