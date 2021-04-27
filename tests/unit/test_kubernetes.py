import os

import mock

import utils

from common import helpers

# Need this for plugin imports
utils.add_sys_plugin_path("kubernetes")
from plugins.kubernetes import (  # noqa E402
    _01general,
    _02network,
)
from _01general import KubernetesServiceChecks  # noqa E402


class TestKubernetesPlugin01general(utils.BaseTestCase):

    def setUp(self):
        self.snaps_list = helpers.get_snap_list_all()
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(_01general, "KUBERNETES_INFO", {})
    def test_get_service_info(self):
        expected = ['calico-node (3)',
                    'containerd (17)',
                    'containerd-shim (16)',
                    'flanneld (1)',
                    'kube-proxy (1)',
                    'kubelet (2)']
        _01general.get_kubernetes_service_checker()()
        self.assertEqual(_01general.KUBERNETES_INFO['services'], expected)

    @mock.patch.object(_01general, "KUBERNETES_INFO", {})
    def test_get_snap_info_from_line(self):
        result = {'conjure-up': '2.6.14-20200716.2107',
                  'core': '16-2.48.2',
                  'core18': '20201210',
                  'docker': '19.03.11',
                  'go': '1.15.6',
                  'helm': '3.5.0',
                  'kubectl': '1.20.2',
                  'vault': '1.5.4'}
        _01general.get_kubernetes_service_checker()()
        self.assertEqual(_01general.KUBERNETES_INFO["snaps"], result)

    @mock.patch.object(_01general.helpers, "get_snap_list_all")
    @mock.patch.object(_01general, "KUBERNETES_INFO", {})
    def test_get_snap_info_from_line_no_k8s(self, mock_get_snap_list_all):
        filterered_snaps = []
        for line in self.snaps_list:
            found = False
            for snap in _01general.SNAPS_K8S:
                if KubernetesServiceChecks.get_snap_info_from_line(line, snap):
                    found = True
                    break

            if not found:
                filterered_snaps.append(line)

        mock_get_snap_list_all.return_value = filterered_snaps
        _01general.get_kubernetes_service_checker()()
        self.assertIsNone(_01general.KUBERNETES_INFO.get("snaps"))


class TestKubernetesPlugin02network(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(_02network.helpers, "get_ip_addr")
    @mock.patch.object(_02network, "NETWORK_INFO", {})
    def test_get_network_info(self, mock_get_ip_addr):

        def fake_get_ip_addr():
            path = os.path.join(os.environ["DATA_ROOT"],
                                "sos_commands/networking/ip_-d_address.k8s")
            with open(path) as fd:
                return fd.readlines()

        mock_get_ip_addr.side_effect = fake_get_ip_addr
        expected = {'flannel':
                    {'flannel.1': {'addr': '58.49.23.0/32',
                                   'vxlan': '10.78.2.176@enp6s0f0'}}}
        _02network.get_kubernetes_network_checks()()
        self.assertEqual(_02network.NETWORK_INFO, expected)
