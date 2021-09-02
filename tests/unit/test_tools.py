import os

import tempfile
import utils
import yaml

from tools import output_filter


class TestTools(utils.BaseTestCase):

    def test_output_filter_empty(self):
        issues = {}
        with tempfile.NamedTemporaryFile() as ftmp:
            os.environ["MASTER_YAML_OUT"] = ftmp.name
            with open(ftmp.name, 'w') as fd:
                fd.write(yaml.dump(issues))

            output_filter.filter_master_yaml()

            with open(ftmp.name) as fd:
                result = yaml.load(fd, Loader=yaml.SafeLoader)

            self.assertEqual(result, None)

    def test_output_filter(self):
        issue_key = output_filter.issue_utils.MASTER_YAML_ISSUES_FOUND_KEY
        bug_key = output_filter.known_bugs_utils.MASTER_YAML_KNOWN_BUGS_KEY
        issues = {"testplugin":
                  {issue_key: [{"type": "MemoryWarning",
                                "desc": "a msg",
                                "origin": "testplugin.01part"}],
                   bug_key: [{"id": "1234",
                              "desc": "a msg",
                              "origin": "testplugin.01part"}]}}
        expected = {issue_key: {"testplugin": [{"type": "MemoryWarning",
                                                "desc": "a msg",
                                                "origin":
                                                "testplugin.01part"}]},
                    bug_key: {"testplugin": [{"id": "1234",
                                              "desc": "a msg",
                                              "origin": "testplugin.01part"}]}}
        with tempfile.NamedTemporaryFile() as ftmp:
            os.environ["MASTER_YAML_OUT"] = ftmp.name
            with open(ftmp.name, 'w') as fd:
                fd.write(yaml.dump(issues))

            output_filter.filter_master_yaml()

            with open(ftmp.name) as fd:
                result = yaml.load(fd, Loader=yaml.SafeLoader)

            self.assertEqual(result, expected)
