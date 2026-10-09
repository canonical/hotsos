import os
import json
import logging
import tempfile
from unittest import mock

from hotsos.client import OutputManager, OutputBuilder
from hotsos.core.host_helpers.cli import CLIHelper
from hotsos.core.issues import IssuesManager

from . import utils

# It is fine for a test to access a protected member so allow it for all tests.
# Also don't restrict number of tests we can have per test class.
# pylint: disable=protected-access,too-many-public-methods

ISSUES_LEGACY_FORMAT = {
    'testplugin': {
        IssuesManager.SUMMARY_OUT_ISSUES_ROOT: [{
             'type': 'MemoryWarning',
             'message': 'a msg'}],
        IssuesManager.SUMMARY_OUT_BUGS_ROOT: [{
             'id': '1234',
             'message': 'a msg'}]}}

ISSUES_NEW_FORMAT = {
    'testplugin': {
        IssuesManager.SUMMARY_OUT_ISSUES_ROOT: {
             'MemoryWarnings': ['a msg']},
        IssuesManager.SUMMARY_OUT_BUGS_ROOT: [{
             'id': '1234',
             'message': 'a msg'}]}}


class TestPluginTools(utils.BaseTestCase):
    """ Unit tests for plugintools code. """
    def test_summary_empty(self):
        """Test empty summary produces empty JSON."""
        filtered = OutputManager().get_builder().to(fmt="json")
        self.assertEqual(filtered, '{}')

    def test_summary_mode_short_legacy(self):
        """Test short mode minimisation of legacy format."""
        expected = {IssuesManager.SUMMARY_OUT_ISSUES_ROOT: {
                        'testplugin': [{
                            'type': 'MemoryWarning',
                            'message': 'a msg'}]},
                    IssuesManager.SUMMARY_OUT_BUGS_ROOT: {
                        'testplugin': [{
                            'id': '1234',
                            'message': 'a msg'}]}}

        filtered = OutputBuilder._minimise(ISSUES_LEGACY_FORMAT, mode='short')
        self.assertEqual(filtered, expected)

    def test_summary_mode_short(self):
        """Test short mode minimisation of new format."""
        expected = {IssuesManager.SUMMARY_OUT_ISSUES_ROOT: {
                        'testplugin': {
                            'MemoryWarnings': ['a msg']}},
                    IssuesManager.SUMMARY_OUT_BUGS_ROOT: {
                        'testplugin': [{
                            'id': '1234',
                            'message': 'a msg'}]}}
        filtered = OutputBuilder._minimise(ISSUES_NEW_FORMAT, mode='short')
        self.assertEqual(filtered, expected)

    def test_summary_mode_very_short_legacy(self):
        """Test very-short mode minimisation of legacy format."""
        expected = {IssuesManager.SUMMARY_OUT_ISSUES_ROOT: {
                        'testplugin': {
                            'MemoryWarning': 1}},
                    IssuesManager.SUMMARY_OUT_BUGS_ROOT: {
                        'testplugin': ['1234']}}
        filtered = OutputBuilder._minimise(ISSUES_LEGACY_FORMAT,
                                           mode='very-short')
        self.assertEqual(filtered, expected)

    def test_summary_mode_very_short(self):
        """Test very-short mode minimisation of new format."""
        expected = {IssuesManager.SUMMARY_OUT_ISSUES_ROOT: {
                        'testplugin': {
                            'MemoryWarnings': 1}},
                    IssuesManager.SUMMARY_OUT_BUGS_ROOT: {
                        'testplugin': ['1234']}}

        filtered = OutputBuilder._minimise(ISSUES_NEW_FORMAT,
                                           mode='very-short')
        self.assertEqual(filtered, expected)

    def test_apply_output_formatting_json(self):
        """Test JSON output formatting."""
        summary = {'opt': 'value'}
        filtered = OutputManager(summary).get_builder().to("json")
        self.assertEqual(filtered, json.dumps(summary, indent=2,
                                              sort_keys=True))

    def test_apply_output_formatting_markdown(self):
        """Test markdown output formatting."""
        summary = {
            'item-1':
                {
                    'level-2': [
                        'value-1',
                        'value-2',
                        'value-3',
                        'value-4',
                    ],
                    'level-3': 'plain value',
                },
            'item-2':
                ['a', 'b', 'c'],
        }
        expected = '''# hotsos summary

## item-1

### level-2

- value-1
- value-2
- value-3
- value-4

### level-3

plain value

## item-2

- a
- b
- c'''
        filtered = OutputManager(summary).get_builder().to(fmt="markdown")
        self.assertEqual(filtered, expected)

    def test_apply_output_formatting_html_1(self):
        """Test HTML output formatting variant 1."""
        summary = {
            'item-1':
                {
                    'level-2': [
                        'value-1',
                        'value-2',
                        'value-3',
                        'value-4',
                    ],
                    'level-3': 'plain value',
                },
            'item-2':
                ['a', 'b', 'c'],
        }
        filtered = OutputManager(summary).get_builder().to(fmt="html")
        self.assertIn('vanilla-framework-version-', filtered)
        self.assertIn('p-side-navigation', filtered)
        self.assertIn('id="item-1"', filtered)
        self.assertIn('id="item-2"', filtered)
        self.assertIn('value-4', filtered)

    def test_apply_output_formatting_html_2(self):
        """Test HTML output formatting variant 2."""
        summary = {
            'item-1':
                {
                    'level-2': [
                        'value-1',
                        'value-2',
                        'value-3',
                        'value-4',
                    ],
                    'level-3': 'plain value',
                },
            'item-2':
                ['a', 'b', 'c'],
        }
        filtered = OutputManager(summary).get_builder().to(fmt="html")
        self.assertIn('Known issues/bugs', filtered)

    def test_apply_output_formatting_html_3(self):
        """Test HTML output formatting variant 3."""
        summary = {
            'system':
                {
                    'hostname': 'compute4',
                    'level-2': [
                        'value-1',
                        'value-2',
                        'value-3',
                        'value-4',
                    ],
                    'level-3': 'plain value',
                },
            'item-2':
                ['a', 'b', 'c'],
        }
        filtered = OutputManager(summary).get_builder().to(fmt="html")
        self.assertIn(f'Host: <strong>{CLIHelper().hostname()}</strong>',
                      filtered)
        self.assertIn('Generated ', filtered)

    def test_apply_output_formatting_html_barchart(self):
        """A category distribution of counts is rendered as a bar chart."""
        summary = {
            'storage':
                {
                    'lock-durations':
                        {
                            '61': 1,
                            '22': 1,
                            '3': 1,
                            '2': 2,
                        },
                },
        }
        filtered = OutputManager(summary).get_builder().to(fmt="html")
        self.assertIn('class="hs-chart__bars', filtered)
        self.assertIn('hs-chart__bar-row', filtered)
        # Each bar exposes its label and value.
        self.assertIn('title="2: 2"', filtered)

    def test_apply_output_formatting_html_stackplot_timestamps(self):
        """Timestamped {label: count} data is rendered as a stackplot."""
        summary = {
            'storage':
                {
                    'ovsdb-monitor-router-binding-transitions':
                        {
                            '2023-03-28': {'hostA': 5, 'hostB': 3},
                            '2023-03-29': {'hostA': 2},
                            '2023-03-30': {'hostA': 1, 'hostC': 4},
                        },
                },
        }
        filtered = OutputManager(summary).get_builder().to(fmt="html")
        self.assertIn('class="hs-chart hs-chart--stack', filtered)
        self.assertIn('<polygon', filtered)
        # Multiple series are stacked, not drawn as a single line chart.
        self.assertNotIn('hs-chart hs-chart--stack hs-chart--line', filtered)
        # Each series is selectable from the legend to isolate it, with a
        # standalone (unstacked) line drawn for the isolated series.
        self.assertIn('hs-chart__legend-btn', filtered)
        self.assertIn('data-series="0"', filtered)
        self.assertIn('class="hs-chart__isolate"', filtered)
        # hostA's series total is shown in the legend (5 + 2 + 1 = 8).
        self.assertIn('title="hostA: 8"', filtered)
        # The timestamp axis is preserved rather than aggregated away.
        self.assertIn('2023-03-28', filtered)
        self.assertIn('2023-03-30', filtered)
        # The chart has a value (y) axis with the peak at the top and 0 below.
        self.assertIn('hs-chart__yaxis', filtered)
        self.assertIn('hs-chart__ytick', filtered)
        # Not rendered as a bar chart.
        self.assertNotIn('class="hs-chart__bars', filtered)

    def test_apply_output_formatting_html_single_series_line(self):
        """A lone scalar time series is drawn as a single line, not stacked."""
        summary = {
            'openvswitch':
                {
                    'per-port-day-total':
                        {
                            '2026-01-01': 20054,
                            '2026-01-02': 105367,
                            '2026-01-03': 112029,
                        },
                },
        }
        filtered = OutputManager(summary).get_builder().to(fmt="html")
        # A single series is a line chart rather than a filled stacked area.
        self.assertIn('hs-chart--line', filtered)
        self.assertIn('<polyline', filtered)
        # The filled stacked-area polygon style is not used for a single line.
        self.assertNotIn('fill-opacity="0.85"', filtered)
        self.assertNotIn('class="hs-chart__bars', filtered)

    def test_apply_output_formatting_html_stackplot_ovn_revision_bump(self):
        """A single-timestamp breakdown is graphed as a bar chart."""
        summary = {
            'openstack':
                {
                    'ovn-resource-revision-bump':
                        {
                            '2023-12-09':
                                {
                                    'res-a': 2,
                                    'res-b': 2,
                                    'res-c': 2,
                                },
                        },
                },
        }
        filtered = OutputManager(summary).get_builder().to(fmt="html")
        # A single date/time cannot form a stackplot, so its {label: count}
        # breakdown is graphed as a bar chart (one bar per label) instead.
        self.assertNotIn('class="hs-chart hs-chart--stack', filtered)
        self.assertNotIn('<polygon', filtered)
        self.assertIn('class="hs-chart__bars', filtered)
        self.assertIn('title="res-a: 2"', filtered)

    def test_apply_output_formatting_html_barchart_widths(self):
        """Bar widths are scaled relative to the largest value."""
        summary = {
            'storage':
                {
                    'warnings':
                        {
                            'WARN': 5,
                            'ERR': 1,
                        },
                },
        }
        filtered = OutputManager(summary).get_builder().to(fmt="html")
        self.assertIn('class="hs-chart__bars', filtered)
        # The largest value fills the track, smaller values are proportional.
        self.assertIn('width: 100.0%', filtered)
        self.assertIn('width: 20.0%', filtered)

    def test_apply_output_formatting_html_stats_not_barchart(self):
        """A statistics mapping must not be rendered as a bar chart."""
        summary = {
            'storage':
                {
                    'stats':
                        {
                            'min': 1,
                            'max': 5,
                            'avg': 3,
                            'samples': 10,
                        },
                },
        }
        filtered = OutputManager(summary).get_builder().to(fmt="html")
        self.assertNotIn('class="hs-chart__bars', filtered)

    def test_apply_output_formatting_html_single_date_scalar_barchart(self):
        """A single date/time scalar value is graphed as a bar chart."""
        summary = {
            'storage':
                {
                    'lock-durations':
                        {
                            '2022-02-10': 12,
                        },
                    'notes': 'ok',
                },
        }
        filtered = OutputManager(summary).get_builder().to(fmt="html")
        self.assertIn('class="hs-chart__bars', filtered)
        # The date is the bar label and the scalar is its value.
        self.assertIn('title="2022-02-10: 12"', filtered)
        # A single date/time is not drawn as a stackplot.
        self.assertNotIn('class="hs-chart hs-chart--stack', filtered)

    def test_apply_output_formatting_html_piechart(self):
        """Distributions under http-requests are rendered as pie charts."""
        summary = {
            'openstack':
                {
                    'api-info':
                        {
                            'http-requests':
                                {
                                    'nova':
                                        {
                                            '2022-02-10':
                                                {
                                                    '200': 3,
                                                    '404': 1,
                                                },
                                        },
                                },
                        },
                },
        }
        filtered = OutputManager(summary).get_builder().to(fmt="html")
        self.assertIn('class="hs-chart hs-chart--pie', filtered)
        self.assertIn('conic-gradient(', filtered)
        # Pie slices are not rendered as bars.
        self.assertNotIn('class="hs-chart__bars', filtered)
        # Each slice exposes its label and value.
        self.assertIn('title="200: 3"', filtered)

    def test_apply_output_formatting_html_piechart_http_status(self):
        """Distributions under http-status are rendered as pie charts."""
        summary = {
            'openstack':
                {
                    'api-info':
                        {
                            'http-status':
                                {
                                    'nova':
                                        {
                                            '2022-02-10':
                                                {
                                                    '200 (OK)': 4,
                                                    '500 (ERROR)': 1,
                                                },
                                        },
                                },
                        },
                },
        }
        filtered = OutputManager(summary).get_builder().to(fmt="html")
        self.assertIn('class="hs-chart hs-chart--pie', filtered)
        self.assertNotIn('class="hs-chart__bars', filtered)

    def test_apply_output_formatting_html_timeseries_defaults_to_stackplot(
            self):
        """Timestamp-keyed distributions are rendered as stackplots."""
        summary = {
            'openstack':
                {
                    'some-other-info':
                        {
                            '2022-02-10': 3,
                            '2022-02-11': 1,
                        },
                },
        }
        filtered = OutputManager(summary).get_builder().to(fmt="html")
        self.assertIn('class="hs-chart hs-chart--stack', filtered)
        self.assertNotIn('class="hs-chart__bars', filtered)
        self.assertNotIn('class="hs-chart hs-chart--pie', filtered)

    def test_apply_output_formatting_html_label_keyed_timeseries(self):
        """Label-keyed time series (e.g. WARN/ERR) graph as one chart."""
        summary = {
            'openvswitch':
                {
                    'ovsdb-server-sb':
                        {
                            'WARN': {'2022-02-17': 10, '2022-02-18': 13},
                            'ERR': {'2022-02-17': 2},
                        },
                },
        }
        filtered = OutputManager(summary).get_builder().to(fmt="html")
        # Both labels are consolidated into a single time series chart.
        self.assertIn('class="hs-chart hs-chart--stack', filtered)
        self.assertIn('title="WARN: 23"', filtered)
        self.assertIn('title="ERR: 2"', filtered)

    def test_apply_output_formatting_html_errors_warnings_multi_day(self):
        """A nested WARN/ERR daily series graphs as a stacked plot."""
        summary = {
            'openvswitch':
                {
                    'ovn-checks':
                        {
                            'errors-and-warnings':
                                {
                                    'ovn-controller':
                                        {
                                            'WARN': {
                                                '2026-01-01': 108,
                                                '2026-01-02': 703,
                                                '2026-01-03': 1128,
                                                '2026-01-04': 1383,
                                            },
                                            'ERR': {
                                                '2026-01-01': 8,
                                                '2026-01-02': 56,
                                                '2026-01-03': 86,
                                                '2026-01-04': 109,
                                            },
                                        },
                                },
                        },
                },
        }
        filtered = OutputManager(summary).get_builder().to(fmt="html")
        # WARN and ERR are consolidated into one stacked time series chart.
        self.assertIn('class="hs-chart hs-chart--stack', filtered)
        self.assertIn('<polygon', filtered)
        self.assertNotIn('hs-chart hs-chart--stack hs-chart--line', filtered)
        self.assertIn('title="WARN: 3322"', filtered)
        self.assertIn('title="ERR: 259"', filtered)

    def test_apply_output_formatting_html_topn_daily_totals(self):
        """A per-date top-N result plots daily totals and keeps the detail."""
        summary = {
            'openvswitch':
                {
                    'bridge-no-such-device':
                        {
                            '2026-01-03': {
                                'total': 83,
                                'top5': {'tapc97b0af4-f0': 2,
                                         'tap7524580f-37': 2},
                            },
                            '2026-01-05': {
                                'total': 142,
                                'top5': {'tapc97b0af4-f0': 3,
                                         'tap7524580f-37': 3},
                            },
                        },
                },
        }
        filtered = OutputManager(summary).get_builder().to(fmt="html")
        # The daily totals are plotted as a single line time series.
        self.assertIn('hs-chart--line', filtered)
        self.assertIn('<polyline', filtered)
        # The top-N breakdown is still shown as detail below the chart.
        self.assertIn('tapc97b0af4-f0', filtered)

    def test_apply_output_formatting_html_topn_daily_totals_mixed(self):
        """Daily totals plot when only some dates exceed the display limit."""
        summary = {
            'openvswitch':
                {
                    'bridge-no-such-device':
                        {
                            # A quiet date left as an ordinary label/count
                            # mapping (two distinct entries).
                            '2026-01-03': {'tapc97b0af4-f0': 2,
                                           'tap7524580f-37': 2},
                            # A busy date shortened to a top-N result.
                            '2026-01-05': {
                                'total': 142,
                                'top5': {'tapc97b0af4-f0': 3,
                                         'tap7524580f-37': 3},
                            },
                        },
                },
        }
        filtered = OutputManager(summary).get_builder().to(fmt="html")
        # The daily totals are plotted as a single line time series even
        # though only one date is shortened.
        self.assertIn('hs-chart--line', filtered)
        self.assertIn('<polyline', filtered)
        # The detail below the chart is retained for both dates.
        self.assertIn('tapc97b0af4-f0', filtered)

    def test_apply_output_formatting_html_single_label_keyed_timeseries(self):
        """A single-label time series (e.g. only WARN) is still graphed."""
        summary = {
            'openvswitch':
                {
                    'ovn-controller':
                        {
                            'WARN': {'2022-02-17': 5},
                        },
                },
        }
        filtered = OutputManager(summary).get_builder().to(fmt="html")
        # A single date/time with one label is graphed as a bar chart.
        self.assertIn('class="hs-chart__bars', filtered)
        self.assertIn('title="WARN: 5"', filtered)

    def test_apply_output_formatting_html_findings_grouped_by_plugin(self):
        """Detected issues and bugs are grouped by plugin at the top."""
        summary = {
            'openstack':
                {
                    'potential-issues':
                        {'MemoryWarning': ['openstack issue message']},
                },
            'storage':
                {
                    'bugs-detected':
                        {'https://bugs.example/1': 'storage bug message'},
                },
        }
        filtered = OutputManager(summary).get_builder().to(fmt="html")
        # Findings are grouped, with one group header per plugin.
        self.assertIn('class="hs-finding-group"', filtered)
        self.assertIn('hs-finding-group__name">storage<', filtered)
        self.assertIn('hs-finding-group__name">openstack<', filtered)
        # The per-finding plugin label is replaced by the group header.
        self.assertNotIn('hs-finding__plugin', filtered)
        # The highest severity plugin group (bug) is listed first.
        self.assertLess(filtered.index('hs-finding-group__name">storage<'),
                        filtered.index('hs-finding-group__name">openstack<'))
        self.assertIn('openstack issue message', filtered)
        self.assertIn('storage bug message', filtered)

    def test_apply_output_formatting_html_findings_clustered_by_type(self):
        """Findings of the same type are clustered under one category."""
        summary = {
            'openstack':
                {
                    'potential-issues':
                        {'MemoryWarning': ['first message', 'second message']},
                },
        }
        filtered = OutputManager(summary).get_builder().to(fmt="html")
        # The repeated issue type is shown once as a grouped cluster.
        self.assertIn('hs-finding--grouped', filtered)
        # The issue type is not repeated per message within the cluster.
        findings = filtered.split('id="hs-findings-list"', 1)[1]
        findings = findings.split('id="hs-plugins"', 1)[0]
        self.assertEqual(findings.count('MemoryWarning'), 1)
        # An occurrence count badge is shown for the cluster.
        self.assertIn('hs-finding__count', filtered)
        self.assertIn('&times;2', filtered)
        # Both messages are listed within the cluster.
        self.assertIn('first message', filtered)
        self.assertIn('second message', filtered)

    def test_apply_output_formatting_html_findings_single_not_clustered(self):
        """A single finding per type is rendered inline, not as a cluster."""
        summary = {
            'openstack':
                {
                    'potential-issues':
                        {'MemoryWarning': ['only message']},
                },
        }
        filtered = OutputManager(summary).get_builder().to(fmt="html")
        self.assertNotIn('hs-finding--grouped', filtered)
        self.assertIn('hs-finding__category--inline', filtered)
        self.assertIn('only message', filtered)


class TestOutputManagerLogile(utils.BaseTestCase):
    """
    Tests for OutputManager log file handling.
    """

    def test_compressed_logfile(self):
        """Test log file compression in output directory."""
        with tempfile.NamedTemporaryFile(delete=False) as ftmp:
            with mock.patch('hotsos.client.log.handlers',
                            [logging.FileHandler(ftmp.name)]):
                summary = {'opt': 'value'}
                with tempfile.TemporaryDirectory() as dtmp:
                    path = OutputManager(summary).save('testplugin',
                                                       output_path=dtmp)
                    self.assertEqual(path, dtmp)
                    logpath = os.path.join(dtmp, 'testplugin', 'hotsos.log.gz')
                    self.assertTrue(os.path.exists(logpath))

            # Will have been deleted by compress()
            self.assertFalse(os.path.exists(ftmp.name))
