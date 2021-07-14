import os

import mock

import utils

from common import cli_helpers
from plugins.kubernetes.pyparts import (
    general,
    network,
)


class TestKubernetesPluginPartGeneral(utils.BaseTestCase):

    def setUp(self):
        self.snaps_list = cli_helpers.get_snap_list_all()
        super().setUp()

    def test_get_service_info(self):
        expected = ['calico-node (3)',
                    'containerd (17)',
                    'containerd-shim (16)',
                    'flanneld (1)',
                    'kube-proxy (1)',
                    'kubelet (2)']
        inst = general.KubernetesServiceChecks()
        inst()
        self.assertEqual(inst.output['services'], expected)

    def test_get_snap_info_from_line(self):
        result = ['conjure-up 2.6.14-20200716.2107',
                  'core 16-2.48.2',
                  'core18 20201210',
                  'docker 19.03.11',
                  'go 1.15.6',
                  'helm 3.5.0',
                  'kubectl 1.20.2',
                  'vault 1.5.4']
        inst = general.get_kubernetes_package_checker()
        inst()
        self.assertEqual(inst.output['snaps'], result)

    @mock.patch.object(general.checks.cli_helpers, "get_snap_list_all")
    def test_get_snap_info_from_line_no_k8s(self, mock_get_snap_list_all):
        filterered_snaps = []
        for line in self.snaps_list:
            found = False
            for snap in general.SNAPS_K8S:
                obj = general.KubernetesPackageChecks([])
                if obj._get_snap_info_from_line(line, snap):
                    found = True
                    break

            if not found:
                filterered_snaps.append(line)

        mock_get_snap_list_all.return_value = filterered_snaps
        inst = general.get_kubernetes_package_checker()
        inst()
        self.assertEqual(inst.output, None)


class TestKubernetesPluginPartNetwork(utils.BaseTestCase):

    @mock.patch.object(network.cli_helpers, "get_ip_addr")
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
        inst = network.KubernetesNetworkChecks()
        inst()
        self.assertEqual(inst.output, expected)
