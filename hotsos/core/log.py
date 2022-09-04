#!/usr/bin/python3
import logging
import tempfile

from hotsos.core.config import HotSOSConfig

log = logging.getLogger()


def setup_logging(debug_mode=False):
    format = ("%(asctime)s.%(msecs)03d %(process)d %(levelname)s %(name)s [-] "
              "%(message)s")
    log.name = HotSOSConfig.PLUGIN_NAME
    if not debug_mode:
        logging.basicConfig(format=format, level=logging.DEBUG,
                            filename=tempfile.mktemp(suffix='hotsos.log'))
    else:
        logging.basicConfig(format=format, level=logging.DEBUG)
