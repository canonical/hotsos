
from hotsos.core.host_helpers import packaging as host_pack

from .. import utils

SNAP_LIST_W_DISABLED = """
Name       Version          Rev    Tracking         Publisher       Notes
code       61b3d0ab         228    latest/stable    vscode**        classic
lxd        5.21.4-8caf727   37923  5.21/stable      canonical**     disabled
"""


class TestAPTPackageHelper(utils.BaseTestCase):
    """ Unit tests for apt helper """
    def test_core_packages(self):
        """Test that core APT packages are loaded correctly."""
        expected = {'systemd': '245.4-4ubuntu3.15',
                    'systemd-container': '245.4-4ubuntu3.15',
                    'systemd-sysv': '245.4-4ubuntu3.15',
                    'systemd-timesyncd': '245.4-4ubuntu3.15'}
        obj = host_pack.APTPackageHelper(["systemd"])
        self.assertEqual(obj.all, expected)
        # lookup package already loaded
        self.assertEqual(obj.get_version("systemd"), "245.4-4ubuntu3.15")
        # lookup package not already loaded
        self.assertEqual(obj.get_version("apt"), "2.0.6")

    def test_all_packages(self):
        """Test that core and extra packages are combined."""
        expected = {'python3-systemd': '234-3build2',
                    'systemd': '245.4-4ubuntu3.15',
                    'systemd-container': '245.4-4ubuntu3.15',
                    'systemd-sysv': '245.4-4ubuntu3.15',
                    'systemd-timesyncd': '245.4-4ubuntu3.15'}
        obj = host_pack.APTPackageHelper(["systemd"], ["python3?-systemd"])
        self.assertEqual(obj.all, expected)

    def test_formatted(self):
        """Test formatted APT package output."""
        expected = ['systemd 245.4-4ubuntu3.15',
                    'systemd-container 245.4-4ubuntu3.15',
                    'systemd-sysv 245.4-4ubuntu3.15',
                    'systemd-timesyncd 245.4-4ubuntu3.15']
        obj = host_pack.APTPackageHelper(["systemd"])
        self.assertEqual(obj.all_formatted, expected)


class TestSnapPackageHelper(utils.BaseTestCase):
    """ Unit tests for snap helper """
    def test_all(self):
        """Test that snap packages are loaded and queried."""
        expected = {'core20': {'channel': 'latest/stable',
                               'version': '20220114'}}
        obj = host_pack.SnapPackageHelper(["core20"])
        self.assertEqual(obj.all, expected)
        # lookup package already loaded
        self.assertEqual(obj.get_version("core20"), "20220114")
        # lookup package not already loaded
        self.assertEqual(obj.get_version("lxd"), "4.22")

    def test_formatted(self):
        """Test formatted snap package output."""
        expected = ['core20 20220114 (latest/stable)']
        obj = host_pack.SnapPackageHelper(["core20"])
        self.assertEqual(obj.all_formatted, expected)

    @utils.create_data_root({'sos_commands/snap/snap_list_--all':
                             SNAP_LIST_W_DISABLED})
    def test_ignore_disabled(self):
        """Test that disabled snaps are excluded by default."""
        obj = host_pack.SnapPackageHelper(core_snaps=['code', 'lxd'])
        self.assertEqual(obj.all_formatted, ['code 61b3d0ab (latest/stable)'])

    @utils.create_data_root({'sos_commands/snap/snap_list_--all':
                             SNAP_LIST_W_DISABLED})
    def test_dont_ignore_disabled(self):
        """Test that disabled snaps are included when requested."""
        obj = host_pack.SnapPackageHelper(core_snaps=['code', 'lxd'],
                                          ignore_disabled=False)
        self.assertListEqual(obj.all_formatted,
                             ['code 61b3d0ab (latest/stable)',
                              'lxd 5.21.4-8caf727 (5.21/stable)'])


class TestDPKGVersion(utils.BaseTestCase):  # noqa, pylint: disable=too-many-public-methods
    """ Unit tests for dpkg version helper """
    def test_dpkg_normalize_string_repr(self):
        """Test string representation of normalized criteria."""
        data = [
            {"ge": "8.9"}, {"lt": "4"}, {"ge": "6.3", "lt": "7.2"}
        ]

        self.assertEqual(
            repr(host_pack.DPKGVersion.normalize_version_criteria(data)),
            "[{'ge': 8.9}, {'ge': 6.3, 'lt': 7.2}, {'lt': 4}]")

    def test_dpkg_version_comparison(self):
        """Test normalization with overlapping gt criteria."""
        data = [
             {"gt": '1.2~1'}, {"gt": '1.2~2'}, {"gt": '1.2'}
        ]

        result = host_pack.DPKGVersion.normalize_version_criteria(data)
        expected = [
            {'gt': '1.2'},
            {'gt': '1.2~2', 'le': '1.2'},
            {'gt': '1.2~1', 'le': '1.2~2'}
        ]
        self.assertEqual(result, expected)

    def test_dpkg_version_normalize_00(self):
        """Test normalization with single-element criteria."""
        for elem in ['eq', 'ge', 'gt', 'le', 'lt', 'min', 'max']:
            data = [
                {
                    elem: '1'
                }
            ]
            result = host_pack.DPKGVersion.normalize_version_criteria(data)
            self.assertEqual(result, data)

    def test_dpkg_version_normalize_01(self):
        """Test normalization with two-element range criteria."""
        for elem_a in ['eq', 'ge', 'gt', 'le', 'lt']:
            for elem_b in ['eq', 'ge', 'gt', 'le', 'lt']:
                if elem_a.startswith(elem_b[0]):
                    continue
                data = [
                    {
                        elem_a: '3', elem_b: '4'
                    },
                    {
                        elem_a: '1', elem_b: '2'
                    },
                ]
                result = host_pack.DPKGVersion.normalize_version_criteria(data)
                self.assertEqual(result, data)

    def test_dpkg_version_normalize_02(self):
        """Test normalization with mixed gt and lt criteria."""
        data = [
            {'gt': '1'}, {'gt': '2'}, {'lt': '4'}
        ]
        result = host_pack.DPKGVersion.normalize_version_criteria(data)
        expected = [
            {'lt': '4', 'gt': '4'},
            {'gt': '2', 'le': '4'},
            {'gt': '1', 'le': '2'}
        ]
        self.assertEqual(result, expected)

    def test_dpkg_version_normalize_03(self):
        """Test normalization with bounded and unbounded ranges."""
        data = [
            {'gt': '1', 'lt': '2'}, {'gt': '3'}, {'gt': '4'}
        ]
        result = host_pack.DPKGVersion.normalize_version_criteria(data)
        expected = [
            {'gt': '4'},
            {'gt': '3', 'le': '4'},
            {'gt': '1', 'lt': '2'}
        ]
        self.assertEqual(result, expected)

    def test_dpkg_version_normalize_04(self):
        """Test normalization with multiple bounded ranges."""
        data = [
            {'gt': '1', 'lt': '2'}, {'gt': '3', 'lt': '4'}, {'gt': '4'}
        ]
        result = host_pack.DPKGVersion.normalize_version_criteria(data)
        expected = [
            {'gt': '4'},
            {'gt': '3', 'lt': '4'},
            {'gt': '1', 'lt': '2'}
        ]
        self.assertEqual(result, expected)

    def test_dpkg_version_normalize_05(self):
        """Test normalization fills gaps between ranges."""
        data = [
            {'gt': '1'}, {'gt': '3', 'lt': '4'}, {'gt': '4'}
        ]
        result = host_pack.DPKGVersion.normalize_version_criteria(data)
        expected = [
            {'gt': '4'},
            {'gt': '3', 'lt': '4'},
            {'gt': '1', 'le': '3'}
        ]
        self.assertEqual(result, expected)

    def test_dpkg_version_normalize_06(self):
        """Test normalization with multiple lt criteria."""
        data = [
            {'lt': '2'}, {'lt': '3'}, {'lt': '4'}
        ]
        result = host_pack.DPKGVersion.normalize_version_criteria(data)
        expected = [
            {'ge': '3', 'lt': '4'},
            {'lt': '2'},
            {'ge': '2', 'lt': '3'},
        ]
        self.assertEqual(result, expected)

    def test_dpkg_version_normalize_07(self):
        """Test normalization converts min/max to ge/le."""
        data = [
            {'min': '2', 'max': '3'}
        ]
        result = host_pack.DPKGVersion.normalize_version_criteria(data)
        expected = [
            {'ge': '2', 'le': '3'}
        ]
        self.assertEqual(result, expected)

    def test_dpkg_version_pkgver_bad_version(self):
        """Test that invalid version string raises error."""
        with self.assertRaises(host_pack.DPKGBadVersionSyntax):
            host_pack.DPKGVersion.is_version_within_ranges(
                '1:8.2p1-4ubuntu0.4',
                [{'lt': 'immabadversion'}]
            )

    def test_dpkg_version_pkgver_lt_false(self):
        """Test lt returns false when version equals bound."""
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'lt': '1:8.2p1-4ubuntu0.4'}]
        )
        self.assertFalse(result)

    def test_dpkg_version_pkgver_lt_true(self):
        """Test lt returns true when version is less."""
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'lt': '1:8.2p1-4ubuntu0.5'}]
        )
        self.assertTrue(result)

    def test_dpkg_version_pkgver_le_false(self):
        """Test le returns false when version exceeds bound."""
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'le': '1:8.2p1-4ubuntu0.3'}]
        )
        self.assertFalse(result)

    def test_dpkg_version_pkgver_le_true_eq(self):
        """Test le returns true when version equals bound."""
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'le': '1:8.2p1-4ubuntu0.4'}]
        )
        self.assertTrue(result)

    def test_dpkg_version_pkgver_le_true_less(self):
        """Test le returns true when version is less."""
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'le': '1:8.2p1-4ubuntu0.4'}]
        )
        self.assertTrue(result)

    def test_dpkg_version_pkgver_gt_false(self):
        """Test gt returns false when version is less."""
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'gt': '1:8.2p1-4ubuntu0.5'}]
        )
        self.assertFalse(result)

    def test_dpkg_version_pkgver_gt_true(self):
        """Test gt returns true when version is greater."""
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'gt': '1:8.2p1-4ubuntu0.3'}]
        )
        self.assertTrue(result)

    def test_dpkg_version_pkgver_ge_false(self):
        """Test ge returns false when version is less."""
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'ge': '1:8.2p1-4ubuntu0.5'}]
        )
        self.assertFalse(result)

    def test_dpkg_version_pkgver_ge_true_eq(self):
        """Test ge returns true when version equals bound."""
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'ge': '1:8.2p1-4ubuntu0.4'}]
        )
        self.assertTrue(result)

    def test_dpkg_version_pkgver_ge_true_greater(self):
        """Test ge returns true when version exceeds bound."""
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'ge': '1:8.2p1-4ubuntu0.3'}]
        )
        self.assertTrue(result)

    def test_dpkg_version_pkgver_is_equal_true(self):
        """Test eq returns true for matching versions."""
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'eq': '1:8.2p1-4ubuntu0.4'}]
        )
        self.assertTrue(result)

    def test_dpkg_version_pkgver_is_equal_false(self):
        """Test eq returns false for different versions."""
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'eq': '1:8.2p1-4ubuntu0.3'}]
        )
        self.assertFalse(result)

    def test_dpkg_version_pkgver_within_ranges_true(self):
        """Test version within min/max range returns true."""
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'min': '1:8.2',
              'max': '1:8.3'}])
        self.assertTrue(result)

    def test_dpkg_version_pkgver_within_ranges_false(self):
        """Test version outside min/max range returns false."""
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'min': '1:8.2',
              'max': '1:8.2'}])
        self.assertFalse(result)

    def test_dpkg_version_pkgver_within_ranges_multi(self):
        """Test version matches second of multiple ranges."""
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'min': '1:8.0',
              'max': '1:8.1'},
             {'min': '1:8.2',
              'max': '1:8.3'}])
        self.assertTrue(result)

    def test_dpkg_version_pkgver_within_ranges_no_max_true(self):
        """Test open-ended min ranges match correctly."""
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'min': '1:8.0'},
             {'min': '1:8.1'},
             {'min': '1:8.2'},
             {'min': '1:8.3'}])
        self.assertTrue(result)

    def test_dpkg_version_pkgver_within_ranges_no_max_false(self):
        """Test open-ended min ranges reject lower version."""
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'min': '1:8.3'},
             {'min': '1:8.4'},
             {'min': '1:8.5'}])
        self.assertFalse(result)

    def test_dpkg_version_pkgver_within_ranges_mixed_true(self):
        """Test mixed bounded/unbounded ranges match."""
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'min': '1:8.0'},
             {'min': '1:8.1',
              'max': '1:8.1.1'},
             {'min': '1:8.2'},
             {'min': '1:8.3'}])
        self.assertTrue(result)

    def test_dpkg_version_pkgver_within_ranges_mixed_false(self):
        """Test mixed ranges reject version at exact max."""
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'min': '1:8.0'},
             {'min': '1:8.1',
              'max': '1:8.1.1'},
             {'min': '1:8.2',
              'max': '1:8.2'},
             {'min': '1:8.3'}])
        self.assertFalse(result)

    def test_dpkg_version_pkgver_within_ranges_mixed_lg_false(self):
        """Test gt/lt mixed ranges reject equal version."""
        # 1:8.2p1-4ubuntu0.4
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'gt': '1:8.2p1-4ubuntu0.4'},
             {'gt': '1:8.1',
              'lt': '1:8.1.1'},
             {'gt': '1:8.2',
              'lt': '1:8.2'},
             {'gt': '1:8.3'}]
        )
        self.assertFalse(result)

    def test_dpkg_version_pkgver_within_ranges_mixed_lg_true(self):
        """Test gt/lt mixed ranges accept version in range."""
        # 1:8.2p1-4ubuntu0.4
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'gt': '1:8.2p1-4ubuntu0.4'},
             {'gt': '1:8.1',
              'lt': '1:8.1.1'},
             {'gt': '1:8.2p1-4ubuntu0.3',
              'lt': '1:8.2p1-4ubuntu0.5'},
             {'gt': '1:8.3'}]
        )
        self.assertTrue(result)

    def test_dpkg_version_pkgver_within_ranges_first_true(self):
        """Test ge match on first range entry."""
        # 1:8.2p1-4ubuntu0.4
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'ge': '1:8.2p1-4ubuntu0.4'},
             {'gt': '1:8.1',
              'lt': '1:8.1.1'},
             {'gt': '1:8.2p1-4ubuntu0.3',
              'lt': '1:8.2p1-4ubuntu0.5'},
             {'gt': '1:8.3'}]
        )
        self.assertTrue(result)

    def test_dpkg_version_pkgver_within_ranges_mid_true(self):
        """Test le match on middle range entry."""
        # 1:8.2p1-4ubuntu0.4
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'gt': '1:8.2p1-4ubuntu0.4'},
             {'gt': '1:8.1',
              'le': '1:8.2p1-4ubuntu0.4'},
             {'gt': '1:8.2p1-4ubuntu0.6',
              'lt': '1:8.2p1-4ubuntu0.9'},
             {'gt': '1:8.3'}]
        )
        self.assertTrue(result)

    def test_dpkg_version_pkgver_within_ranges_last_true(self):
        """Test eq match on last range entry."""
        # 1:8.2p1-4ubuntu0.4
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'gt': '1:8.2p1-4ubuntu0.4'},
             {'gt': '1:8.1',
              'le': '1:8.2p1-4ubuntu0.4'},
             {'gt': '1:8.2p1-4ubuntu0.6',
              'lt': '1:8.2p1-4ubuntu0.9'},
             {'eq': '1:8.2p1-4ubuntu0.4'}]
        )
        self.assertTrue(result)

    def test_dpkg_version_invalid_op_name(self):
        """Test that invalid operator name raises exception."""
        with self.assertRaises(Exception):
            # 1:8.2p1-4ubuntu0.4
            host_pack.DPKGVersion.is_version_within_ranges(
                '1:8.2p1-4ubuntu0.4',
                [{'foo': '1:8.2p1-4ubuntu0.4'}]
            )
