import os

import tempfile

import utils

utils.add_sys_plugin_path("sosreport")
from plugins.sosreport.parts.pyparts import (  # noqa E402
    plugin_checks,
)


class TestSOSReportPluginPartPluginChecks(utils.BaseTestCase):

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
