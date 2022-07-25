import os

from . import utils

from hotsos.core import host_helpers
from hotsos.core.config import HotSOSConfig


DUMMY_CONFIG = """
[a-section]
a-key = 1023
b-key = 10-23
c-key = 2-8,10-31
"""


class TestChecks(utils.BaseTestCase):

    def test_APTPackageChecksBase_core_only(self):
        expected = {'systemd': '245.4-4ubuntu3.15',
                    'systemd-container': '245.4-4ubuntu3.15',
                    'systemd-sysv': '245.4-4ubuntu3.15',
                    'systemd-timesyncd': '245.4-4ubuntu3.15'}
        obj = host_helpers.APTPackageChecksBase(["systemd"])
        self.assertEqual(obj.all, expected)
        # lookup package already loaded
        self.assertEqual(obj.get_version("systemd"), "245.4-4ubuntu3.15")
        # lookup package not already loaded
        self.assertEqual(obj.get_version("apt"), "2.0.6")

    def test_APTPackageChecksBase_all(self):
        expected = {'python3-systemd': '234-3build2',
                    'systemd': '245.4-4ubuntu3.15',
                    'systemd-container': '245.4-4ubuntu3.15',
                    'systemd-sysv': '245.4-4ubuntu3.15',
                    'systemd-timesyncd': '245.4-4ubuntu3.15'}
        obj = host_helpers.APTPackageChecksBase(["systemd"],
                                                ["python3?-systemd"])
        self.assertEqual(obj.all, expected)

    def test_APTPackageChecksBase_formatted(self):
        expected = ['systemd 245.4-4ubuntu3.15',
                    'systemd-container 245.4-4ubuntu3.15',
                    'systemd-sysv 245.4-4ubuntu3.15',
                    'systemd-timesyncd 245.4-4ubuntu3.15']
        obj = host_helpers.APTPackageChecksBase(["systemd"])
        self.assertEqual(obj.all_formatted, expected)

    def test_SnapPackageChecksBase(self):
        expected = {'core20': '20220114'}
        obj = host_helpers.SnapPackageChecksBase(["core20"])
        self.assertEqual(obj.all, expected)
        # lookup package already loaded
        self.assertEqual(obj.get_version("core20"), "20220114")
        # lookup package not already loaded
        self.assertEqual(obj.get_version("lxd"), "4.22")

    def test_SnapPackageChecksBase_formatted(self):
        expected = ['core20 20220114']
        obj = host_helpers.SnapPackageChecksBase(["core20"])
        self.assertEqual(obj.all_formatted, expected)

    @utils.create_test_files({'test.conf': DUMMY_CONFIG})
    def test_sectionalconfig_base(self):
        conf = os.path.join(HotSOSConfig.DATA_ROOT, 'test.conf')
        cfg = host_helpers.SectionalConfigBase(conf)
        self.assertTrue(cfg.exists)
        self.assertEqual(cfg.get('a-key'), '1023')
        self.assertEqual(cfg.get('a-key', section='a-section'), '1023')
        self.assertEqual(cfg.get('a-key', section='missing-section'), None)
        self.assertEqual(cfg.get('a-key', expand_to_list=True), [1023])

        expanded = cfg.get('b-key', expand_to_list=True)
        self.assertEqual(expanded, list(range(10, 24)))
        self.assertEqual(cfg.squash_int_range(expanded), '10-23')

        expanded = cfg.get('c-key', expand_to_list=True)
        self.assertEqual(expanded, list(range(2, 9)) + list(range(10, 32)))
        self.assertEqual(cfg.squash_int_range(expanded), '2-8,10-31')
