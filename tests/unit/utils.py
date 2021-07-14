import os

import shutil
import tempfile
import unittest


# Must be set prior to other imports
TESTS_DIR = os.environ["TESTS_DIR"]
os.environ["DATA_ROOT"] = os.path.join(TESTS_DIR, "fake_data_root")


class BaseTestCase(unittest.TestCase):

    def setUp(self):
        # Always reset env globals
        os.environ["DATA_ROOT"] = os.path.join(TESTS_DIR, "fake_data_root")
        os.environ["PLUGIN_NAME"] = "testplugin"
        os.environ["USE_ALL_LOGS"] = "True"
        os.environ["PART_NAME"] = "01part"
        os.environ["PLUGIN_YAML_DEFS"] = os.path.join(TESTS_DIR, "defs")
        self.plugin_tmp_dir = tempfile.mkdtemp()
        os.environ["PLUGIN_TMP_DIR"] = self.plugin_tmp_dir

    def tearDown(self):
        if os.path.isdir(self.plugin_tmp_dir):
            shutil.rmtree(self.plugin_tmp_dir)
