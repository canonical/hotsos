import os

import shutil
import tempfile
import unittest


# Must be set prior to other imports
TESTS_DIR = os.environ["TESTS_DIR"]
DEFAULT_FAKE_ROOT = 'fake_data_root/openstack'
os.environ["DATA_ROOT"] = os.path.join(TESTS_DIR, DEFAULT_FAKE_ROOT)


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
        os.environ["DEBUG_MODE"] = "True"
        # ensure locale consistency wherever tests are run
        os.environ["LANG"] = 'C.UTF-8'
        # Always reset env globals
        os.environ["DATA_ROOT"] = os.path.join(TESTS_DIR, DEFAULT_FAKE_ROOT)
        # If a test relies on loading info from defs yaml this needs to be set
        # to actual plugin name.
        os.environ["PLUGIN_NAME"] = "testplugin"
        os.environ["USE_ALL_LOGS"] = "True"
        os.environ["PART_NAME"] = "01part"
        os.environ["PLUGIN_YAML_DEFS"] = os.path.join(TESTS_DIR, "defs")
        self.plugin_tmp_dir = tempfile.mkdtemp()
        os.environ["PLUGIN_TMP_DIR"] = self.plugin_tmp_dir

    def tearDown(self):
        if os.path.isdir(self.plugin_tmp_dir):
            shutil.rmtree(self.plugin_tmp_dir)
