import os
import tempfile

import yaml

from tests.unit import utils

from tools import output_filter
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
        with tempfile.NamedTemporaryFile() as ftmp:
            os.environ['MASTER_YAML_OUT'] = ftmp.name
            with open(ftmp.name, 'w') as fd:
                fd.write(yaml.dump(issues))

            output_filter.minimise_master_output(mode='short')

            with open(ftmp.name) as fd:
                result = yaml.load(fd, Loader=yaml.SafeLoader)

            self.assertEqual(result, None)

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
        with tempfile.NamedTemporaryFile() as ftmp:
            os.environ['MASTER_YAML_OUT'] = ftmp.name
            with open(ftmp.name, 'w') as fd:
                fd.write(yaml.dump(ISSUES_LEGACY_FORMAT))

            output_filter.minimise_master_output(mode='short')

            with open(ftmp.name) as fd:
                result = yaml.load(fd, Loader=yaml.SafeLoader)

            self.assertEqual(result, expected)

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
        with tempfile.NamedTemporaryFile() as ftmp:
            os.environ['MASTER_YAML_OUT'] = ftmp.name
            with open(ftmp.name, 'w') as fd:
                fd.write(yaml.dump(ISSUES_NEW_FORMAT))

            output_filter.minimise_master_output(mode='short')

            with open(ftmp.name) as fd:
                result = yaml.load(fd, Loader=yaml.SafeLoader)

            self.assertEqual(result, expected)

    def test_output_filter_mode_very_short_legacy(self):
        expected = {MASTER_YAML_ISSUES_FOUND_KEY: {
                        'testplugin': {
                            'MemoryWarning': 1}},
                    MASTER_YAML_KNOWN_BUGS_KEY: {
                        'testplugin': ['1234']}}
        with tempfile.NamedTemporaryFile() as ftmp:
            os.environ['MASTER_YAML_OUT'] = ftmp.name
            with open(ftmp.name, 'w') as fd:
                fd.write(yaml.dump(ISSUES_LEGACY_FORMAT))

            output_filter.minimise_master_output(mode='very-short')

            with open(ftmp.name) as fd:
                result = yaml.load(fd, Loader=yaml.SafeLoader)

            self.assertEqual(result, expected)

    def test_output_filter_mode_very_short(self):
        expected = {MASTER_YAML_ISSUES_FOUND_KEY: {
                        'testplugin': {
                            'MemoryWarnings': 1}},
                    MASTER_YAML_KNOWN_BUGS_KEY: {
                        'testplugin': ['1234']}}
        with tempfile.NamedTemporaryFile() as ftmp:
            os.environ['MASTER_YAML_OUT'] = ftmp.name
            with open(ftmp.name, 'w') as fd:
                fd.write(yaml.dump(ISSUES_NEW_FORMAT))

            output_filter.minimise_master_output(mode='very-short')

            with open(ftmp.name) as fd:
                result = yaml.load(fd, Loader=yaml.SafeLoader)

            self.assertEqual(result, expected)
