import json

from . import utils

from hotsos.core.config import (
    setup_config,
    HotSOSConfig,
)
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


class TestHotSOSConfig(utils.BaseTestCase):

    def test_restore_defaults(self):
        try:
            path = 'tests/unit/fake_data_root/openstack'
            self.assertTrue(HotSOSConfig.DATA_ROOT.endswith(path))
            self.assertTrue(HotSOSConfig.USE_ALL_LOGS)
            self.assertEqual(HotSOSConfig.MAX_LOGROTATE_DEPTH, 7)

            setup_config(DATA_ROOT='foo', USE_ALL_LOGS=False,
                         MAX_LOGROTATE_DEPTH=1)
            self.assertEqual(HotSOSConfig.DATA_ROOT, 'foo')
            self.assertFalse(HotSOSConfig.USE_ALL_LOGS)
            self.assertEqual(HotSOSConfig.MAX_LOGROTATE_DEPTH, 1)
        finally:
            HotSOSConfig.reset()
            # check global defaults
            self.assertFalse(HotSOSConfig.USE_ALL_LOGS)
            self.assertEqual(HotSOSConfig.MAX_LOGROTATE_DEPTH, 7)
            super().setUp()
            # check unit test defaults
            self.assertTrue(HotSOSConfig.DATA_ROOT.endswith(path))
            self.assertTrue(HotSOSConfig.USE_ALL_LOGS)


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
