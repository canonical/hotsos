import os

import yaml
from hotsos.core.config import HotSOSConfig
from hotsos.core.issues import (
    LaunchpadBug,
    MemoryWarning,
    IssueContext,
    IssuesManager,
)

from . import utils


class TestIssuesUtils(utils.BaseTestCase):
    """ Unit tests for issues utils. """
    def setUp(self):
        super().setUp()
        HotSOSConfig.machine_readable = False

    def test_get_issues(self):
        raised_issues = {}
        with open(os.path.join(self.plugin_tmp_dir, 'yaml'), 'w') as fd:
            fd.write(yaml.dump(raised_issues))

        mgr = IssuesManager()
        ret = mgr.load_issues()
        self.assertEqual(ret, raised_issues)

    def test_issue_not_machine_readable(self):
        mgr = IssuesManager()
        mgr.add(MemoryWarning("test"))
        ret = mgr.load_issues()
        self.assertEqual(ret,
                         {IssuesManager.SUMMARY_OUT_ISSUES_ROOT:
                          {'MemoryWarnings': ['test']}})

    def test_issue_machine_readable(self):
        HotSOSConfig.machine_readable = True
        mgr = IssuesManager()
        mgr.add(MemoryWarning("test"))
        ret = mgr.load_issues()
        self.assertEqual(ret,
                         {IssuesManager.SUMMARY_OUT_ISSUES_ROOT:
                          [{'type': 'MemoryWarning',
                            'message': 'test',
                            'origin': 'testplugin.testpart'}]})

    def test_add_issue_w_empty_context(self):
        HotSOSConfig.machine_readable = True
        ctxt = IssueContext()
        mgr = IssuesManager()
        mgr.add(MemoryWarning("test"), ctxt)
        ret = mgr.load_issues()
        self.assertEqual(ret,
                         {IssuesManager.SUMMARY_OUT_ISSUES_ROOT:
                          [{'type': 'MemoryWarning',
                            'message': 'test',
                            'origin': 'testplugin.testpart'}]})

    def test_add_issue_empty_context(self):
        HotSOSConfig.machine_readable = True
        ctxt = IssueContext()
        ctxt.set(linenumber=123, path='/foo/bar')
        mgr = IssuesManager()
        mgr.add(MemoryWarning("test"), ctxt)
        ret = mgr.load_issues()
        self.assertEqual(ret,
                         {IssuesManager.SUMMARY_OUT_ISSUES_ROOT:
                          [{'type': 'MemoryWarning',
                            'message': 'test',
                            'context': {'path': '/foo/bar', 'linenumber': 123},
                            'origin': 'testplugin.testpart'}]})


class TestKnownBugsUtils(utils.BaseTestCase):
    """ Unit tests for known bugs utils. """
    def test_get_known_bugs(self):
        known_bugs = {IssuesManager.SUMMARY_OUT_BUGS_ROOT:
                      [{'id': 'https://bugs.launchpad.net/bugs/1',
                        'message': None,
                        'origin': 'testplugin.testpart'}]}
        with open(os.path.join(self.plugin_tmp_dir,
                               'known_bugs.yaml'), 'w') as fd:
            fd.write(yaml.dump(known_bugs))

        ret = IssuesManager().load_bugs()
        self.assertEqual(ret, known_bugs)

    def test_get_known_bugs_none(self):
        ret = IssuesManager().load_bugs()
        self.assertEqual(ret, {})

    def test_add_issue_first(self):
        mgr = IssuesManager()
        mgr.add(LaunchpadBug(1, None))
        ret = mgr.load_bugs()
        self.assertEqual(ret,
                         {IssuesManager.SUMMARY_OUT_BUGS_ROOT:
                          [{'id': 'https://bugs.launchpad.net/bugs/1',
                            'message': None,
                            'origin': 'testplugin.testpart'}
                           ]})

    def test_add_issue(self):
        known_bugs = {IssuesManager.SUMMARY_OUT_BUGS_ROOT:
                      [{'id': 'https://bugs.launchpad.net/bugs/1',
                        'message': None,
                        'origin': 'testplugin.testpart'}]}
        with open(os.path.join(self.plugin_tmp_dir,
                               'known_bugs.yaml'), 'w') as fd:
            fd.write(yaml.dump(known_bugs))

        mgr = IssuesManager()
        mgr.add(LaunchpadBug(2, None))
        ret = mgr.load_bugs()
        expected = {IssuesManager.SUMMARY_OUT_BUGS_ROOT:
                    [{'id': 'https://bugs.launchpad.net/bugs/1',
                      'message': None,
                      'origin': 'testplugin.testpart'},
                     {'id': 'https://bugs.launchpad.net/bugs/2',
                      'message': None,
                      'origin': 'testplugin.testpart'}]}
        self.assertEqual(ret, expected)
