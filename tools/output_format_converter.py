#!/usr/bin/env python3

import sys
import json
import yaml

from core import constants
from core.log import log

if __name__ == '__main__':
    log.debug('Converting master yaml file')
    if constants.OUTPUT_FORMAT == 'yaml':
        sys.exit(0)
    with open(constants.MASTER_YAML_OUT, encoding='utf-8') as fd:
        master_yaml = yaml.safe_load(fd)
    if constants.OUTPUT_FORMAT == 'json':
        with open(constants.MASTER_YAML_OUT, 'w', encoding='utf-8') as fd:
            fd.write(json.dumps(master_yaml, indent=2, sort_keys=True))
