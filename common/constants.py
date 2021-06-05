import os

from common import cli_helpers

# HOTSOS GLOBALS
DATA_ROOT = os.environ.get('DATA_ROOT', '/')
MASTER_YAML_OUT = os.environ.get('MASTER_YAML_OUT')
PLUGIN_TMP_DIR = os.environ.get('PLUGIN_TMP_DIR')
PLUGIN_NAME = os.environ.get('PLUGIN_NAME')
PART_NAME = os.environ.get('PART_NAME')
PLUGIN_YAML_DEFS = os.environ.get('PLUGIN_YAML_DEFS')
USE_ALL_LOGS = os.environ.get('USE_ALL_LOGS', "False")
if cli_helpers.bool_str(USE_ALL_LOGS):
    USE_ALL_LOGS = True
else:
    USE_ALL_LOGS = False

MAX_PARALLEL_TASKS = int(os.environ.get('MAX_PARALLEL_TASKS', 8))
MAX_LOGROTATE_DEPTH = int(os.environ.get('MAX_LOGROTATE_DEPTH', 7))
