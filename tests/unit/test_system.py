import os
import shutil
import tempfile

import mock

import utils

from core.ycheck.bugs import YBugChecker
from plugins.system.pyparts import (
    checks,
    general,
)


class SystemTestsBase(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        os.environ['PLUGIN_NAME'] = 'system'


class TestSystemGeneral(SystemTestsBase):

    def test_get_service_info(self):
        expected = {'date': 'Tue Aug 3 10:31:30 UTC 2021',
                    'hostname': 'compute4',
                    'num-cpus': 2,
                    'os': 'ubuntu focal',
                    'virtualisation': 'kvm',
                    'unattended-upgrades': 'ENABLED'}
        inst = general.SystemGeneral()
        inst()
        self.assertEqual(inst.output, expected)


class TestSystemChecks(SystemTestsBase):

    def test_sysctl_checks(self):
        expected = {'juju-charm-sysctl-mismatch': {
                        'kernel.pid_max': {
                            'conf': '50-ceph-osd-charm.conf',
                            'actual': '4194304',
                            'expected': '2097152'}}}
        inst = checks.SystemChecks()
        inst()
        self.assertEqual(inst.output, expected)

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
            orig_data_root = os.environ['DATA_ROOT']
            os.environ['DATA_ROOT'] = dtmp
            os.makedirs(os.path.join(dtmp, 'etc'))
            etc_sysctl_conf = os.path.join(orig_data_root, 'etc/sysctl.conf')
            etc_sysctl_d = os.path.join(orig_data_root, 'etc/sysctl.d')
            shutil.copy(etc_sysctl_conf, os.path.join(dtmp, 'etc'))
            shutil.copytree(etc_sysctl_d, os.path.join(dtmp, 'etc/sysctl.d'))
            shutil.copytree(os.path.join(orig_data_root, 'usr/lib/sysctl.d'),
                            os.path.join(dtmp, 'usr/lib/sysctl.d'))
            os.makedirs(os.path.join(dtmp, 'sos_commands'))
            shutil.copytree(os.path.join(orig_data_root,
                                         'sos_commands/kernel'),
                            os.path.join(dtmp, 'sos_commands/kernel'))

            # inject an unset value
            with open(os.path.join(dtmp, 'etc/sysctl.d/99-unit-test.conf'),
                      'w') as fd:
                fd.write("kernel.pid_max = 12345678")

            # inject an unset value into an invalid file
            with open(os.path.join(dtmp, 'etc/sysctl.d/98-unit-test.conf.bak'),
                      'w') as fd:
                fd.write("kernel.watchdog = 0")

            inst = checks.SystemChecks()
            inst()
            self.assertEqual(inst.output, expected)


class TestSystemBugChecks(SystemTestsBase):

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
