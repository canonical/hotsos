import os
import shutil
import tempfile

import mock

from tests.unit import utils

from core.issues.issue_types import KubernetesWarning
from core import checks, constants, cli_helpers
from core.plugins import kubernetes as kubernetes_core
from core.ycheck.bugs import YBugChecker
from core.ycheck.scenarios import YScenarioChecker
from plugins.kubernetes.pyparts import (
    service_info,
    network_checks,
)

SYSTEMD_UNITS = """
UNIT FILE                                               STATE           VENDOR PRESET
calico-node.service                    enabled         enabled      
containerd.service                     enabled         enabled      
flannel.service                        enabled         enabled      
snap.kube-proxy.daemon.service         enabled         enabled      
snap.kubelet.daemon.service            enabled         enabled      
"""  # noqa


class KubernetesTestsBase(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        os.environ['PLUGIN_NAME'] = 'kubernetes'


class TestKubernetesServiceInfo(KubernetesTestsBase):

    def setUp(self):
        self.snaps_list = cli_helpers.CLIHelper().snap_list_all()
        super().setUp()

    def test_get_service_info(self):
        orig_ps = checks.CLIHelper().ps()
        with mock.patch('core.checks.CLIHelper') as mock_helper:
            mock_helper.return_value = mock.MagicMock()
            helper = mock_helper.return_value
            helper.systemctl_list_unit_files.return_value = \
                SYSTEMD_UNITS.split('\n')
            helper.ps.return_value = orig_ps
            expected = {'systemd': {
                            'enabled': [
                                'calico-node',
                                'containerd',
                                'flannel',
                                'snap.kube-proxy.daemon',
                                'snap.kubelet.daemon']
                            },
                        'ps': [
                            'calico-node (3)',
                            'containerd (17)',
                            'containerd-shim-runc-v2 (1)',
                            'flanneld (1)',
                            'kube-proxy (1)',
                            'kubelet (1)']}
            inst = service_info.KubernetesServiceChecks()
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
        inst = service_info.KubernetesPackageChecks()
        inst()
        self.assertEqual(inst.output['snaps'], result)

    @mock.patch.object(checks, 'CLIHelper')
    def test_get_snap_info_from_line_no_k8s(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        filterered_snaps = []
        for line in self.snaps_list:
            found = False
            for pkg in kubernetes_core.K8S_PACKAGES:
                obj = service_info.KubernetesPackageChecks()
                if obj.snap_check._get_snap_info_from_line(line, pkg):
                    found = True
                    break

            if not found:
                filterered_snaps.append(line)

        mock_helper.return_value.snap_list_all.return_value = filterered_snaps
        inst = service_info.KubernetesPackageChecks()
        inst()
        self.assertFalse(inst.plugin_runnable)
        self.assertEqual(inst.output, None)


class TestKubernetesNetworkChecks(KubernetesTestsBase):

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
            inst = network_checks.KubernetesNetworkChecks()
            inst()
            self.assertEqual(inst.output, expected)


class TestKubernetesBugChecks(KubernetesTestsBase):

    @mock.patch('core.ycheck.bugs.add_known_bug')
    def test_bug_checks(self, mock_add_known_bug):
        bugs = []

        def fake_add_bug(*args, **kwargs):
            bugs.append((args, kwargs))

        mock_add_known_bug.side_effect = fake_add_bug
        YBugChecker()()
        # This will need modifying once we have some storage bugs defined
        self.assertFalse(mock_add_known_bug.called)
        self.assertEqual(len(bugs), 0)


class TestKubernetesScenarioChecks(KubernetesTestsBase):

    @mock.patch('core.ycheck.YDefsLoader._is_def',
                new=utils.is_def_filter('system_cpufreq_mode.yaml'))
    @mock.patch('core.plugins.system.SystemBase.virtualisation_type',
                None)
    @mock.patch('core.plugins.kernel.CPU.cpufreq_scaling_governor_all',
                'powersave')
    @mock.patch('core.plugins.kubernetes.KubernetesChecksBase.plugin_runnable',
                True)
    @mock.patch.object(checks, 'CLIHelper')
    @mock.patch('core.ycheck.scenarios.issue_utils.add_issue')
    def test_system_cpufreq_mode(self, mock_add_issue, mock_cli):
        issues = {}

        def fake_add_issue(issue):
            if type(issue) in issues:
                issues[type(issue)].append(issue.msg)
            else:
                issues[type(issue)] = [issue.msg]

        mock_cli.return_value = mock.MagicMock()
        mock_cli.return_value.snap_list_all.return_value = \
            ['kubelet 1.2.3 123\n']

        mock_add_issue.side_effect = fake_add_issue
        YScenarioChecker()()
        self.assertTrue(mock_add_issue.called)
        msg = ('This node is used for Kubernetes but is not using '
               'cpufreq scaling_governor in "performance" mode '
               '(actual=powersave). This is not recommended and can result in '
               'performance degradation. To fix this you can install '
               'cpufrequtils and set "GOVERNOR=performance" in '
               '/etc/default/cpufrequtils. NOTE: requires node reboot to '
               'take effect.')
        self.assertEqual(issues[KubernetesWarning], [msg])
