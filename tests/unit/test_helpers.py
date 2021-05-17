import os

import mock
import tempfile
import utils

from common import cli_helpers


class Testcli_helpers(utils.BaseTestCase):

    def setUp(self):
        # NOTE: remember that data_root is configured so helpers will always
        # use fake_data_root if possible. If you write a test that wants to
        # test scenario where no data root is set (i.e. no sosreport) you need
        # to unset it as part of the test.
        super().setUp()

    def tearDown(self):
        super().tearDown()

    @mock.patch.object(cli_helpers, 'subprocess')
    def test_get_ip_addr(self, mock_subprocess):
        path = os.path.join(os.environ["DATA_ROOT"],
                            "sos_commands/networking/ip_-d_address")
        with open(path, 'r') as fd:
            out = fd.readlines()

        ret = cli_helpers.get_ip_addr()
        self.assertEquals(ret, out)
        self.assertFalse(mock_subprocess.called)

    @mock.patch.object(cli_helpers, 'subprocess')
    def test_get_ps(self, mock_subprocess):
        path = os.path.join(os.environ["DATA_ROOT"], "ps")
        with open(path, 'r') as fd:
            out = fd.readlines()

        ret = cli_helpers.get_ps()
        self.assertEquals(ret, out)
        self.assertFalse(mock_subprocess.called)

    @mock.patch.object(cli_helpers, "DATA_ROOT", '/')
    def test_get_date_local(self):
        self.assertEquals(type(cli_helpers.get_date()), str)

    def test_get_date(self):
        self.assertEquals(cli_helpers.get_date(), '1616669705\n')

    def test_get_date_w_tz(self):
        with tempfile.TemporaryDirectory() as dtmp:
            with mock.patch.object(cli_helpers, 'DATA_ROOT', dtmp):
                os.makedirs(os.path.join(dtmp, "sos_commands/date"))
                with open(os.path.join(dtmp, "sos_commands/date/date"),
                          'w') as fd:
                    fd.write("Thu Mar 25 10:55:05 UTC 2021")

                self.assertEquals(cli_helpers.get_date(), '1616669705\n')

    def test_get_date_w_invalid_tz(self):
        with tempfile.TemporaryDirectory() as dtmp:
            with mock.patch.object(cli_helpers, 'DATA_ROOT', dtmp):
                os.makedirs(os.path.join(dtmp, "sos_commands/date"))
                with open(os.path.join(dtmp, "sos_commands/date/date"),
                          'w') as fd:
                    fd.write("Thu Mar 25 10:55:05 123UTC 2021")

                self.assertEquals(cli_helpers.get_date(), "")
