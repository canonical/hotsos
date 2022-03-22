import json

from tests.unit import utils

from core.plugintools import dump
from core import output_filter
from core.issues.utils import MASTER_YAML_ISSUES_FOUND_KEY
from core.issues.bugs import MASTER_YAML_KNOWN_BUGS_KEY

ISSUES_LEGACY_FORMAT = {
    'testplugin': {
        MASTER_YAML_ISSUES_FOUND_KEY: [{
             'type': 'MemoryWarning',
             'desc': 'a msg',
             'origin': 'testplugin.01part'}],
        MASTER_YAML_KNOWN_BUGS_KEY: [{
             'id': '1234',
             'desc': 'a msg',
             'origin': 'testplugin.01part'}]}}

ISSUES_NEW_FORMAT = {
    'testplugin': {
        MASTER_YAML_ISSUES_FOUND_KEY: {
             'MemoryWarnings': [
                 'a msg (origin=testplugin.01part)']},
        MASTER_YAML_KNOWN_BUGS_KEY: [{
             'id': '1234',
             'desc': 'a msg',
             'origin': 'testplugin.01part'}]}}


class TestTools(utils.BaseTestCase):

    def test_output_filter_empty(self):
        issues = {}
        filtered = output_filter.minimise_master_output(issues, mode='short')
        self.assertEqual(filtered, {})

    def test_output_filter_mode_short_legacy(self):
        expected = {MASTER_YAML_ISSUES_FOUND_KEY: {
                        'testplugin': [{
                            'type': 'MemoryWarning',
                            'desc': 'a msg',
                            'origin':
                            'testplugin.01part'}]},
                    MASTER_YAML_KNOWN_BUGS_KEY: {
                        'testplugin': [{
                            'id': '1234',
                            'desc': 'a msg',
                            'origin': 'testplugin.01part'}]}}

        filtered = output_filter.minimise_master_output(ISSUES_LEGACY_FORMAT,
                                                        mode='short')
        self.assertEqual(filtered, expected)

    def test_output_filter_mode_short(self):
        expected = {MASTER_YAML_ISSUES_FOUND_KEY: {
                        'testplugin': {
                            'MemoryWarnings': [
                                'a msg (origin=testplugin.01part)']}},
                    MASTER_YAML_KNOWN_BUGS_KEY: {
                        'testplugin': [{
                            'id': '1234',
                            'desc': 'a msg',
                            'origin': 'testplugin.01part'}]}}
        filtered = output_filter.minimise_master_output(ISSUES_NEW_FORMAT,
                                                        mode='short')
        self.assertEqual(filtered, expected)

    def test_output_filter_mode_very_short_legacy(self):
        expected = {MASTER_YAML_ISSUES_FOUND_KEY: {
                        'testplugin': {
                            'MemoryWarning': 1}},
                    MASTER_YAML_KNOWN_BUGS_KEY: {
                        'testplugin': ['1234']}}
        filtered = output_filter.minimise_master_output(ISSUES_LEGACY_FORMAT,
                                                        mode='very-short')
        self.assertEqual(filtered, expected)

    def test_output_filter_mode_very_short(self):
        expected = {MASTER_YAML_ISSUES_FOUND_KEY: {
                        'testplugin': {
                            'MemoryWarnings': 1}},
                    MASTER_YAML_KNOWN_BUGS_KEY: {
                        'testplugin': ['1234']}}

        filtered = output_filter.minimise_master_output(ISSUES_NEW_FORMAT,
                                                        mode='very-short')
        self.assertEqual(filtered, expected)

    def test_apply_output_formatting_defaults(self):
        summary = {'opt': 'value'}
        filtered = output_filter.apply_output_formatting(summary, 'yaml')
        self.assertEqual(filtered, dump(summary))

    def test_apply_output_formatting_json(self):
        summary = {'opt': 'value'}
        filtered = output_filter.apply_output_formatting(summary, 'json')
        self.assertEqual(filtered, json.dumps(summary, indent=2,
                                              sort_keys=True))
