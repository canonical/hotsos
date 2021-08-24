import os

import mock
import shutil
import tempfile

import utils

from common import checks, constants, cli_helpers
from plugins.kubernetes.pyparts import (
    general,
    network,
)


class TestKubernetesPluginPartGeneral(utils.BaseTestCase):

    def setUp(self):
        self.snaps_list = cli_helpers.CLIHelper().snap_list_all()
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
        inst = general.KubernetesPackageChecks()
        inst()
        self.assertEqual(inst.output['snaps'], result)

    @mock.patch.object(checks, 'CLIHelper')
    def test_get_snap_info_from_line_no_k8s(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        filterered_snaps = []
        for line in self.snaps_list:
            found = False
            for snap in general.SNAPS_K8S:
                obj = general.KubernetesPackageChecks()
                if obj._get_snap_info_from_line(line, snap):
                    found = True
                    break

            if not found:
                filterered_snaps.append(line)

        mock_helper.return_value.snap_list_all.return_value = filterered_snaps
        inst = general.KubernetesPackageChecks()
        inst()
        self.assertEqual(inst.output, None)


class TestKubernetesPluginPartNetwork(utils.BaseTestCase):

    def test_get_network_info(self):
        with tempfile.TemporaryDirectory() as dtmp:
            dst = os.path.join(dtmp, "sos_commands/networking")
            os.makedirs(dst)
            dst = os.path.join(dst, "ip_-d_address")
            src = os.path.join(constants.DATA_ROOT,
                               "sos_commands/networking/ip_-d_address.k8s")
            shutil.copy(src, dst)
            os.environ['DATA_ROOT'] = dtmp
            expected = {'flannel':
                        {'flannel.1': {'addr': '58.49.23.0',
                                       'vxlan': {'dev': 'enp6s0f0.1604',
                                                 'id': '1',
                                                 'local_ip': '10.78.2.176'}}}}
            inst = network.KubernetesNetworkChecks()
            inst()
            self.assertEqual(inst.output, expected)
