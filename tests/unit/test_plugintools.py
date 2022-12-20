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
