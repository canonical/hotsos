import os
import mock

from importlib.util import spec_from_loader, module_from_spec
from importlib.machinery import SourceFileLoader

import utils

os.environ["VERBOSITY_LEVEL"] = "1000"

# need this for non-standard import
specs = {}
for plugin in ["01general", "02network"]:
    loader = SourceFileLoader("k8s_{}".format(plugin),
                              "plugins/kubernetes/{}".format(plugin))
    specs[plugin] = spec_from_loader("k8s_{}".format(plugin), loader)

k8s_01general = module_from_spec(specs["01general"])
specs["01general"].loader.exec_module(k8s_01general)

k8s_02network = module_from_spec(specs["02network"])
specs["02network"].loader.exec_module(k8s_02network)


PS = """
"""  # noqa


def fake_ps():
    return [line + '\n' for line in PS.split('\n')]


class TestKubernetesPlugin01general(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(k8s_01general, "KUBERNETES_INFO", {})
    @mock.patch.object(k8s_01general.helpers, 'get_ps', fake_ps)
    def test_get_service_info(self):
        result = {}
        k8s_01general.get_service_info()
        self.assertEqual(k8s_01general.KUBERNETES_INFO, result)


class TestKubernetesPlugin02network(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()
