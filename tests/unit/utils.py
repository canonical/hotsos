import os
import sys

import shutil
import tempfile
import unittest


sys.path += ['plugins']

# Must be set prior to other imports
TESTS_DIR = os.environ["TESTS_DIR"]
os.environ["DATA_ROOT"] = os.path.join(TESTS_DIR, "fake_data_root")
os.environ["USE_ALL_LOGS"] = "True"
os.environ["PLUGIN_NAME"] = "testplugin"
os.environ["PART_NAME"] = "01part"


def add_sys_plugin_path(plugin):
    sys.path += ['plugins/{}'.format(plugin)]


class BaseTestCase(unittest.TestCase):

    def setUp(self):
        self.plugin_tmp_dir = tempfile.mkdtemp()

    def tearDown(self):
        if os.path.isdir(self.plugin_tmp_dir):
            shutil.rmtree(self.plugin_tmp_dir)
