
from hotsos.core.host_helpers import packaging as host_pack

from .. import utils


class TestAPTPackageHelper(utils.BaseTestCase):
    """ Unit tests for apt helper """
    def test_core_packages(self):
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
        expected = {'python3-systemd': '234-3build2',
                    'systemd': '245.4-4ubuntu3.15',
                    'systemd-container': '245.4-4ubuntu3.15',
                    'systemd-sysv': '245.4-4ubuntu3.15',
                    'systemd-timesyncd': '245.4-4ubuntu3.15'}
        obj = host_pack.APTPackageHelper(["systemd"], ["python3?-systemd"])
        self.assertEqual(obj.all, expected)

    def test_formatted(self):
        expected = ['systemd 245.4-4ubuntu3.15',
                    'systemd-container 245.4-4ubuntu3.15',
                    'systemd-sysv 245.4-4ubuntu3.15',
                    'systemd-timesyncd 245.4-4ubuntu3.15']
        obj = host_pack.APTPackageHelper(["systemd"])
        self.assertEqual(obj.all_formatted, expected)


class TestSnapPackageHelper(utils.BaseTestCase):
    """ Unit tests for snap helper """
    def test_all(self):
        expected = {'core20': {'channel': 'latest/stable',
                               'version': '20220114'}}
        obj = host_pack.SnapPackageHelper(["core20"])
        self.assertEqual(obj.all, expected)
        # lookup package already loaded
        self.assertEqual(obj.get_version("core20"), "20220114")
        # lookup package not already loaded
        self.assertEqual(obj.get_version("lxd"), "4.22")

    def test_formatted(self):
        expected = ['core20 20220114']
        obj = host_pack.SnapPackageHelper(["core20"])
        self.assertEqual(obj.all_formatted, expected)


class TestDPKGVersion(utils.BaseTestCase):  # noqa, pylint: disable=too-many-public-methods
    """ Unit tests for dpkg version helper """
    def test_dpkg_normalize_string_repr(self):
        data = [
            {"ge": "8.9"}, {"lt": "4"}, {"ge": "6.3", "lt": "7.2"}
        ]

        self.assertEqual(
            repr(host_pack.DPKGVersion.normalize_version_criteria(data)),
            "[{'ge': 8.9}, {'ge': 6.3, 'lt': 7.2}, {'lt': 4}]")

    def test_dpkg_version_comparison(self):
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
        for elem in ['eq', 'ge', 'gt', 'le', 'lt', 'min', 'max']:
            data = [
                {
                    elem: '1'
                }
            ]
            result = host_pack.DPKGVersion.normalize_version_criteria(data)
            self.assertEqual(result, data)

    def test_dpkg_version_normalize_01(self):
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
        data = [
            {'min': '2', 'max': '3'}
        ]
        result = host_pack.DPKGVersion.normalize_version_criteria(data)
        expected = [
            {'ge': '2', 'le': '3'}
        ]
        self.assertEqual(result, expected)

    def test_dpkg_version_pkgver_bad_version(self):
        with self.assertRaises(host_pack.DPKGBadVersionSyntax):
            host_pack.DPKGVersion.is_version_within_ranges(
                '1:8.2p1-4ubuntu0.4',
                [{'lt': 'immabadversion'}]
            )

    def test_dpkg_version_pkgver_lt_false(self):
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'lt': '1:8.2p1-4ubuntu0.4'}]
        )
        self.assertFalse(result)

    def test_dpkg_version_pkgver_lt_true(self):
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'lt': '1:8.2p1-4ubuntu0.5'}]
        )
        self.assertTrue(result)

    def test_dpkg_version_pkgver_le_false(self):
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'le': '1:8.2p1-4ubuntu0.3'}]
        )
        self.assertFalse(result)

    def test_dpkg_version_pkgver_le_true_eq(self):
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'le': '1:8.2p1-4ubuntu0.4'}]
        )
        self.assertTrue(result)

    def test_dpkg_version_pkgver_le_true_less(self):
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'le': '1:8.2p1-4ubuntu0.4'}]
        )
        self.assertTrue(result)

    def test_dpkg_version_pkgver_gt_false(self):
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'gt': '1:8.2p1-4ubuntu0.5'}]
        )
        self.assertFalse(result)

    def test_dpkg_version_pkgver_gt_true(self):
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'gt': '1:8.2p1-4ubuntu0.3'}]
        )
        self.assertTrue(result)

    def test_dpkg_version_pkgver_ge_false(self):
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'ge': '1:8.2p1-4ubuntu0.5'}]
        )
        self.assertFalse(result)

    def test_dpkg_version_pkgver_ge_true_eq(self):
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'ge': '1:8.2p1-4ubuntu0.4'}]
        )
        self.assertTrue(result)

    def test_dpkg_version_pkgver_ge_true_greater(self):
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'ge': '1:8.2p1-4ubuntu0.3'}]
        )
        self.assertTrue(result)

    def test_dpkg_version_pkgver_is_equal_true(self):
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'eq': '1:8.2p1-4ubuntu0.4'}]
        )
        self.assertTrue(result)

    def test_dpkg_version_pkgver_is_equal_false(self):
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'eq': '1:8.2p1-4ubuntu0.3'}]
        )
        self.assertFalse(result)

    def test_dpkg_version_pkgver_within_ranges_true(self):
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'min': '1:8.2',
              'max': '1:8.3'}])
        self.assertTrue(result)

    def test_dpkg_version_pkgver_within_ranges_false(self):
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'min': '1:8.2',
              'max': '1:8.2'}])
        self.assertFalse(result)

    def test_dpkg_version_pkgver_within_ranges_multi(self):
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'min': '1:8.0',
              'max': '1:8.1'},
             {'min': '1:8.2',
              'max': '1:8.3'}])
        self.assertTrue(result)

    def test_dpkg_version_pkgver_within_ranges_no_max_true(self):
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'min': '1:8.0'},
             {'min': '1:8.1'},
             {'min': '1:8.2'},
             {'min': '1:8.3'}])
        self.assertTrue(result)

    def test_dpkg_version_pkgver_within_ranges_no_max_false(self):
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'min': '1:8.3'},
             {'min': '1:8.4'},
             {'min': '1:8.5'}])
        self.assertFalse(result)

    def test_dpkg_version_pkgver_within_ranges_mixed_true(self):
        result = host_pack.DPKGVersion.is_version_within_ranges(
            '1:8.2p1-4ubuntu0.4',
            [{'min': '1:8.0'},
             {'min': '1:8.1',
              'max': '1:8.1.1'},
             {'min': '1:8.2'},
             {'min': '1:8.3'}])
        self.assertTrue(result)

    def test_dpkg_version_pkgver_within_ranges_mixed_false(self):
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
        with self.assertRaises(Exception):
            # 1:8.2p1-4ubuntu0.4
            host_pack.DPKGVersion.is_version_within_ranges(
                '1:8.2p1-4ubuntu0.4',
                [{'foo': '1:8.2p1-4ubuntu0.4'}]
            )
