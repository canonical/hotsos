#!/usr/bin/python3
import logging

from core import constants

logging.disable(level=logging.CRITICAL)
log = logging.getLogger(constants.PLUGIN_NAME)


def setup_logging(debug_mode=False):
    format = ("%(asctime)s.%(msecs)03d %(process)d %(levelname)s %(name)s [-] "
              "%(message)s")
    logging.basicConfig(format=format)
    if debug_mode:
        logging.disable(logging.NOTSET)
        log.setLevel(logging.DEBUG)
