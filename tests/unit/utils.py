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
    Filter hotsos.core.ycheck.YDefsLoader._is_def to only match a file with the
    given name. This permits a unit test to only run the ydef checks that are
    under test.

    Note that in order for directory globals to run def_filename must be a
    relative path that includes the parent directory name e.g. foo/bar.yaml
    where bar contains the checks and there is also a file called foo/foo.yaml
    that contains directory globals.
    """
    def inner(_inst, abs_path):
        # filename may optionally have a parent dir which allows us to permit
        # directory globals to be run.
        parent_dir = os.path.dirname(def_filename)
        """ Ensure we only load/run the yaml def with the given name. """
        if parent_dir:
            # allow directory global to run
            base_dir = os.path.basename(os.path.dirname(abs_path))
            if base_dir != parent_dir:
                return False

            if os.path.basename(abs_path) == "{}.yaml".format(parent_dir):
                return True

        if abs_path.endswith(def_filename):
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
        self.global_tmp_dir = tempfile.mkdtemp()
        self.plugin_tmp_dir = tempfile.mkdtemp(dir=self.global_tmp_dir)
        # Always reset env globals
        # If a test relies on loading info from defs yaml this needs to be set
        # to actual plugin name.
        setup_config(DATA_ROOT=os.path.join(TESTS_DIR, DEFAULT_FAKE_ROOT),
                     PLUGIN_NAME="testplugin",
                     PLUGIN_YAML_DEFS=os.path.join(TESTS_DIR, "defs"),
                     PART_NAME="01part",
                     GLOBAL_TMP_DIR=self.global_tmp_dir,
                     PLUGIN_TMP_DIR=self.plugin_tmp_dir,
                     USE_ALL_LOGS=True)
        setup_logging(debug_mode=True)

    def tearDown(self):
        if os.path.isdir(self.plugin_tmp_dir):
            shutil.rmtree(self.plugin_tmp_dir)
