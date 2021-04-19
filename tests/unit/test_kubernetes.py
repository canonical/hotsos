import os
import mock

from importlib.util import spec_from_loader, module_from_spec
from importlib.machinery import SourceFileLoader

import utils

from common import helpers

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


class TestKubernetesPlugin01general(utils.BaseTestCase):

    def setUp(self):
        self.snaps_list = helpers.get_snap_list_all()
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(k8s_01general, "KUBERNETES_INFO", {})
    def test_get_service_info(self):
        expected = {'services': ['containerd (17)',
                                 'containerd-shim (16)',
                                 'flanneld (1)',
                                 'kube-proxy (1)',
                                 'kubelet (2)']}
        k8s_01general.get_kubernetes_service_checker()()
        self.assertEqual(k8s_01general.KUBERNETES_INFO, expected)

    @mock.patch.object(k8s_01general, "KUBERNETES_INFO", {})
    def test_get_snap_info(self):
        result = {'snaps': {'conjure-up': '2.6.14-20200716.2107',
                            'core': '16-2.48.2',
                            'core18': '20201210',
                            'docker': '19.03.11',
                            'go': '1.15.6',
                            'helm': '3.5.0',
                            'kubectl': '1.20.2',
                            'vault': '1.5.4'}}
        k8s_01general.get_snap_info()
        self.assertEqual(k8s_01general.KUBERNETES_INFO, result)

    @mock.patch.object(k8s_01general.helpers, "get_snap_list_all")
    @mock.patch.object(k8s_01general, "KUBERNETES_INFO", {})
    def test_get_snap_info_no_k8s(self, mock_get_snap_list_all):
        filterered_snaps = []
        for line in self.snaps_list:
            found = False
            for snap in k8s_01general.SNAPS_K8S:
                if k8s_01general._get_snap_info(line, snap):
                    found = True
                    break

            if not found:
                filterered_snaps.append(line)

        mock_get_snap_list_all.return_value = filterered_snaps
        result = {}
        k8s_01general.get_snap_info()
        self.assertEqual(k8s_01general.KUBERNETES_INFO, result)


class TestKubernetesPlugin02network(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()
