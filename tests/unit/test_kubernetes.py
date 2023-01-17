import os

from unittest import mock

from . import utils

from hotsos.core.config import HotSOSConfig
from hotsos.core import host_helpers
from hotsos.plugin_extensions.kubernetes import summary

SNAP_LIST_ALL_NO_K8S = """
Name                     Version    Rev    Tracking       Publisher   Notes
lxd                      4.0.8      21835  4.0/stable/…   canonical*  -
snapd                    2.54.2     14549  latest/stable  canonical*  snapd
"""


class KubernetesTestsBase(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        HotSOSConfig.plugin_name = 'kubernetes'
        HotSOSConfig.data_root = os.path.join(utils.TESTS_DIR,
                                              'fake_data_root/kubernetes')


class TestKubernetesSummary(KubernetesTestsBase):

    def test_services(self):
        expected = {'systemd': {
                        'enabled': [
                            'calico-node',
                            'containerd',
                            'flannel',
                            'kube-proxy-iptables-fix',
                            'snap.kube-apiserver.daemon',
                            'snap.kube-controller-manager.daemon',
                            'snap.kube-proxy.daemon',
                            'snap.kube-scheduler.daemon']
                        },
                    'ps': [
                        'calico-node (3)',
                        'containerd (1)',
                        'containerd-shim-runc-v2 (1)',
                        'flanneld (1)',
                        'kube-apiserver (1)',
                        'kube-controller-manager (1)',
                        'kube-proxy (1)',
                        'kube-scheduler (1)']}
        inst = summary.KubernetesSummary()
        self.assertEqual(self.part_output_to_actual(inst.output)['services'],
                         expected)

    def test_snaps(self):
        result = ['cdk-addons 1.23.0',
                  'core 16-2.54.2',
                  'core18 20211215',
                  'core20 20220114',
                  'kube-apiserver 1.23.3',
                  'kube-controller-manager 1.23.3',
                  'kube-proxy 1.23.3',
                  'kube-scheduler 1.23.3',
                  'kubectl 1.23.3']
        inst = summary.KubernetesSummary()
        self.assertEqual(self.part_output_to_actual(inst.output)['snaps'],
                         result)

    @mock.patch.object(host_helpers.packaging, 'CLIHelper')
    def test_snaps_no_k8s(self, mock_helper):
        mock_helper.return_value.snap_list_all.return_value = \
            SNAP_LIST_ALL_NO_K8S.splitlines()
        inst = summary.KubernetesSummary()
        self.assertFalse(inst.plugin_runnable)
        self.assertTrue('snaps' not in inst.output)

    def test_network_info(self):
        expected = {'flannel.1': {'addr': '10.1.84.0',
                                  'vxlan': {'dev': 'ens3',
                                            'id': '1',
                                            'local_ip': '10.6.3.201'}}}
        inst = summary.KubernetesSummary()
        self.assertEqual(self.part_output_to_actual(inst.output)['flannel'],
                         expected)


@utils.load_templated_tests('scenarios/kubernetes')
class TestKubernetesScenarios(KubernetesTestsBase):
    """
    Scenario tests can be written using YAML templates that are auto-loaded
    into this test runner. This is the recommended way to write tests for
    scenarios. It is however still possible to write the tests in Python if
    required. See defs/tests/README.md for more info.
    """
