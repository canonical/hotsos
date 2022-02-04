import os
import tempfile

from tests.unit import utils

from plugins.sosreport.pyparts import (
    general,
    plugin_checks,
)


class TestSOSReportGeneral(utils.BaseTestCase):

    def test_version(self):
        inst = general.SOSReportInfo()
        inst()
        expected = {'version': '4.1',
                    'dpkg': ['sosreport 4.1-1ubuntu0.20.04.3']}
        self.assertEqual(inst.output, expected)


class TestSOSReportPluginChecks(utils.BaseTestCase):

    def test_check_plugin_timouts_none(self):
        inst = plugin_checks.SOSReportPluginChecks()
        inst()
        self.assertIsNone(inst.output)

    def test_check_plugin_timouts_some(self):
        with tempfile.TemporaryDirectory() as dtmp:
            os.environ["DATA_ROOT"] = dtmp
            os.makedirs(os.path.join(dtmp, "sos_logs"))
            with open(os.path.join(dtmp, "sos_logs", 'ui.log'), 'w') as fd:
                fd.write(" Plugin networking timed out\n")

            inst = plugin_checks.SOSReportPluginChecks()
            inst()
            self.assertEquals(inst.output, {"plugin-timeouts": ["networking"]})
