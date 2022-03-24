import os

import shutil
import tempfile
import unittest

from hotsos.core.config import setup_config
from hotsos.core.log import setup_logging


# Must be set prior to other imports
TESTS_DIR = os.environ["TESTS_DIR"]
DEFAULT_FAKE_ROOT = 'fake_data_root/openstack'
setup_config(DATA_ROOT=os.path.join(TESTS_DIR, DEFAULT_FAKE_ROOT))


def is_def_filter(def_filename):
    """
    This is used to filter core.ycheck.YDefsLoader._is_def to only match the
    yaml def with the given filename so that e.g. a unit will only run that set
    of checks so as to make it easier to know that the result is from a
    specific check(s).

    NOTE: this will omit directory-global defs e.g. for a dir foo containing
    foo.yaml and mycheck.yaml, globals in foo.yaml will not be applied (unless
    of course name=="foo.yaml")
    """
    def inner(_inst, path):
        """ Ensure we only load/run the yaml def with the given name. """
        if os.path.basename(path) == def_filename:
            return True

        return False

    return inner


class BaseTestCase(unittest.TestCase):

    def part_output_to_actual(self, output):
        actual = {}
        for key, entry in output.items():
            actual[key] = entry.data

        return actual

    def setUp(self):
        self.maxDiff = None
        # ensure locale consistency wherever tests are run
        os.environ["LANG"] = 'C.UTF-8'
        self.plugin_tmp_dir = tempfile.mkdtemp()
        # Always reset env globals
        # If a test relies on loading info from defs yaml this needs to be set
        # to actual plugin name.
        setup_config(DATA_ROOT=os.path.join(TESTS_DIR, DEFAULT_FAKE_ROOT),
                     PLUGIN_NAME="testplugin",
                     PLUGIN_YAML_DEFS=os.path.join(TESTS_DIR, "defs"),
                     PART_NAME="01part",
                     PLUGIN_TMP_DIR=self.plugin_tmp_dir,
                     USE_ALL_LOGS=True)
        setup_logging(debug_mode=True)

    def tearDown(self):
        if os.path.isdir(self.plugin_tmp_dir):
            shutil.rmtree(self.plugin_tmp_dir)
