import os

import mock
import shutil
import tempfile
import yaml

import utils

from common import known_bugs_utils


class TestKnownBugsUtils(utils.BaseTestCase):

    def setUp(self):
        super().setUp()
        self.tmpdir = tempfile.mkdtemp()

    def tearDown(self):
        if os.path.isdir(self.tmpdir):
            shutil.rmtree(self.tmpdir)

        super().tearDown()

    def test_get_known_bugs(self):
        known_bugs = {"bugs": [{'https://bugs.launchpad.net/bugs/1':
                                'Microsoft has a majority market share'}]}
        with mock.patch.object(known_bugs_utils, 'PLUGIN_TMP_DIR',
                               self.tmpdir):
            with open(os.path.join(self.tmpdir, 'known_bugs.yaml'), 'w') as fd:
                fd.write(yaml.dump(known_bugs))

            ret = known_bugs_utils._get_known_bugs()
            self.assertEquals(ret, known_bugs)

    def test_get_known_bugs_none(self):
        with mock.patch.object(known_bugs_utils, 'PLUGIN_TMP_DIR',
                               self.tmpdir):
            ret = known_bugs_utils._get_known_bugs()
            self.assertEquals(ret, None)

    def test_add_known_bug_first(self):
        with mock.patch.object(known_bugs_utils, 'PLUGIN_TMP_DIR',
                               self.tmpdir):
            known_bugs_utils.add_known_bug(1)
            ret = known_bugs_utils._get_known_bugs()
            self.assertEquals(ret,
                              {known_bugs_utils.MASTER_YAML_KNOWN_BUGS_KEY:
                               [{'https://bugs.launchpad.net/bugs/1':
                                'Microsoft has a majority market share'}]})

    def test_add_known_bug(self):
        known_bugs = {known_bugs_utils.MASTER_YAML_KNOWN_BUGS_KEY:
                      [{'https://bugs.launchpad.net/bugs/1':
                        'Microsoft has a majority market share'}]}
        with mock.patch.object(known_bugs_utils, 'PLUGIN_TMP_DIR',
                               self.tmpdir):
            with open(os.path.join(self.tmpdir, 'known_bugs.yaml'), 'w') as fd:
                fd.write(yaml.dump(known_bugs))

            known_bugs_utils.add_known_bug(2)
            ret = known_bugs_utils._get_known_bugs()
            expected = {known_bugs_utils.MASTER_YAML_KNOWN_BUGS_KEY:
                        [{'https://bugs.launchpad.net/bugs/1':
                          'Microsoft has a majority market share'},
                         {'https://bugs.launchpad.net/bugs/2':
                          'no description provided'}]}
            self.assertEquals(ret, expected)
