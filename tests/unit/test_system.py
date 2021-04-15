import os
import mock

from importlib.util import spec_from_loader, module_from_spec
from importlib.machinery import SourceFileLoader

import utils

os.environ["VERBOSITY_LEVEL"] = "1000"

# need this for non-standard import
specs = {}
for plugin in ["01system"]:
    loader = SourceFileLoader("sys_{}".format(plugin),
                              "plugins/system/{}".format(plugin))
    specs[plugin] = spec_from_loader("sys_{}".format(plugin), loader)

sys_01system = module_from_spec(specs["01system"])
specs["01system"].loader.exec_module(sys_01system)


class TestSystemPlugin01system(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(sys_01system, "SYSTEM_INFO", {})
    def test_get_service_info(self):
        pass
