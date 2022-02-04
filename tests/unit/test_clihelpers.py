import os
import subprocess
import tempfile

import mock

from tests.unit import utils

from core import cli_helpers


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
        ns = "qrouter-4a39d0f7-77ab-4c79-97e1-652cc80c52e2"
        out = self.helper.ns_ip_addr(namespace=ns)
        self.assertEquals(type(out), list)
        self.assertEquals(len(out), 18)

    def test_udevadm_info_dev(self):
        out = self.helper.udevadm_info_dev(device='/dev/vdb')
        self.assertEquals(out, [])

    @mock.patch.object(cli_helpers, 'subprocess')
    def test_ps(self, mock_subprocess):
        path = os.path.join(os.environ["DATA_ROOT"], "ps")
        with open(path, 'r') as fd:
            out = fd.readlines()

        ret = self.helper.ps()
        self.assertEquals(ret, out)
        self.assertFalse(mock_subprocess.called)

    def test_get_date_local(self):
        os.environ['DATA_ROOT'] = '/'
        helper = cli_helpers.CLIHelper()
        self.assertEquals(type(helper.date()), str)

    def test_get_date(self):
        self.assertEquals(self.helper.date(), '1627986690')

    def test_get_date_w_tz(self):
        with tempfile.TemporaryDirectory() as dtmp:
            os.environ['DATA_ROOT'] = dtmp
            helper = cli_helpers.CLIHelper()
            os.makedirs(os.path.join(dtmp, "sos_commands/date"))
            with open(os.path.join(dtmp, "sos_commands/date/date"),
                      'w') as fd:
                fd.write("Thu Mar 25 10:55:05 UTC 2021")

            self.assertEquals(helper.date(), '1616669705')

    def test_get_date_w_invalid_tz(self):
        with tempfile.TemporaryDirectory() as dtmp:
            os.environ['DATA_ROOT'] = dtmp
            helper = cli_helpers.CLIHelper()
            os.makedirs(os.path.join(dtmp, "sos_commands/date"))
            with open(os.path.join(dtmp, "sos_commands/date/date"),
                      'w') as fd:
                fd.write("Thu Mar 25 10:55:05 123UTC 2021")

            self.assertEquals(helper.date(), "")

    def test_ovs_ofctl_bin_w_errors(self):

        def fake_check_output(cmd, *_args, **_kwargs):
            if 'OpenFlow13' in cmd:
                return 'testdata'.encode(encoding='utf_8', errors='strict')
            else:
                raise subprocess.CalledProcessError(1, 'ofctl')

        os.environ['DATA_ROOT'] = '/'
        with mock.patch('core.cli_helpers.subprocess.check_output') as \
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
