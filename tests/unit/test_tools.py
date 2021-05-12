import mock
import tempfile
import utils
import yaml

from tools import (
    output_filter,
)


class TestTools(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    def test_output_filter_empty(self):
        issues = {}
        with tempfile.NamedTemporaryFile() as ftmp:
            with mock.patch.object(output_filter.constants, 'MASTER_YAML_OUT',
                                   ftmp.name):
                with open(ftmp.name, 'w') as fd:
                    fd.write(yaml.dump(issues))

                output_filter.filter_master_yaml()

                with open(ftmp.name) as fd:
                    result = yaml.load(fd, Loader=yaml.SafeLoader)

                self.assertEqual(result, None)

    def test_output_filter(self):
        issue_key = output_filter.issues_utils.MASTER_YAML_ISSUES_FOUND_KEY
        bug_key = output_filter.known_bugs_utils.MASTER_YAML_KNOWN_BUGS_KEY
        issues = {"testplugin":
                  {issue_key: [{"MemoryWarning": "a msg"}],
                   bug_key: [{1234: "a msg"}]}}
        expected = {issue_key: {'(testplugin) MemoryWarning': 'a msg'},
                    bug_key: {'(testplugin) 1234': "a msg"}}
        with tempfile.NamedTemporaryFile() as ftmp:
            with mock.patch.object(output_filter.constants, 'MASTER_YAML_OUT',
                                   ftmp.name):
                with open(ftmp.name, 'w') as fd:
                    fd.write(yaml.dump(issues))

                output_filter.filter_master_yaml()

                with open(ftmp.name) as fd:
                    result = yaml.load(fd, Loader=yaml.SafeLoader)

                self.assertEqual(result, expected)
