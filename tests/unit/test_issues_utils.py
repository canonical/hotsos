import os

import mock
import tempfile
import utils
import shutil
import yaml

from common import (
    issue_types,
    issues_utils,
)


class TestIssuesUtils(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        if os.path.isdir(self.tmpdir):
            shutil.rmtree(self.tmpdir)

        super().tearDown()

    def test_get_issues(self):
        issues = {}
        with mock.patch.object(issues_utils, 'PLUGIN_TMP_DIR',
                               self.tmpdir):
            with open(os.path.join(self.tmpdir, 'issues.yaml'), 'w') as fd:
                fd.write(yaml.dump(issues))

            ret = issues_utils._get_issues()
            self.assertEquals(ret, issues)

    def test_add_issue(self):
        with mock.patch.object(issues_utils, 'PLUGIN_TMP_DIR',
                               self.tmpdir):
            issues_utils.add_issue(issue_types.MemoryWarning("test"))
            ret = issues_utils._get_issues()
            self.assertEquals(ret,
                              {issues_utils.MASTER_YAML_ISSUES_FOUND_KEY:
                               [{'MemoryWarning': 'test'}]})
