#!/usr/bin/python3
import logging
import tempfile

from hotsos.core.config import HotSOSConfig

log = logging.getLogger('hotsos')


def setup_logging(level=logging.DEBUG):
    fmt = ("%(asctime)s.%(msecs)03d %(process)d %(levelname)s %(name)s [-] "
           "%(message)s")
    log.name = 'hotsos.plugin.{}'.format(HotSOSConfig.plugin_name)
    if not HotSOSConfig.debug_mode:
        logging.basicConfig(format=fmt, level=level,
                            filename=tempfile.mktemp(suffix='hotsos.log'))
    else:
        logging.basicConfig(format=fmt, level=level)

    # Set logging level for dependencies
    logging.getLogger('searchkit').setLevel(level=level)
