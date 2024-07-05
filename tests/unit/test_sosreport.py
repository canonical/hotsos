from hotsos.core.config import HotSOSConfig
import hotsos.core.plugins.sosreport as sosreport_core
from hotsos.plugin_extensions.sosreport import summary

from . import utils


class TestSOSReportBase(utils.BaseTestCase):
    """ Custom base testcase that sets sosreport plugin context. """
    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        HotSOSConfig.plugin_name = 'sosreport'


class TestSOSReportCore(TestSOSReportBase):
    """ Unit tests for sosreport plugin core code. """
    @utils.create_data_root({'sos_logs/ui.log':
                             (" Plugin networking timed out\n"
                              " Plugin system timed out\n")})
    def test_plugin_timouts_some(self):
        c = sosreport_core.SOSReportChecks()
        self.assertEqual(c.timed_out_plugins, ['networking', 'system'])


class TestSOSReportSummary(TestSOSReportBase):
    """ Unit tests for sosreport summary. """
    def test_version(self):
        inst = summary.SOSReportSummary()
        expected = {'version': '4.2',
                    'dpkg': ['sosreport 4.2-1ubuntu0.20.04.1']}
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual, expected)

    def test_check_plugin_timouts_none(self):
        inst = summary.SOSReportSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertNotIn('plugin-timeouts', actual)

    @utils.create_data_root({'sos_logs/ui.log':
                             (" Plugin networking timed out\n"
                              " Plugin system timed out\n")})
    def test_check_plugin_timouts_some(self):
        inst = summary.SOSReportSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual['plugin-timeouts'],
                         ['networking', 'system'])


@utils.load_templated_tests('scenarios/sosreport')
class TestSOSReportScenarios(TestSOSReportBase):
    """
    Scenario tests can be written using YAML templates that are auto-loaded
    into this test runner. This is the recommended way to write tests for
    scenarios. It is however still possible to write the tests in Python if
    required. See https://hotsos.readthedocs.io/en/latest/contrib/testing.html
    for more information.
    """
