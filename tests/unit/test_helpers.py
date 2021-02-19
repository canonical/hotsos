import os

import mock
import utils

from common import helpers


class TestHelpers(utils.BaseTestCase):

    def setUp(self):
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(helpers, 'subprocess')
    def test_get_ip_addr(self, mock_subprocess):
        path = os.path.join(os.environ["DATA_ROOT"],
                            "sos_commands/networking/ip_-d_address")
        with open(path, 'r') as fd:
            out = fd.readlines()

        ret = helpers.get_ip_addr()
        self.assertEquals(ret, out)
        self.assertFalse(mock_subprocess.called)

    @mock.patch.object(helpers, 'subprocess')
    def test_get_ps(self, mock_subprocess):
        path = os.path.join(os.environ["DATA_ROOT"], "ps")
        with open(path, 'r') as fd:
            out = fd.readlines()

        ret = helpers.get_ps()
        self.assertEquals(ret, out)
        self.assertFalse(mock_subprocess.called)
