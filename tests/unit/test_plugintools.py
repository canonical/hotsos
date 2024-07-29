import json

from hotsos.client import OutputManager, OutputBuilder
from hotsos.core.host_helpers.cli import CLIHelper
from hotsos.core.issues import IssuesManager
from hotsos.core import plugintools

from . import utils

# It is fine for a test to access a protected member so allow it for all tests
# pylint: disable=protected-access

HTML1 = """<ul class="tree">
<li>
<details>
<summary>item-1</summary>
<ul >
<li>
<b>level-2</b>

<ul>
<li>
value-1
</li><li>
value-2
</li><li>
value-3
</li><li>
value-4
</li>
</ul>
</li>
<li>
<b>level-3</b>
plain value
</li>
</ul>
</details>
</li>
<li>
<details>
<summary>item-2</summary>

<ul>
<li>
a
</li><li>
b
</li><li>
c
</li>
</ul>
</details>
</li>
</ul>"""

HTML2 = """<ul class="tree">
<li>
<details>
<summary>item-1</summary>
<ul >
<li>
<b>level-2</b>

<ul>
<li>
value-1
</li><li>
value-2
</li><li>
value-3
</li><li>
value-4
</li>
</ul>
</li>
<li>
<b>level-3</b>
plain value
</li>
</ul>
</details>
</li>
<li>
<details>
<summary>item-2</summary>

<ul>
<li>
a
</li><li>
b
</li><li>
c
</li>
</ul>
</details>
</li>
</ul>"""

HTML3 = """<ul class="tree">
<li>
<details>
<summary>item-1</summary>
<ul >
<li>
<b>level-2</b>

<ul>
<li>
value-1
</li><li>
value-2
</li><li>
value-3
</li><li>
value-4
</li>
</ul>
</li>
<li>
<b>level-3</b>
plain value
</li>
</ul>
</details>
</li>
<li>
<details>
<summary>item-2</summary>

<ul>
<li>
a
</li><li>
b
</li><li>
c
</li>
</ul>
</details>
</li>
</ul>"""


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
        filtered = OutputManager().get_builder().to(fmt="json")
        self.assertEqual(filtered, '{}')

    def test_summary_mode_short_legacy(self):
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
        expected = {IssuesManager.SUMMARY_OUT_ISSUES_ROOT: {
                        'testplugin': {
                            'MemoryWarning': 1}},
                    IssuesManager.SUMMARY_OUT_BUGS_ROOT: {
                        'testplugin': ['1234']}}
        filtered = OutputBuilder._minimise(ISSUES_LEGACY_FORMAT,
                                           mode='very-short')
        self.assertEqual(filtered, expected)

    def test_summary_mode_very_short(self):
        expected = {IssuesManager.SUMMARY_OUT_ISSUES_ROOT: {
                        'testplugin': {
                            'MemoryWarnings': 1}},
                    IssuesManager.SUMMARY_OUT_BUGS_ROOT: {
                        'testplugin': ['1234']}}

        filtered = OutputBuilder._minimise(ISSUES_NEW_FORMAT,
                                           mode='very-short')
        self.assertEqual(filtered, expected)

    def test_apply_output_formatting_json(self):
        summary = {'opt': 'value'}
        filtered = OutputManager(summary).get_builder().to("json")
        self.assertEqual(filtered, json.dumps(summary, indent=2,
                                              sort_keys=True))

    def test_apply_output_formatting_markdown(self):
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
        htmlout = plugintools.HTMLFormatter(CLIHelper().hostname())
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
        expected = htmlout.header + HTML1 + htmlout.footer
        filtered = OutputManager(summary).get_builder().to(fmt="html")
        self.assertEqual(filtered, expected)

    def test_apply_output_formatting_html_2(self):
        htmlout = plugintools.HTMLFormatter(CLIHelper().hostname())
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
        expected = htmlout.header + HTML2 + htmlout.footer
        filtered = OutputManager(summary).get_builder().to(fmt="html")
        self.assertEqual(filtered, expected)

    def test_apply_output_formatting_html_3(self):
        htmlout = plugintools.HTMLFormatter(CLIHelper().hostname())
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
        expected = htmlout.header + HTML3 + htmlout.footer
        filtered = OutputManager(summary).get_builder().to(fmt="html")
        self.assertEqual(filtered, expected)
