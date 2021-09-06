import os

import mock

import utils

from core import checks


class TestChecks(utils.BaseTestCase):

    def setUp(self):
        # NOTE: remember that data_root is configured so helpers will always
        # use fake_data_root if possible. If you write a test that wants to
        # test scenario where no data root is set (i.e. no sosreport) you need
        # to unset it as part of the test.
        super().setUp()

    def tearDown(self):
        super().tearDown()

    def test_APTPackageChecksBase_core_only(self):
        expected = {'systemd': '245.4-4ubuntu3.11',
                    'systemd-container': '245.4-4ubuntu3.11',
                    'systemd-sysv': '245.4-4ubuntu3.11',
                    'systemd-timesyncd': '245.4-4ubuntu3.11'}
        obj = checks.APTPackageChecksBase(["systemd"])
        self.assertEqual(obj.all, expected)
        # lookup package already loaded
        self.assertEqual(obj.get_version("systemd"), "245.4-4ubuntu3.11")
        # lookup package not already loaded
        self.assertEqual(obj.get_version("apt"), "2.0.6")

    def test_APTPackageChecksBase_all(self):
        expected = {'python3-systemd': '234-3build2',
                    'systemd': '245.4-4ubuntu3.11',
                    'systemd-container': '245.4-4ubuntu3.11',
                    'systemd-sysv': '245.4-4ubuntu3.11',
                    'systemd-timesyncd': '245.4-4ubuntu3.11'}
        obj = checks.APTPackageChecksBase(["systemd"], ["python3?-systemd"])
        self.assertEqual(obj.all, expected)

    def test_APTPackageChecksBase_formatted(self):
        expected = ['systemd 245.4-4ubuntu3.11',
                    'systemd-container 245.4-4ubuntu3.11',
                    'systemd-sysv 245.4-4ubuntu3.11',
                    'systemd-timesyncd 245.4-4ubuntu3.11']
        obj = checks.APTPackageChecksBase(["systemd"])
        self.assertEqual(obj.all_formatted, expected)

    def test_SnapPackageChecksBase(self):
        expected = {'core': '16-2.48.2'}
        obj = checks.SnapPackageChecksBase(["core"])
        self.assertEqual(obj.all, expected)
        # lookup package already loaded
        self.assertEqual(obj.get_version("core"), "16-2.48.2")
        # lookup package not already loaded
        self.assertEqual(obj.get_version("juju"), "2.7.8")

    def test_SnapPackageChecksBase_formatted(self):
        expected = ['core 16-2.48.2']
        obj = checks.SnapPackageChecksBase(["core"])
        self.assertEqual(obj.all_formatted, expected)

    def test_PackageBugChecksBase(self):
        os.environ['PLUGIN_NAME'] = 'openstack'
        with mock.patch.object(checks, 'add_known_bug') as mock_add_known_bug:
            pkg_info = {'neutron-common': '2:16.4.0-0ubuntu4~cloud0'}
            obj = checks.PackageBugChecksBase('ussuri', pkg_info)
            obj()
            self.assertFalse(mock_add_known_bug.called)

            mock_add_known_bug.reset_mock()
            pkg_info = {'neutron-common': '2:16.4.0-0ubuntu2~cloud0'}
            obj = checks.PackageBugChecksBase('ussuri', pkg_info)
            obj()
            self.assertTrue(mock_add_known_bug.called)

            mock_add_known_bug.reset_mock()
            pkg_info = {'neutron-common': '2:16.2.0-0ubuntu4~cloud0'}
            obj = checks.PackageBugChecksBase('ussuri', pkg_info)
            obj()
            self.assertFalse(mock_add_known_bug.called)
