import os
import shutil
import tempfile

from unittest import mock

from . import utils

from hotsos.core.config import HotSOSConfig
from hotsos.core.plugins.system.system import NUMAInfo, SystemBase
from hotsos.plugin_extensions.system import (
    checks,
    summary,
)

NUMACTL = """
available: 2 nodes (0-1)
node 0 cpus: 0 2 4 6 8 10 12 14 16 18 20 22 24 26 28 30 32 34 36 38
node 0 size: 96640 MB
node 0 free: 72733 MB
node 1 cpus: 1 3 5 7 9 11 13 15 17 19 21 23 25 27 29 31 33 35 37 39
node 1 size: 96762 MB
node 1 free: 67025 MB
node distances:
node   0   1
  0:  10  21
  1:  21  10
""".splitlines(keepends=True)  # noqa


UBUNTU_PRO_ATTACHED = r"""SERVICE          ENTITLED  STATUS    DESCRIPTION
esm-apps         yes       enabled   Expanded Security Maintenance for Applications
esm-infra        yes       enabled   Expanded Security Maintenance for Infrastructure
livepatch        yes       enabled   Canonical Livepatch service
realtime-kernel  yes       disabled  Ubuntu kernel with PREEMPT_RT patches integrated

Enable services with: pro enable <service>

                Account: Canonical - staff
           Subscription: Ubuntu Pro (Apps-only) - Virtual
            Valid until: Sat Jan  1 02:59:59 4000 +03
Technical support level: essential
""".splitlines(keepends=True)  # noqa

UBUNTU_PRO_NOT_ATTACHED = r"""SERVICE          AVAILABLE  DESCRIPTION
esm-apps         yes        Expanded Security Maintenance for Applications
esm-infra        yes        Expanded Security Maintenance for Infrastructure
livepatch        yes        Canonical Livepatch service
realtime-kernel  yes        Ubuntu kernel with PREEMPT_RT patches integrated

This machine is not attached to an Ubuntu Pro subscription.
See https://ubuntu.com/pro
""".splitlines(keepends=True)  # noqa

UA_NOT_ATTACHED = r"""SERVICE       AVAILABLE  DESCRIPTION
esm-infra     yes        UA Infra: Extended Security Maintenance (ESM)
fips          yes        NIST-certified FIPS modules
fips-updates  yes        Uncertified security updates to FIPS modules
livepatch     yes        Canonical Livepatch service

This machine is not attached to a UA subscription.
See https://ubuntu.com/advantage
""".splitlines(keepends=True)  # noqa

UA_ATTACHED = r"""SERVICE       ENTITLED  STATUS    DESCRIPTION
esm-apps      yes       enabled   UA Apps: Extended Security Maintenance (ESM)
esm-infra     yes       enabled   UA Infra: Extended Security Maintenance (ESM)
fips          yes       n/a       NIST-certified FIPS modules
fips-updates  yes       n/a       Uncertified security updates to FIPS modules
livepatch     yes       n/a       Canonical Livepatch service

Enable services with: ua enable <service>

                Account: Canonical - staff
           Subscription: Ubuntu Pro (Apps-only) - Virtual
            Valid until: 3999-12-31 23:59:59
Technical support level: essential
""".splitlines(keepends=True)  # noqa


class SystemTestsBase(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        HotSOSConfig.plugin_name = 'system'


class TestSystemSummary(SystemTestsBase):

    def test_get_service_info(self):
        expected = {'date': 'Thu Feb 10 16:19:17 UTC 2022',
                    'load': '3.58, 3.27, 2.58',
                    'hostname': 'compute4',
                    'num-cpus': 2,
                    'os': 'ubuntu focal',
                    'rootfs': ('/dev/vda2      308585260 25514372 267326276 '
                               '  9% /'),
                    'ubuntu-pro': {'status': 'not-attached'},
                    'virtualisation': 'kvm',
                    'unattended-upgrades': 'ENABLED'}
        inst = summary.SystemSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual, expected)


class TestNUMAInfo(SystemTestsBase):

    @mock.patch('hotsos.core.plugins.system.system.CLIHelper')
    def test_numainfo(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.numactl.return_value = NUMACTL
        nodes = {0: [0, 2, 4, 6, 8, 10, 12, 14, 16, 18, 20, 22, 24, 26, 28, 30,
                     32, 34, 36, 38],
                 1: [1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23, 25, 27, 29, 31,
                     33, 35, 37, 39]}
        info = NUMAInfo()
        self.assertEqual(info.nodes, nodes)
        self.assertEqual(info.cores(0), nodes[0])
        self.assertEqual(info.cores(1), nodes[1])
        self.assertEqual(info.cores(), nodes[0] + nodes[1])


class TestSYSCtlChecks(SystemTestsBase):

    def test_sysctl_checks(self):
        expected = {'juju-charm-sysctl-mismatch': {
                        'kernel.pid_max': {
                            'conf': '50-ceph-osd-charm.conf',
                            'actual': '4194304',
                            'expected': '2097152'}}}
        inst = checks.SYSCtlChecks()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual, expected)

    def test_sysctl_checks_w_issue(self):
        expected = {'sysctl-mismatch': {
                        'kernel.pid_max': {
                            'actual': '4194304',
                            'expected': '12345678'}},
                    'juju-charm-sysctl-mismatch': {
                        'kernel.pid_max': {
                            'conf': '50-ceph-osd-charm.conf',
                            'actual': '4194304',
                            'expected': '2097152'}}}
        with tempfile.TemporaryDirectory() as dtmp:
            orig_data_root = HotSOSConfig.data_root
            HotSOSConfig.data_root = dtmp
            os.makedirs(os.path.join(dtmp, 'etc'))
            etc_sysctl_conf = os.path.join(orig_data_root, 'etc/sysctl.conf')
            etc_sysctl_d = os.path.join(orig_data_root, 'etc/sysctl.d')
            shutil.copy(etc_sysctl_conf, os.path.join(dtmp, 'etc'))
            etc_sysctl_conf = os.path.join(dtmp, 'etc/sysctl.conf')
            shutil.copytree(etc_sysctl_d, os.path.join(dtmp, 'etc/sysctl.d'))
            shutil.copytree(os.path.join(orig_data_root, 'usr/lib/sysctl.d'),
                            os.path.join(dtmp, 'usr/lib/sysctl.d'))
            os.makedirs(os.path.join(dtmp, 'sos_commands'))
            shutil.copytree(os.path.join(orig_data_root,
                                         'sos_commands/kernel'),
                            os.path.join(dtmp, 'sos_commands/kernel'))

            with open(etc_sysctl_conf, 'a') as fd:
                fd.write('-net.core.rmem_default\n')

            # create a config with an unsetter
            with open(os.path.join(dtmp, 'etc/sysctl.d/99-unit-test.conf'),
                      'w') as fd:
                fd.write("-net.ipv4.conf.all.rp_filter\n")

            # create a config that has not been applied
            with open(os.path.join(dtmp, 'etc/sysctl.d/98-unit-test.conf'),
                      'w') as fd:
                fd.write("kernel.pid_max = 12345678\n")
                fd.write("net.ipv4.conf.all.rp_filter = 200\n")

            # inject an unset value into an invalid file
            with open(os.path.join(dtmp, 'etc/sysctl.d/97-unit-test.conf.bak'),
                      'w') as fd:
                fd.write("kernel.watchdog = 0\n")

            # create a config with an unsetter that wont be applied since it
            # has a lesser priority.
            with open(os.path.join(dtmp, 'etc/sysctl.d/96-unit-test.conf'),
                      'w') as fd:
                fd.write("-kernel.pid_max\n")
                fd.write("net.core.rmem_default = 1000000000\n")

            inst = checks.SYSCtlChecks()
            actual = self.part_output_to_actual(inst.output)
            self.assertEqual(actual, expected)


class TestUbuntuPro(SystemTestsBase):

    @mock.patch('hotsos.core.plugins.system.system.CLIHelper')
    def test_ubuntu_pro_attached(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.pro_status.return_value = UBUNTU_PRO_ATTACHED
        result = SystemBase().ubuntu_pro_status
        self.assertNotEqual(result, None)
        print(result)
        self.assertNotEqual(result, False)

        expected_result = {
            "status": "attached",
            "services": {
                "esm-apps": {
                    "entitled": "yes",
                    "status": "enabled"
                },
                "esm-infra": {
                    "entitled": "yes",
                    "status": "enabled"
                },
                "livepatch": {
                    "entitled": "yes",
                    "status": "enabled"
                },
                "realtime-kernel": {
                    "entitled": "yes",
                    "status": "disabled"
                }
            },
            "account": "Canonical - staff",
            "subscription": "Ubuntu Pro (Apps-only) - Virtual",
            "technical_support_level": "essential",
            "valid_until": "Sat Jan  1 02:59:59 4000 +03"
        }

        self.assertEqual(result, expected_result)

    @mock.patch('hotsos.core.plugins.system.system.CLIHelper')
    def test_ubuntu_pro_not_attached(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.pro_status.return_value = UBUNTU_PRO_NOT_ATTACHED # noqa, pylint: disable=C0301
        result = SystemBase().ubuntu_pro_status
        expected_result = {
            "status": "not-attached"
        }
        self.assertEqual(result, expected_result)

    @mock.patch('hotsos.core.plugins.system.system.CLIHelper')
    def test_ubuntu_advantage_attached(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.pro_status.return_value = UA_ATTACHED
        result = SystemBase().ubuntu_pro_status
        self.assertNotEqual(result, None)

        expected_result = {
            "status": "attached",
            "services": {
                "esm-apps": {
                    "entitled": "yes",
                    "status": "enabled"
                },
                "esm-infra": {
                    "entitled": "yes",
                    "status": "enabled"
                },
                "fips": {
                    "entitled": "yes",
                    "status": "n/a"
                },
                "fips-updates": {
                    "entitled": "yes",
                    "status": "n/a"
                },
                "livepatch": {
                    "entitled": "yes",
                    "status": "n/a"
                }
            },
            "account": "Canonical - staff",
            "subscription": "Ubuntu Pro (Apps-only) - Virtual",
            "technical_support_level": "essential",
            "valid_until": "3999-12-31 23:59:59"
        }

        self.assertEqual(result, expected_result)

    @mock.patch('hotsos.core.plugins.system.system.CLIHelper')
    def test_ubuntu_advantage_not_attached(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        mock_helper.return_value.pro_status.return_value = UA_NOT_ATTACHED
        result = SystemBase().ubuntu_pro_status
        expected_result = {
            "status": "not-attached"
        }
        self.assertEqual(result, expected_result)

    @mock.patch('hotsos.core.plugins.system.system.CLIHelper')
    def test_ubuntu_pro_invalid(self, mock_helper):
        mock_helper.return_value = mock.MagicMock()
        invalid_UBUNTU_PRO = UBUNTU_PRO_ATTACHED
        invalid_UBUNTU_PRO[0] = "MERVICE          ENTITLED  STATUS    DESCRIPTION" # noqa, pylint: disable=C0301
        mock_helper.return_value.pro_status.return_value = invalid_UBUNTU_PRO
        result = SystemBase().ubuntu_pro_status
        expected_result = {
            "status": "error"
        }
        self.assertEqual(result, expected_result)


@utils.load_templated_tests('scenarios/system')
class TestSystemScenarios(SystemTestsBase):
    """
    Scenario tests can be written using YAML templates that are auto-loaded
    into this test runner. This is the recommended way to write tests for
    scenarios. It is however still possible to write the tests in Python if
    required. See defs/tests/README.md for more info.
    """
