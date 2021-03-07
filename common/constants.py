import os

from common import helpers

# HOTSOS GLOBALS
VERBOSITY_LEVEL = int(os.environ.get('VERBOSITY_LEVEL', 0))
DATA_ROOT = os.environ.get('DATA_ROOT', '/')
MASTER_YAML_OUT = os.environ.get('MASTER_YAML_OUT')
USE_ALL_LOGS = os.environ.get('USE_ALL_LOGS', "False")
if helpers.bool_str(USE_ALL_LOGS):
    USE_ALL_LOGS = True
else:
    USE_ALL_LOGS = False
