import os
import subprocess
from unittest import mock

from hotsos.core.config import HotSOSConfig
from hotsos.core.host_helpers import cli as host_cli

from .. import utils


class TestCLIHelper(utils.BaseTestCase):
    """
    NOTE: remember that a data_root is configured so helpers will always
    use fake_data_root if possible. If you write a test that wants to
    test a scenario where no data root is set (i.e. no sosreport) you need
    to unset it as part of the test.
    """

    def test_journalctl(self):
        HotSOSConfig.use_all_logs = False
        HotSOSConfig.max_logrotate_depth = 7
        self.assertEqual(host_cli.JournalctlBase().since_date,
                         "2022-02-09")
        HotSOSConfig.use_all_logs = True
        self.assertEqual(host_cli.JournalctlBase().since_date,
                         "2022-02-03")
        HotSOSConfig.max_logrotate_depth = 1000
        self.assertEqual(host_cli.JournalctlBase().since_date,
                         "2019-05-17")

    def test_ns_ip_addr(self):
        ns = "qrouter-984c22fd-64b3-4fa1-8ddd-87090f401ce5"
        out = host_cli.CLIHelper().ns_ip_addr(namespace=ns)
        self.assertIsInstance(out, list)
        self.assertEqual(len(out), 18)

    def test_udevadm_info_dev(self):
        out = host_cli.CLIHelper().udevadm_info_dev(device='/dev/vdb')
        self.assertEqual(out, [])

    @mock.patch.object(host_cli, 'subprocess')
    def test_ps(self, mock_subprocess):
        path = os.path.join(HotSOSConfig.data_root, "ps")
        with open(path, 'r') as fd:
            out = fd.readlines()

        self.assertEqual(host_cli.CLIHelper().ps(), out)
        self.assertFalse(mock_subprocess.called)

    def test_get_date_local(self):
        HotSOSConfig.data_root = '/'
        self.assertEqual(type(host_cli.CLIHelper().date()), str)

    def test_get_date(self):
        self.assertEqual(host_cli.CLIHelper().date(), '1644509957')

    @utils.create_data_root({'sos_commands/date/date':
                             'Thu Mar 25 10:55:05 2021'})
    def test_get_date_no_tz(self):
        self.assertEqual(host_cli.CLIHelper().date(), '1616669705')

    @utils.create_data_root({'sos_commands/date/date':
                             'Thu Mar 25 10:55:05 -03 2021'})
    def test_get_date_w_numeric_tz(self):
        self.assertEqual(host_cli.CLIHelper().date(), '1616680505')

    @utils.create_data_root({'sos_commands/date/date':
                             'Thu Mar 25 10:55:05 UTC 2021'})
    def test_get_date_w_tz(self):
        self.assertEqual(host_cli.CLIHelper().date(), '1616669705')

    @utils.create_data_root({'sos_commands/date/date':
                             'Thu Mar 25 10:55:05 123UTC 2021'})
    def test_get_date_w_invalid_tz(self):
        with self.assertLogs(logger='hotsos', level='ERROR') as log:
            self.assertEqual(host_cli.CLIHelper().date(), "")
            # If invalid date, log.error() will have been called
            self.assertEqual(len(log.output), 1)
            self.assertIn('has invalid date string', log.output[0])

    def test_ovs_ofctl_bin_w_errors(self):

        def fake_run(cmd, *_args, **_kwargs):
            if 'OpenFlow13' in cmd:
                m = mock.MagicMock()
                m.returncode = 0
                m.stdout = 'testdata'.encode(encoding='utf_8', errors='strict')
                m.stderr = ''
                return m

            raise subprocess.CalledProcessError(1, 'ofctl')

        HotSOSConfig.data_root = '/'
        with mock.patch.object(host_cli.subprocess, 'run') as \
                mock_run:
            mock_run.side_effect = fake_run

            # Test errors with eventual success
            helper = host_cli.CLIHelper()
            self.assertEqual(helper.ovs_ofctl(command='show', args='br-int'),
                             ['testdata'])

            mock_run.side_effect = \
                subprocess.CalledProcessError(1, 'ofctl')

            # Ensure that if all fails the result is always iterable
            helper = host_cli.CLIHelper()
            self.assertEqual(helper.ovs_ofctl(command='show', args='br-int'),
                             [])

    @mock.patch.object(host_cli.CLIHelper, 'command_catalog',
                       {'sleep': [host_cli.BinCmd('time sleep 2')]})
    def test_cli_timeout(self):
        cli = host_cli.CLIHelper()
        orig_cfg = HotSOSConfig.CONFIG
        try:
            # ensure bin command executed
            HotSOSConfig.data_root = '/'
            HotSOSConfig.command_timeout = 1
            out = cli.sleep()
            # a returned [] implies an exception was raised and caught
            self.assertEqual(out, [])
        finally:
            # restore
            HotSOSConfig.set(**orig_cfg)

    @mock.patch.object(host_cli.CLIHelper, 'command_catalog',
                       {'sleep': [host_cli.BinCmd('time sleep 1')]})
    def test_cli_no_timeout(self):
        cli = host_cli.CLIHelper()
        orig_cfg = HotSOSConfig.CONFIG
        try:
            # ensure bin command executed
            HotSOSConfig.data_root = '/'
            out = cli.sleep()
            self.assertEqual(len(out), 2)
        finally:
            # restore
            HotSOSConfig.set(**orig_cfg)

    def test_clitempfile(self):
        with host_cli.CLIHelperFile() as cli:
            self.assertEqual(os.path.basename(cli.date()), 'date')

        with host_cli.CLIHelperFile() as cli:
            orig_cfg = HotSOSConfig.CONFIG
            try:
                # ensure bin command executed
                HotSOSConfig.data_root = '/'
                self.assertEqual(cli.date(), cli.output_file)
            finally:
                # restore
                HotSOSConfig.set(**orig_cfg)
