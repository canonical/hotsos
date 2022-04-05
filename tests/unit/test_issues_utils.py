import os

import yaml

from . import utils

from hotsos.core.issues import (
    utils as issues_utils,
    LaunchpadBug,
    MemoryWarning,
)


class TestIssuesUtils(utils.BaseTestCase):

    def test_get_issues(self):
        raised_issues = {}
        with open(os.path.join(self.plugin_tmp_dir, 'yaml'), 'w') as fd:
            fd.write(yaml.dump(raised_issues))

        ret = issues_utils.get_plugin_issues()
        self.assertEqual(ret, raised_issues)

    def test_add_issue(self):
        issues_utils.add_issue(MemoryWarning("test"))
        ret = issues_utils.get_plugin_issues()
        self.assertEqual(ret,
                         {issues_utils.MASTER_YAML_ISSUES_FOUND_KEY:
                          [{'type': 'MemoryWarning',
                            'desc': 'test',
                            'origin': 'testplugin.01part'}]})


class TestKnownBugsUtils(utils.BaseTestCase):

    def test_get_known_bugs(self):
        known_bugs = {issues_utils.MASTER_YAML_KNOWN_BUGS_KEY:
                      [{'id': 'https://bugs.launchpad.net/bugs/1',
                        'desc': None,
                        'origin': 'testplugin.01part'}]}
        with open(os.path.join(self.plugin_tmp_dir,
                               'known_bugs.yaml'), 'w') as fd:
            fd.write(yaml.dump(known_bugs))

        ret = issues_utils.get_known_bugs()
        self.assertEqual(ret, known_bugs)

    def test_get_known_bugs_none(self):
        ret = issues_utils.get_known_bugs()
        self.assertEqual(ret, {})

    def test_add_issue_first(self):
        issues_utils.add_issue(LaunchpadBug(1, None))
        ret = issues_utils.get_known_bugs()
        self.assertEqual(ret,
                         {issues_utils.MASTER_YAML_KNOWN_BUGS_KEY:
                          [{'id': 'https://bugs.launchpad.net/bugs/1',
                            'desc': None,
                            'origin': 'testplugin.01part'}
                           ]})

    def test_add_issue(self):
        known_bugs = {issues_utils.MASTER_YAML_KNOWN_BUGS_KEY:
                      [{'id': 'https://bugs.launchpad.net/bugs/1',
                        'desc': None,
                        'origin': 'testplugin.01part'}]}
        with open(os.path.join(self.plugin_tmp_dir,
                               'known_bugs.yaml'), 'w') as fd:
            fd.write(yaml.dump(known_bugs))

        issues_utils.add_issue(LaunchpadBug(2, None))
        ret = issues_utils.get_known_bugs()
        expected = {issues_utils.MASTER_YAML_KNOWN_BUGS_KEY:
                    [{'id': 'https://bugs.launchpad.net/bugs/1',
                      'desc': None,
                      'origin': 'testplugin.01part'},
                     {'id': 'https://bugs.launchpad.net/bugs/2',
                      'desc': None,
                      'origin': 'testplugin.01part'}]}
        self.assertEqual(ret, expected)
