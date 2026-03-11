from hotsos.core.config import HotSOSConfig
from hotsos.plugin_extensions.storage.smartctl_summary import SmartctlSummary

from .. import utils


SMARTCTL_OUT1 = """
SMART overall-health self-assessment test result: PASSED
ID# ATTRIBUTE_NAME FLAG VALUE WORST THRESH TYPE UPDATED WHEN_FAILED RAW_VALUE
  5 Reallocated_Sector_Ct 0x0033 100 100 036 Pre-fail Always - 0
197 Current_Pending_Sector 0x0012 100 100 000 Old_age Always - 0
"""  # noqa

SMARTCTL_OUT2 = """
SMART overall-health self-assessment test result: FAILED
ID# ATTRIBUTE_NAME FLAG VALUE WORST THRESH TYPE UPDATED WHEN_FAILED RAW_VALUE
  5 Reallocated_Sector_Ct 0x0033 100 100 036 Pre-fail Always - 3
197 Current_Pending_Sector 0x0012 100 100 000 Old_age Always - 2
"""  # noqa

SMARTCTL_OUT3 = """
ID# ATTRIBUTE_NAME          FLAG     VALUE WORST THRESH TYPE UPDATED  WHEN_FAILED RAW_VALUE
  5 Reallocated_Sector_Ct   0x0033   100   100   036 Pre-fail Always - 2
197 Current_Pending_Sector  0x0012   100   100   000 Old_age Always - 1
"""  # noqa


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

    @utils.create_data_root({'sos_commands/ata/smartctl_-a_vda':
                             ('SMART overall-health self-assessment test '
                              'result: FAILED'),
                             'sos_commands/ata/smartctl_-a_vdb':
                             ('SMART overall-health self-assessment test '
                              'result: PASSED')},
                            copy_from_original=[
                                'sos_commands/block/ls_-lanR_.sys.block'])
    def test_failed_disk(self):
        result = self.plugin.smartctl_summary()
        self.assertIn('unhealthy-disks', result)
        self.assertIn('vda', result['unhealthy-disks'])
        self.assertEqual(result['unhealthy-disks']['vda']['health_status'],
                         'FAILED')

    @utils.create_data_root({'sos_commands/ata/smartctl_-a_vda':
                             SMARTCTL_OUT2},
                            copy_from_original=[
                                'sos_commands/block/ls_-lanR_.sys.block'])
    def test_failed_and_abnormal_counters(self):
        result = self.plugin.smartctl_summary()
        self.assertIn('unhealthy-disks', result)
        disk = result['unhealthy-disks']['vda']
        self.assertEqual(disk['health_status'], 'FAILED')
        # Current_Pending_Sector is a failure counter
        self.assertEqual(disk['failure_counters']['Current_Pending_Sector'], 2)
        # Reallocated_Sector_Ct is an info counter
        self.assertEqual(disk['info_counters']['Reallocated_Sector_Ct'], 3)

    @utils.create_data_root({'sos_commands/ata/smartctl_-a_vda':
                             SMARTCTL_OUT1},
                            copy_from_original=[
                                'sos_commands/block/ls_-lanR_.sys.block'])
    def test_zero_error_counters(self):
        result = self.plugin.smartctl_summary()
        self.assertNotIn('unhealthy-disks', result)

    @utils.create_data_root({'sos_commands/ata/smartctl_-a_vda':
                             SMARTCTL_OUT3},
                            copy_from_original=[
                                'sos_commands/block/ls_-lanR_.sys.block'])
    def test_abnormal_error_counters(self):
        result = self.plugin.smartctl_summary()
        self.assertIn('unhealthy-disks', result)
        disk = result['unhealthy-disks']['vda']
        # Reallocated_Sector_Ct is an info counter
        self.assertEqual(disk['info_counters']['Reallocated_Sector_Ct'], 2)
        # Current_Pending_Sector is a failure counter
        self.assertEqual(disk['failure_counters']['Current_Pending_Sector'], 1)

    @utils.create_data_root({'sos_commands/ata/smartctl_-a_vda':
                             ('SMART overall-health self-assessment test '
                              'result: PASSED')},
                            copy_from_original=[
                                'sos_commands/block/ls_-lanR_.sys.block'])
    def test_all_disks_passed(self):
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
