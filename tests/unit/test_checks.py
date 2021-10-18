import os
import yaml

import mock

import utils

from core import checks


YAML_DEF1 = """
pluginX:
  groupA:
    input:
      type: filesystem
      value: foo/bar1
    sectionA:
      artifactX:
        settingA: True
"""

YAML_DEF2 = """
pluginX:
  groupA:
    input:
      type: filesystem
      value: foo/bar1
    sectionA:
      input:
        type: filesystem
        value: foo/bar2
      artifactX:
        settingA: True
"""

YAML_DEF3 = """
pluginX:
  groupA:
    input:
      type: filesystem
      value: foo/bar1
    sectionA:
      input:
        type: filesystem
        value: foo/bar2
      artifactX:
        input:
            type: filesystem
            value: foo/bar3
        settingA: True
"""


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

    def test_yaml_def_group_input(self):
        plugin_checks = yaml.safe_load(YAML_DEF1).get('pluginX')
        for name, group in plugin_checks.items():
            group = checks.YAMLDefGroup(name, group, event_check_obj=None)
            for section in group.sections:
                for entry in section.entries:
                    self.assertEquals(entry.input.type, 'filesystem')
                    self.assertEquals(entry.input.value,
                                      os.path.join(checks.constants.DATA_ROOT,
                                                   'foo/bar1'))

    def test_yaml_def_section_input_override(self):
        plugin_checks = yaml.safe_load(YAML_DEF2).get('pluginX')
        for name, group in plugin_checks.items():
            group = checks.YAMLDefGroup(name, group, event_check_obj=None)
            for section in group.sections:
                for entry in section.entries:
                    self.assertEquals(entry.input.type, 'filesystem')
                    self.assertEquals(entry.input.value,
                                      os.path.join(checks.constants.DATA_ROOT,
                                                   'foo/bar2'))

    def test_yaml_def_entry_input_override(self):
        plugin_checks = yaml.safe_load(YAML_DEF3).get('pluginX')
        for name, group in plugin_checks.items():
            group = checks.YAMLDefGroup(name, group, event_check_obj=None)
            for section in group.sections:
                for entry in section.entries:
                    self.assertEquals(entry.input.type, 'filesystem')
                    self.assertEquals(entry.input.value,
                                      os.path.join(checks.constants.DATA_ROOT,
                                                   'foo/bar3'))
