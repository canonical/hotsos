from importlib.util import spec_from_loader, module_from_spec
from importlib.machinery import SourceFileLoader

import utils

# need this for non-standard import
specs = {}
for plugin in ["01juju", "02charms", "03units"]:
    loader = SourceFileLoader("juju_{}".format(plugin),
                              "plugins/juju/{}".format(plugin))
    specs[plugin] = spec_from_loader("juju_{}".format(plugin), loader)

juju_01juju = module_from_spec(specs["01juju"])
specs["01juju"].loader.exec_module(juju_01juju)

juju_02charms = module_from_spec(specs["02charms"])
specs["02charms"].loader.exec_module(juju_02charms)

juju_03units = module_from_spec(specs["03units"])
specs["03units"].loader.exec_module(juju_03units)


class TestJujuPlugin01juju(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    def test_get_machine_info(self):
        pass


class TestJujuPlugin02charms(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    def test_get_charm_versions(self):
        pass


class TestJujuPlugin03charms(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    def test_get_app_from_unit(self):
        pass

    def test_get_unit_version(self):
        pass

    def test_get_unit_info(self):
        pass
