#!/usr/bin/python3
import logging
import tempfile

from hotsos.core.config import HotSOSConfig

log = logging.getLogger()


def setup_logging():
    format = ("%(asctime)s.%(msecs)03d %(process)d %(levelname)s %(name)s [-] "
              "%(message)s")
    log.name = 'plugin.{}'.format(HotSOSConfig.plugin_name)
    if not HotSOSConfig.debug_mode:
        logging.basicConfig(format=format, level=logging.DEBUG,
                            filename=tempfile.mktemp(suffix='hotsos.log'))
    else:
        logging.basicConfig(format=format, level=logging.DEBUG)
