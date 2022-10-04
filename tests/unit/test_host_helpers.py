import os

from unittest import mock

from . import utils

from hotsos.core.config import HotSOSConfig
from hotsos.core import host_helpers
from hotsos.core.host_helpers.filestat import FileFactory

UPTIME_LONG_FORMAT = ' 14:51:10 up 1 day,  6:27,  1 user,  load average: 0.55, 0.73, 0.70'  # noqa, pylint: disable=C0301


class TestHostNetworkingHelper(utils.BaseTestCase):

    def test_get_host_interfaces(self):
        expected = ['lo', 'ens3', 'ens4', 'ens5', 'ens6', 'ens7', 'ens8',
                    'ens9', 'br-ens3', 'ovs-system', 'br-tun', 'br-int',
                    'br-ex', 'br-data', 'lxdbr0', 'veth1883dceb@if16',
                    'veth5cc250bc@if18', 'veth396824c3@if20',
                    'vethe7aaf6c3@if22', 'veth59e22e6f@if24',
                    'veth8aa19e05@if26', 'veth0d284c32@if28',
                    'vxlan_sys_4789', 'tap0e778df8-ca']
        helper = host_helpers.HostNetworkingHelper()
        ifaces = helper.host_interfaces
        names = [iface.name for iface in ifaces]
        self.assertEqual(names, expected)

    def test_get_host_interfaces_w_ns(self):
        expected = ['lo', 'ens3', 'ens4', 'ens5', 'ens6', 'ens7', 'ens8',
                    'ens9', 'br-ens3', 'ovs-system', 'br-tun', 'br-int',
                    'br-ex', 'br-data', 'lxdbr0', 'veth1883dceb@if16',
                    'veth5cc250bc@if18', 'veth396824c3@if20',
                    'vethe7aaf6c3@if22', 'veth59e22e6f@if24',
                    'veth8aa19e05@if26', 'veth0d284c32@if28',
                    'vxlan_sys_4789', 'tap0e778df8-ca', 'lo',
                    'fpr-984c22fd-6@if2', 'fg-c8dcce74-c4', 'lo',
                    'rfp-984c22fd-6@if2', 'qr-3a70b31c-3f', 'lo',
                    'ha-550dc175-c0', 'qg-14f81a43-69', 'sg-189f4c40-9d']
        helper = host_helpers.HostNetworkingHelper()
        ifaces = helper.host_interfaces_all
        names = [iface.name for iface in ifaces]
        self.assertEqual(names, expected)

    def test_get_interface_with_addr_not_exists(self):
        helper = host_helpers.HostNetworkingHelper()
        iface = helper.get_interface_with_addr('1.2.3.4')
        self.assertIsNone(iface)

    def test_get_interface_with_addr_exists(self):
        expected = {'br-ens3': {
                        'addresses': ['10.0.0.128'],
                        'hwaddr': '22:c2:7b:1c:12:1b',
                        'state': 'UP',
                        'speed': 'unknown'}}
        helper = host_helpers.HostNetworkingHelper()
        iface = helper.get_interface_with_addr('10.0.0.128')
        self.assertEqual(iface.to_dict(), expected)

    @mock.patch.object(host_helpers.network, 'CLIHelper')
    def test_get_interface_with_speed_exists(self, mock_cli):
        cli = host_helpers.CLIHelper()
        orig_ip_addr = cli.ip_addr()
        orig_ip_link = cli.ip_link()
        mock_cli.return_value = mock.MagicMock()
        mock_cli.return_value.ethtool.return_value = ['Speed: 100000Mb/s\n']
        mock_cli.return_value.ip_addr.return_value = orig_ip_addr
        mock_cli.return_value.ip_link.return_value = orig_ip_link
        expected = {'br-ens3': {'addresses': ['10.0.0.128'],
                                'hwaddr': '22:c2:7b:1c:12:1b',
                                'state': 'UP',
                                'speed': '100000Mb/s'}}
        helper = host_helpers.HostNetworkingHelper()
        iface = helper.get_interface_with_addr('10.0.0.128')
        self.assertEqual(iface.to_dict(), expected)

    def test_get_interface_stats(self):
        expected = {'rx': {'dropped': 0,
                           'errors': 0,
                           'overrun': 0,
                           'packets': 1628707},
                    'tx': {'dropped': 0,
                           'errors': 0,
                           'packets': 1520974}}
        helper = host_helpers.HostNetworkingHelper()
        iface = helper.get_interface_with_addr('10.0.0.128')
        self.assertEqual(iface.stats, expected)

    def test_get_interfaces_cached(self):
        helper = host_helpers.HostNetworkingHelper()
        helper.host_interfaces_all
        path = helper.global_cache_root
        for path in [os.path.join(path, 'interfaces.json'),
                     os.path.join(path, 'ns_interfaces.json')]:
            self.assertTrue(os.path.exists(path))

        addr = '10.0.0.128'
        iface = helper.get_interface_with_addr(addr)
        # do this to cache stats
        iface.stats
        helper = host_helpers.HostNetworkingHelper()
        data = helper.cache_load()
        iface_found = False
        for _iface in data:
            if _iface['name'] == iface.name:
                iface_found = True
                self.assertEqual(_iface['addresses'], [addr])

        with mock.patch.object(host_helpers.network, 'CLIHelper') as mock_cli:
            mock_cli.return_value = mock.MagicMock()
            helper = host_helpers.HostNetworkingHelper()
            iface = helper.get_interface_with_addr(addr)
            self.assertEqual(iface.addresses, [addr])
            # these should no longer be called
            self.assertFalse(mock_cli.return_value.ip_addr.called)
            self.assertFalse(mock_cli.return_value.ip_netns.called)
            self.assertFalse(mock_cli.return_value.ns_ip_addr.called)
            self.assertFalse(mock_cli.return_value.ip_link.called)
            self.assertFalse(mock_cli.return_value.ethtool.called)

        self.assertTrue(iface_found)


class TestCLIHelper(utils.BaseTestCase):

    @mock.patch('hotsos.core.host_helpers.cli.HotSOSConfig')
    def test_cli_journalctl(self, mock_config):
        mock_config.DATA_ROOT = HotSOSConfig.DATA_ROOT
        mock_config.USE_ALL_LOGS = False
        mock_config.MAX_LOGROTATE_DEPTH = 7
        self.assertEqual(host_helpers.cli.JournalctlBase().since_date,
                         "2022-02-09")
        mock_config.USE_ALL_LOGS = True
        self.assertEqual(host_helpers.cli.JournalctlBase().since_date,
                         "2022-02-03")
        mock_config.MAX_LOGROTATE_DEPTH = 1000
        self.assertEqual(host_helpers.cli.JournalctlBase().since_date,
                         "2019-05-17")


class TestSystemdHelper(utils.BaseTestCase):

    def test_service_factory(self):
        svc = host_helpers.systemd.ServiceFactory().rsyslog
        self.assertEqual(svc.start_time_secs, 1644446297.0)

        self.assertEqual(host_helpers.systemd.ServiceFactory().noexist, None)


class TestFileStatHelper(utils.BaseTestCase):

    @utils.create_data_root({'foo': 'bar'})
    def test_filestat_factory(self):
        fpath = os.path.join(HotSOSConfig.DATA_ROOT, 'foo')
        fileobj = FileFactory().foo
        self.assertEqual(fileobj.mtime, os.path.getmtime(fpath))

        fileobj = FileFactory().noexist
        self.assertEqual(fileobj.mtime, 0)


class TestUptimeHelper(utils.BaseTestCase):

    def test_loadavg(self):
        self.assertEqual(host_helpers.UptimeHelper().loadavg,
                         "3.58, 3.27, 2.58")

    def test_uptime(self):
        self.assertEqual(host_helpers.UptimeHelper().seconds, 63660)
        self.assertEqual(host_helpers.UptimeHelper().hours, 17)

    @utils.create_data_root({'uptime': UPTIME_LONG_FORMAT})
    def test_uptime_alt_format(self):
        self.assertEqual(host_helpers.UptimeHelper().seconds, 109620)
        self.assertEqual(host_helpers.UptimeHelper().hours, 30)
