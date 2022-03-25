import os

import yaml

from tests.unit import utils

from core import issues


class TestIssuesUtils(utils.BaseTestCase):

    def test_get_issues(self):
        raised_issues = {}
        with open(os.path.join(self.plugin_tmp_dir, 'issues.yaml'), 'w') as fd:
            fd.write(yaml.dump(raised_issues))

        ret = issues.utils.get_plugin_issues()
        self.assertEqual(ret, raised_issues)

    def test_add_issue(self):
        issues.utils.add_issue(issues.MemoryWarning("test"))
        ret = issues.utils.get_plugin_issues()
        self.assertEqual(ret,
                         {issues.utils.MASTER_YAML_ISSUES_FOUND_KEY:
                          [{'type': 'MemoryWarning',
                            'desc': 'test',
                            'origin': 'testplugin.01part'}]})


class TestKnownBugsUtils(utils.BaseTestCase):

    def test_get_known_bugs(self):
        known_bugs = {issues.bugs.MASTER_YAML_KNOWN_BUGS_KEY:
                      [{'id': 'https://bugs.launchpad.net/bugs/1',
                        'desc': 'no description provided',
                        'origin': 'testplugin.01part'}]}
        with open(os.path.join(self.plugin_tmp_dir,
                               'known_bugs.yaml'), 'w') as fd:
            fd.write(yaml.dump(known_bugs))

        ret = issues.bugs.get_known_bugs()
        self.assertEqual(ret, known_bugs)

    def test_get_known_bugs_none(self):
        ret = issues.bugs.get_known_bugs()
        self.assertEqual(ret, {})

    def test_add_known_bug_first(self):
        issues.bugs.add_known_bug(1)
        ret = issues.bugs.get_known_bugs()
        self.assertEqual(ret,
                         {issues.bugs.MASTER_YAML_KNOWN_BUGS_KEY:
                          [{'id': 'https://bugs.launchpad.net/bugs/1',
                            'desc': 'no description provided',
                            'origin': 'testplugin.01part'}
                           ]})

    def test_add_known_bug(self):
        known_bugs = {issues.bugs.MASTER_YAML_KNOWN_BUGS_KEY:
                      [{'id': 'https://bugs.launchpad.net/bugs/1',
                        'desc': 'no description provided',
                        'origin': 'testplugin.01part'}]}
        with open(os.path.join(self.plugin_tmp_dir,
                               'known_bugs.yaml'), 'w') as fd:
            fd.write(yaml.dump(known_bugs))

        issues.bugs.add_known_bug(2)
        ret = issues.bugs.get_known_bugs()
        expected = {issues.bugs.MASTER_YAML_KNOWN_BUGS_KEY:
                    [{'id': 'https://bugs.launchpad.net/bugs/1',
                      'desc': 'no description provided',
                      'origin': 'testplugin.01part'},
                     {'id': 'https://bugs.launchpad.net/bugs/2',
                      'desc': 'no description provided',
                      'origin': 'testplugin.01part'}]}
        self.assertEqual(ret, expected)
