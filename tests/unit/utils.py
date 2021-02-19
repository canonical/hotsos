import os
import unittest

# Must be set prior to other imports
TESTS_DIR = os.environ["TESTS_DIR"]
os.environ["DATA_ROOT"] = os.path.join(TESTS_DIR, "fake_data_root")
os.environ["VERBOSITY_LEVEL"] = "1000"


class BaseTestCase(unittest.TestCase):

    def setUp(self):
        pass

    def tearDown(self):
        pass
