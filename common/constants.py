import os


# HOTSOS GLOBALS
VERBOSITY_LEVEL = int(os.environ.get('VERBOSITY_LEVEL', 0))
DATA_ROOT = os.environ.get('DATA_ROOT', '/')
MASTER_YAML_OUT = os.environ.get('MASTER_YAML_OUT')