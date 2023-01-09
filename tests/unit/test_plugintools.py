import json

from . import utils

from hotsos.core import plugintools
from hotsos.client import OutputManager
from hotsos.core.issues import IssuesManager


ISSUES_LEGACY_FORMAT = {
    'testplugin': {
        IssuesManager.SUMMARY_OUT_ISSUES_ROOT: [{
             'type': 'MemoryWarning',
             'desc': 'a msg',
             'origin': 'testplugin.01part'}],
        IssuesManager.SUMMARY_OUT_BUGS_ROOT: [{
             'id': '1234',
             'desc': 'a msg',
             'origin': 'testplugin.01part'}]}}

ISSUES_NEW_FORMAT = {
    'testplugin': {
        IssuesManager.SUMMARY_OUT_ISSUES_ROOT: {
             'MemoryWarnings': [
                 'a msg (origin=testplugin.01part)']},
        IssuesManager.SUMMARY_OUT_BUGS_ROOT: [{
             'id': '1234',
             'desc': 'a msg',
             'origin': 'testplugin.01part'}]}}


class TestPluginTools(utils.BaseTestCase):

    def test_summary_empty(self):
        filtered = OutputManager().get()
        self.assertEqual(filtered, '{}')

    def test_summary_mode_short_legacy(self):
        expected = {IssuesManager.SUMMARY_OUT_ISSUES_ROOT: {
                        'testplugin': [{
                            'type': 'MemoryWarning',
                            'desc': 'a msg',
                            'origin':
                            'testplugin.01part'}]},
                    IssuesManager.SUMMARY_OUT_BUGS_ROOT: {
                        'testplugin': [{
                            'id': '1234',
                            'desc': 'a msg',
                            'origin': 'testplugin.01part'}]}}

        filtered = OutputManager().minimise(ISSUES_LEGACY_FORMAT,
                                            mode='short')
        self.assertEqual(filtered, expected)

    def test_summary_mode_short(self):
        expected = {IssuesManager.SUMMARY_OUT_ISSUES_ROOT: {
                        'testplugin': {
                            'MemoryWarnings': [
                                'a msg (origin=testplugin.01part)']}},
                    IssuesManager.SUMMARY_OUT_BUGS_ROOT: {
                        'testplugin': [{
                            'id': '1234',
                            'desc': 'a msg',
                            'origin': 'testplugin.01part'}]}}
        filtered = OutputManager().minimise(ISSUES_NEW_FORMAT, mode='short')
        self.assertEqual(filtered, expected)

    def test_summary_mode_very_short_legacy(self):
        expected = {IssuesManager.SUMMARY_OUT_ISSUES_ROOT: {
                        'testplugin': {
                            'MemoryWarning': 1}},
                    IssuesManager.SUMMARY_OUT_BUGS_ROOT: {
                        'testplugin': ['1234']}}
        filtered = OutputManager().minimise(ISSUES_LEGACY_FORMAT,
                                            mode='very-short')
        self.assertEqual(filtered, expected)

    def test_summary_mode_very_short(self):
        expected = {IssuesManager.SUMMARY_OUT_ISSUES_ROOT: {
                        'testplugin': {
                            'MemoryWarnings': 1}},
                    IssuesManager.SUMMARY_OUT_BUGS_ROOT: {
                        'testplugin': ['1234']}}

        filtered = OutputManager().minimise(ISSUES_NEW_FORMAT,
                                            mode='very-short')
        self.assertEqual(filtered, expected)

    def test_apply_output_formatting_defaults(self):
        summary = {'opt': 'value'}
        filtered = OutputManager(summary).get()
        self.assertEqual(filtered, plugintools.yaml_dump(summary))

    def test_apply_output_formatting_json(self):
        summary = {'opt': 'value'}
        filtered = OutputManager(summary).get(format='json')
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
        filtered = OutputManager(summary).get(format='markdown')
        self.assertEqual(filtered, expected)

    def test_apply_output_formatting_html_1(self):
        htmlout = plugintools.HTMLFormatter()
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
        content = '''    <ul class="tree">
        <li>
            <details>
                <summary>item-1</summary>
                <ul>
                    <li>
                        <details>
                            <summary>level-2</summary>
                            <ul>
                                <li>
                                    value-1
                                </li>
                                <li>
                                    value-2
                                </li>
                                <li>
                                    value-3
                                </li>
                                <li>
                                    value-4
                                </li>
                            </ul>
                        </details>
                    </li>
                    <li>
                        <details>
                            <summary>level-3</summary>
                            plain value
                        </details>
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
                    </li>
                    <li>
                        b
                    </li>
                    <li>
                        c
                    </li>
                </ul>
            </details>
        </li>
    </ul>
'''
        expected = htmlout.header + content + htmlout.footer
        filtered = OutputManager(summary).get(format='html', max_level=100)
        self.assertEqual(filtered, expected)

    def test_apply_output_formatting_html_2(self):
        htmlout = plugintools.HTMLFormatter()
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
        content = '''    <ul class="tree">
        <li>
            <b>item-1</b>
            <ul>
                <li>
                    <b>level-2</b>
                    <ul>
                        <li>
                            value-1
                        </li>
                        <li>
                            value-2
                        </li>
                        <li>
                            value-3
                        </li>
                        <li>
                            value-4
                        </li>
                    </ul>
                </li>
                <li>
                    <b>level-3</b>
                    plain value
                </li>
            </ul>
        </li>
        <li>
            <b>item-2</b>
            <ul>
                <li>
                    a
                </li>
                <li>
                    b
                </li>
                <li>
                    c
                </li>
            </ul>
        </li>
    </ul>
'''
        expected = htmlout.header + content + htmlout.footer
        filtered = OutputManager(summary).get(format='html', max_level=1)
        self.assertEqual(filtered, expected)

    def test_apply_output_formatting_html_3(self):
        htmlout = plugintools.HTMLFormatter()
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
        content = '''    <ul class="tree">
        <li>
            <details>
                <summary>item-1</summary>
                <ul>
                    <li>
                        <b>level-2</b>
                        <ul>
                            <li>
                                value-1
                            </li>
                            <li>
                                value-2
                            </li>
                            <li>
                                value-3
                            </li>
                            <li>
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
                    </li>
                    <li>
                        b
                    </li>
                    <li>
                        c
                    </li>
                </ul>
            </details>
        </li>
    </ul>
'''
        expected = htmlout.header + content + htmlout.footer
        filtered = OutputManager(summary).get(format='html', max_level=2)
        self.assertEqual(filtered, expected)
