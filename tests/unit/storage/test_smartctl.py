from hotsos.core.config import HotSOSConfig
from hotsos.plugin_extensions.storage.smartctl_summary import SmartctlSummary

from .. import utils


class TestSmartctlSummary(utils.BaseTestCase):
    """Unit tests for SmartctlSummary plugin."""
    def setUp(self):
        super().setUp()
        HotSOSConfig.plugin_name = 'storage'
        self.plugin = SmartctlSummary()

    def test_no_smartctl_output(self):
        # pylint: disable=protected-access
        self.plugin._search_sosreport = lambda directory: {}
        result = self.plugin.disk_health()
        self.assertIsNone(result)

    def test_failed_disk(self):
        fake_content = {
            'sos_commands/smartctl/smartctl_-a_sda': (
                'SMART overall-health self-assessment test result: FAILED'
            ),
            'sos_commands/smartctl/smartctl_-a_sdb': (
                'SMART overall-health self-assessment test result: PASSED'
            ),
        }
        # pylint: disable=protected-access
        self.plugin._search_sosreport = lambda directory: fake_content
        result = self.plugin.disk_health()
        self.assertIn('abnormal_disks', result)
        self.assertIn(
            'sos_commands/smartctl/smartctl_-a_sda',
            result['abnormal_disks']
        )
        self.assertEqual(
            result['abnormal_disks']['sos_commands/smartctl/smartctl_-a_sda'][
                'health_status'
            ],
            'FAILED'
        )
        self.assertIn('message', result)
        self.assertEqual(
            result['message'],
            (
                'Some disks reported SMART health failures or abnormal error '
                'counters.'
            )
        )

    def test_failed_and_abnormal_counters(self):
        fake_content = {
            'sos_commands/smartctl/smartctl_-a_sda': (
                'SMART overall-health self-assessment test result: FAILED\n'
                'ID# ATTRIBUTE_NAME FLAG VALUE WORST THRESH TYPE UPDATED '
                'WHEN_FAILED RAW_VALUE\n'
                '  5 Reallocated_Sector_Ct 0x0033 100 100 036 Pre-fail '
                'Always - 3\n'
                '197 Current_Pending_Sector 0x0012 100 100 000 Old_age '
                'Always - 2\n'
            ),
        }
        # pylint: disable=protected-access
        self.plugin._search_sosreport = lambda directory: fake_content
        result = self.plugin.disk_health()
        self.assertIn('abnormal_disks', result)
        disk = result['abnormal_disks'][
            'sos_commands/smartctl/smartctl_-a_sda'
        ]
        self.assertEqual(disk['health_status'], 'FAILED')
        self.assertEqual(disk['Reallocated_Sector_Ct'], 3)
        self.assertEqual(disk['Current_Pending_Sector'], 2)
        self.assertIn('message', result)
        self.assertEqual(
            result['message'],
            (
                'Some disks reported SMART health failures or abnormal error '
                'counters.'
            )
        )

    def test_zero_error_counters(self):
        fake_content = {
            'sos_commands/smartctl/smartctl_-a_sda': (
                'SMART overall-health self-assessment test result: PASSED\n'
                'ID# ATTRIBUTE_NAME FLAG VALUE WORST THRESH TYPE UPDATED '
                'WHEN_FAILED RAW_VALUE\n'
                '  5 Reallocated_Sector_Ct 0x0033 100 100 036 Pre-fail '
                'Always - 0\n'
                '197 Current_Pending_Sector 0x0012 100 100 000 Old_age '
                'Always - 0\n'
            ),
        }
        # pylint: disable=protected-access
        self.plugin._search_sosreport = lambda directory: fake_content
        result = self.plugin.disk_health()
        self.assertNotIn('abnormal_disks', result)
        self.assertIn('message', result)
        self.assertEqual(
            result['message'],
            (
                'No SMART health failures or abnormal error counters '
                'detected.'
            )
        )

    def test_abnormal_error_counters(self):
        fake_content = {
            'sos_commands/smartctl/smartctl_-a_sda': (
                'ID# ATTRIBUTE_NAME          FLAG     VALUE WORST THRESH TYPE '
                'UPDATED  WHEN_FAILED RAW_VALUE\n'
                '  5 Reallocated_Sector_Ct   0x0033   100   100   036    '
                'Pre-fail  Always       -       2\n'
                '197 Current_Pending_Sector  0x0012   100   100   000    '
                'Old_age   Always       -       1\n'
            ),
        }
        # pylint: disable=protected-access
        self.plugin._search_sosreport = lambda directory: fake_content
        result = self.plugin.disk_health()
        self.assertIn('abnormal_disks', result)
        disk = result['abnormal_disks'][
            'sos_commands/smartctl/smartctl_-a_sda'
        ]
        self.assertEqual(disk['Reallocated_Sector_Ct'], 2)
        self.assertEqual(disk['Current_Pending_Sector'], 1)
        self.assertIn('message', result)
        self.assertEqual(
            result['message'],
            (
                'Some disks reported SMART health failures or abnormal error '
                'counters.'
            )
        )

    def test_all_disks_passed(self):
        fake_content = {
            'sos_commands/smartctl/smartctl_-a_sda': (
                'SMART overall-health self-assessment test result: PASSED'
            ),
        }
        # pylint: disable=protected-access
        self.plugin._search_sosreport = lambda directory: fake_content
        result = self.plugin.disk_health()
        self.assertIn('message', result)
        self.assertEqual(
            result['message'],
            (
                'No SMART health failures or abnormal error counters '
                'detected.'
            )
        )
