#!/usr/bin/python3
import logging

from core import constants


format = ("%(asctime)s.%(msecs)03d %(process)d %(levelname)s %(name)s [-] "
          "%(message)s")
logging.basicConfig(format=format)
log = logging.getLogger(constants.PLUGIN_NAME)
if constants.DEBUG_MODE:
    log.setLevel(logging.DEBUG)
