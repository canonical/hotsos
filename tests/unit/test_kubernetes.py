import mock

import utils

from common import helpers

from plugins.kubernetes import (
    _01general,
    _02network,
)


class TestKubernetesPlugin01general(utils.BaseTestCase):

    def setUp(self):
        self.snaps_list = helpers.get_snap_list_all()
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(_01general, "KUBERNETES_INFO", {})
    def test_get_service_info(self):
        expected = {'services': ['containerd (17)',
                                 'containerd-shim (16)',
                                 'flanneld (1)',
                                 'kube-proxy (1)',
                                 'kubelet (2)']}
        _01general.get_kubernetes_service_checker()()
        self.assertEqual(_01general.KUBERNETES_INFO, expected)

    @mock.patch.object(_01general, "KUBERNETES_INFO", {})
    def test_get_snap_info(self):
        result = {'snaps': {'conjure-up': '2.6.14-20200716.2107',
                            'core': '16-2.48.2',
                            'core18': '20201210',
                            'docker': '19.03.11',
                            'go': '1.15.6',
                            'helm': '3.5.0',
                            'kubectl': '1.20.2',
                            'vault': '1.5.4'}}
        _01general.get_snap_info()
        self.assertEqual(_01general.KUBERNETES_INFO, result)

    @mock.patch.object(_01general.helpers, "get_snap_list_all")
    @mock.patch.object(_01general, "KUBERNETES_INFO", {})
    def test_get_snap_info_no_k8s(self, mock_get_snap_list_all):
        filterered_snaps = []
        for line in self.snaps_list:
            found = False
            for snap in _01general.SNAPS_K8S:
                if _01general._get_snap_info(line, snap):
                    found = True
                    break

            if not found:
                filterered_snaps.append(line)

        mock_get_snap_list_all.return_value = filterered_snaps
        result = {}
        _01general.get_snap_info()
        self.assertEqual(_01general.KUBERNETES_INFO, result)


class TestKubernetesPlugin02network(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(_02network, "NETWORK_INFO", {})
    def test_get_network_info(self):
        expected = {}
        _02network.get_network_info()
        self.assertEqual(_02network.NETWORK_INFO, expected)
