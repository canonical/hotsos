import os

import utils
import yaml

from core.issues import (
    issue_types,
    issue_utils,
)


class TestIssuesUtils(utils.BaseTestCase):

    def test_get_issues(self):
        issues = {}
        with open(os.path.join(self.plugin_tmp_dir, 'issues.yaml'), 'w') as fd:
            fd.write(yaml.dump(issues))

        ret = issue_utils._get_issues()
        self.assertEquals(ret, issues)

    def test_add_issue(self):
        issue_utils.add_issue(issue_types.MemoryWarning("test"))
        ret = issue_utils._get_issues()
        self.assertEquals(ret,
                          {issue_utils.MASTER_YAML_ISSUES_FOUND_KEY:
                           [{'type': 'MemoryWarning',
                             'desc': 'test',
                             'origin': 'testplugin.01part'}]})
