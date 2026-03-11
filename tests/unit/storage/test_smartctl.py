from hotsos.core.config import HotSOSConfig
from hotsos.plugin_extensions.storage.smartctl_summary import SmartctlSummary

from .. import utils


class SmartctlTestsBase(utils.BaseTestCase):
    """ Custom test case that sets the storage plugin context. """
    def setUp(self):
        super().setUp()
        HotSOSConfig.plugin_name = 'storage'


class TestSmartctlSummary(SmartctlTestsBase):
    """Unit tests for SmartctlSummary plugin."""
    def setUp(self):
        super().setUp()
        HotSOSConfig.plugin_name = 'storage'
        self.plugin = SmartctlSummary()

    def test_no_smartctl_output(self):
        # pylint: disable=protected-access
        self.plugin._search_sosreport = lambda directory: {}
        result = self.plugin.smartctl_summary()
        self.assertEqual(result, {})

    def test_failed_disk(self):
        fake_content = {
            'sos_commands/ata/smartctl_-a_sda': (
                'SMART overall-health self-assessment test result: FAILED'
            ),
            'sos_commands/ata/smartctl_-a_sdb': (
                'SMART overall-health self-assessment test result: PASSED'
            ),
        }
        # pylint: disable=protected-access
        self.plugin._search_sosreport = lambda directory: fake_content
        result = self.plugin.smartctl_summary()
        self.assertIn('unhealthy-disks', result)
        self.assertIn(
            'sos_commands/ata/smartctl_-a_sda',
            result['unhealthy-disks']
        )
        self.assertEqual(
            result['unhealthy-disks']['sos_commands/ata/smartctl_-a_sda'][
                'health_status'
            ],
            'FAILED'
        )

    def test_failed_and_abnormal_counters(self):
        fake_content = {
            'sos_commands/ata/smartctl_-a_sda': (
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
        result = self.plugin.smartctl_summary()
        self.assertIn('unhealthy-disks', result)
        disk = result['unhealthy-disks'][
            'sos_commands/ata/smartctl_-a_sda'
        ]
        self.assertEqual(disk['health_status'], 'FAILED')
        # Current_Pending_Sector is a failure counter
        self.assertEqual(disk['failure_counters']['Current_Pending_Sector'], 2)
        # Reallocated_Sector_Ct is an info counter
        self.assertEqual(disk['info_counters']['Reallocated_Sector_Ct'], 3)

    def test_zero_error_counters(self):
        fake_content = {
            'sos_commands/ata/smartctl_-a_sda': (
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
        result = self.plugin.smartctl_summary()
        self.assertNotIn('unhealthy-disks', result)

    def test_abnormal_error_counters(self):
        fake_content = {
            'sos_commands/ata/smartctl_-a_sda': (
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
        result = self.plugin.smartctl_summary()
        self.assertIn('unhealthy-disks', result)
        disk = result['unhealthy-disks'][
            'sos_commands/ata/smartctl_-a_sda'
        ]
        # Reallocated_Sector_Ct is an info counter
        self.assertEqual(disk['info_counters']['Reallocated_Sector_Ct'], 2)
        # Current_Pending_Sector is a failure counter
        self.assertEqual(disk['failure_counters']['Current_Pending_Sector'], 1)

    def test_all_disks_passed(self):
        fake_content = {
            'sos_commands/ata/smartctl_-a_sda': (
                'SMART overall-health self-assessment test result: PASSED'
            ),
        }
        # pylint: disable=protected-access
        self.plugin._search_sosreport = lambda directory: fake_content
        result = self.plugin.smartctl_summary()
        self.assertEqual(result, {})


@utils.load_templated_tests('scenarios/storage/smartctl')
class TestSmartCtlScenarios(SmartctlTestsBase):
    """
    Scenario tests can be written using YAML templates that are auto-loaded
    into this test runner. This is the recommended way to write tests for
    scenarios. It is however still possible to write the tests in Python if
    required. See https://hotsos.readthedocs.io/en/latest/contrib/testing.html
    for more information.
    """
