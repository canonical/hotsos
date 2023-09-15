#!/usr/bin/python3
import logging
import tempfile

from hotsos.core.config import HotSOSConfig

log = logging.getLogger('hotsos')


def setup_logging(level=logging.DEBUG):
    fmt = ("%(asctime)s.%(msecs)03d %(process)d %(levelname)s %(name)s [-] "
           "%(message)s")
    log.name = 'hotsos.plugin.{}'.format(HotSOSConfig.plugin_name)
    log.setLevel(level)

    if not log.hasHandlers():
        if HotSOSConfig.debug_mode:
            handler = logging.StreamHandler()
        else:
            handler = logging.FileHandler(tempfile.mktemp(suffix='hotsos.log'))

        handler.setFormatter(logging.Formatter(fmt))
        log.addHandler(handler)

        # Set logging level for dependencies
        logging.getLogger('searchkit').setLevel(level=level)
        logging.getLogger('searchkit').addHandler(handler)
        # NOTE: dont set log level here as it is controlled using env var
        logging.getLogger('propertree').addHandler(handler)
