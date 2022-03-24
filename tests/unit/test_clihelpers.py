import os
import subprocess
import tempfile

import mock

from . import utils

from hotsos.core.config import setup_config, HotSOSConfig
from hotsos.core import cli_helpers


class TestCLIHelpers(utils.BaseTestCase):
    """
    NOTE: remember that data_root is configured so helpers will always
    use fake_data_root if possible. If you write a test that wants to
    test scenario where no data root is set (i.e. no sosreport) you need
    to unset it as part of the test.
    """

    def setUp(self, *args, **kwargs):
        super().setUp(*args, **kwargs)
        self.helper = cli_helpers.CLIHelper()

    def test_ns_ip_addr(self):
        ns = "qrouter-984c22fd-64b3-4fa1-8ddd-87090f401ce5"
        out = self.helper.ns_ip_addr(namespace=ns)
        self.assertEqual(type(out), list)
        self.assertEqual(len(out), 18)

    def test_udevadm_info_dev(self):
        out = self.helper.udevadm_info_dev(device='/dev/vdb')
        self.assertEqual(out, [])

    @mock.patch.object(cli_helpers, 'subprocess')
    def test_ps(self, mock_subprocess):
        path = os.path.join(HotSOSConfig.DATA_ROOT, "ps")
        with open(path, 'r') as fd:
            out = fd.readlines()

        ret = self.helper.ps()
        self.assertEqual(ret, out)
        self.assertFalse(mock_subprocess.called)

    def test_get_date_local(self):
        setup_config(DATA_ROOT='/')
        helper = cli_helpers.CLIHelper()
        self.assertEqual(type(helper.date()), str)

    def test_get_date(self):
        self.assertEqual(self.helper.date(), '1644509957')

    def test_get_date_w_tz(self):
        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(DATA_ROOT=dtmp)
            helper = cli_helpers.CLIHelper()
            os.makedirs(os.path.join(dtmp, "sos_commands/date"))
            with open(os.path.join(dtmp, "sos_commands/date/date"),
                      'w') as fd:
                fd.write("Thu Mar 25 10:55:05 UTC 2021")

            self.assertEqual(helper.date(), '1616669705')

    def test_get_date_w_invalid_tz(self):
        with tempfile.TemporaryDirectory() as dtmp:
            setup_config(DATA_ROOT=dtmp)
            helper = cli_helpers.CLIHelper()
            os.makedirs(os.path.join(dtmp, "sos_commands/date"))
            with open(os.path.join(dtmp, "sos_commands/date/date"),
                      'w') as fd:
                fd.write("Thu Mar 25 10:55:05 123UTC 2021")

            self.assertEqual(helper.date(), "")

    def test_ovs_ofctl_bin_w_errors(self):

        def fake_check_output(cmd, *_args, **_kwargs):
            if 'OpenFlow13' in cmd:
                return 'testdata'.encode(encoding='utf_8', errors='strict')
            else:
                raise subprocess.CalledProcessError(1, 'ofctl')

        setup_config(DATA_ROOT='/')
        with mock.patch('hotsos.core.cli_helpers.subprocess.check_output') as \
                mock_check_output:
            mock_check_output.side_effect = fake_check_output

            # Test errors with eventual success
            helper = cli_helpers.CLIHelper()
            self.assertEqual(helper.ovs_ofctl_show(bridge='br-int'),
                             ['testdata'])

            mock_check_output.side_effect = \
                subprocess.CalledProcessError(1, 'ofctl')

            # Ensure that if all fails the result is always iterable
            helper = cli_helpers.CLIHelper()
            self.assertEqual(helper.ovs_ofctl_show(bridge='br-int'), [])
