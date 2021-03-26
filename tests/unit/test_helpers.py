import os

import mock
import tempfile
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

    def test_get_date(self):
        self.assertEquals(helpers.get_date(), '1616669705\n')

    def test_get_date_w_tz(self):
        with tempfile.TemporaryDirectory() as dtmp:
            with mock.patch.object(helpers, 'DATA_ROOT', dtmp):
                os.makedirs(os.path.join(dtmp, "sos_commands/date"))
                with open(os.path.join(dtmp, "sos_commands/date/date"),
                          'w') as fd:
                    fd.write("Thu Mar 25 10:55:05 UTC 2021")

                self.assertEquals(helpers.get_date(), '1616669705\n')

    def test_get_date_w_invalid_tz(self):
        with tempfile.TemporaryDirectory() as dtmp:
            with mock.patch.object(helpers, 'DATA_ROOT', dtmp):
                os.makedirs(os.path.join(dtmp, "sos_commands/date"))
                with open(os.path.join(dtmp, "sos_commands/date/date"),
                          'w') as fd:
                    fd.write("Thu Mar 25 10:55:05 123UTC 2021")

                self.assertEquals(helpers.get_date(), "")
