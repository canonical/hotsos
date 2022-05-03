import os
import tempfile

from unittest import mock

from . import utils

from hotsos.core.issues.utils import IssuesStore
from hotsos.core.config import setup_config
import hotsos.core.plugins.sosreport as sosreport_core
from hotsos.core.ycheck.scenarios import YScenarioChecker
from hotsos.plugin_extensions.sosreport import summary
from hotsos.core.issues import SOSReportWarning


class TestSOSReportBase(utils.BaseTestCase):

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        setup_config(PLUGIN_NAME='sosreport')

    def setup_timed_out_plugins(self, dtmp):
        setup_config(DATA_ROOT=dtmp)
        os.makedirs(os.path.join(dtmp, "sos_logs"))
        with open(os.path.join(dtmp, "sos_logs", 'ui.log'), 'w') as fd:
            fd.write(" Plugin networking timed out\n")
            fd.write(" Plugin system timed out\n")


class TestSOSReportCore(TestSOSReportBase):

    def test_plugin_timouts_some(self):
        with tempfile.TemporaryDirectory() as dtmp:
            self.setup_timed_out_plugins(dtmp)
            c = sosreport_core.SOSReportChecksBase()
            self.assertEqual(c.timed_out_plugins, ['networking', 'system'])


class TestSOSReportGeneral(TestSOSReportBase):

    def test_version(self):
        inst = summary.SOSReportSummary()
        expected = {'version': '4.2',
                    'dpkg': ['sosreport 4.2-1ubuntu0.20.04.1']}
        actual = self.part_output_to_actual(inst.output)
        self.assertEqual(actual, expected)

    def test_check_plugin_timouts_none(self):
        inst = summary.SOSReportSummary()
        actual = self.part_output_to_actual(inst.output)
        self.assertFalse('plugin-timeouts' in actual)

    def test_check_plugin_timouts_some(self):
        with tempfile.TemporaryDirectory() as dtmp:
            self.setup_timed_out_plugins(dtmp)
            inst = summary.SOSReportSummary()
            actual = self.part_output_to_actual(inst.output)
            self.assertEqual(actual['plugin-timeouts'],
                             ['networking', 'system'])


class TestSOSReportScenarioChecks(TestSOSReportBase):

    @mock.patch('hotsos.core.issues.IssuesManager.add')
    def test_scenarios_none(self, mock_add_issue):
        YScenarioChecker()()
        self.assertFalse(mock_add_issue.called)

    @mock.patch('hotsos.core.ycheck.engine.YDefsLoader._is_def',
                new=utils.is_def_filter('plugin_timeouts.yaml'))
    def test_plugin_timeouts(self):
        with tempfile.TemporaryDirectory() as dtmp:
            self.setup_timed_out_plugins(dtmp)
            YScenarioChecker()()

        msg = ('The following sosreport plugins have have timed out and may '
               'have incomplete data: networking, system')
        issues = list(IssuesStore().load().values())[0]
        self.assertEqual([issue['type'] for issue in issues],
                         [SOSReportWarning('').name])
        self.assertEqual([issue['desc'] for issue in issues], [msg])
