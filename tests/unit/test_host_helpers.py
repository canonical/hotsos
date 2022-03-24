import mock

from . import utils

from hotsos.core.cli_helpers import CLIHelper
from hotsos.core.host_helpers import HostNetworkingHelper


class TestHostNetworkingHelper(utils.BaseTestCase):

    def test_get_host_interfaces(self):
        expected = ['lo', 'ens3', 'ens4', 'ens5', 'ens6', 'ens7', 'ens8',
                    'ens9', 'br-ens3', 'ovs-system', 'br-tun', 'br-int',
                    'br-ex', 'br-data', 'lxdbr0', 'veth1883dceb@if16',
                    'veth5cc250bc@if18', 'veth396824c3@if20',
                    'vethe7aaf6c3@if22', 'veth59e22e6f@if24',
                    'veth8aa19e05@if26', 'veth0d284c32@if28',
                    'vxlan_sys_4789', 'tap0e778df8-ca']
        helper = HostNetworkingHelper()
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
        helper = HostNetworkingHelper()
        ifaces = helper.host_interfaces_all
        names = [iface.name for iface in ifaces]
        self.assertEqual(names, expected)

    def test_get_interface_with_addr_not_exists(self):
        helper = HostNetworkingHelper()
        iface = helper.get_interface_with_addr('1.2.3.4')
        self.assertIsNone(iface)

    def test_get_interface_with_addr_exists(self):
        expected = {'br-ens3': {
                        'addresses': ['10.0.0.128'],
                        'hwaddr': '22:c2:7b:1c:12:1b',
                        'state': 'UP',
                        'speed': 'unknown'}}
        helper = HostNetworkingHelper()
        iface = helper.get_interface_with_addr('10.0.0.128')
        self.assertEqual(iface.to_dict(), expected)

    @mock.patch('hotsos.core.cli_helpers.CLIHelper')
    def test_get_interface_with_speed_exists(self, mock_cli):
        cli = CLIHelper()
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
        helper = HostNetworkingHelper()
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
        helper = HostNetworkingHelper()
        iface = helper.get_interface_with_addr('10.0.0.128')
        self.assertEqual(iface.stats, expected)
