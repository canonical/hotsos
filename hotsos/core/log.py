#!/usr/bin/python3
import logging

from hotsos.core.config import HotSOSConfig

logging.disable(level=logging.CRITICAL)
log = logging.getLogger()


def setup_logging(debug_mode=False):
    format = ("%(asctime)s.%(msecs)03d %(process)d %(levelname)s %(name)s [-] "
              "%(message)s")
    log.name = HotSOSConfig.PLUGIN_NAME
    logging.basicConfig(format=format)
    if debug_mode:
        logging.disable(logging.NOTSET)
        log.setLevel(logging.DEBUG)
