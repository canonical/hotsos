from unittest import mock

from hotsos.core.host_helpers import cli as host_cli
from hotsos.core.host_helpers import network as host_network

from .. import utils


class TestHostNetworkingHelper(utils.BaseTestCase):
    """ Unit tests for networking helper. """
    def test_get_host_interfaces(self):
        expected = ['lo', 'ens3', 'ens4', 'ens5', 'ens6', 'ens7', 'ens8',
                    'ens9', 'br-ens3', 'ovs-system', 'br-tun', 'br-int',
                    'br-ex', 'br-data', 'lxdbr0', 'veth1883dceb@if16',
                    'veth5cc250bc@if18', 'veth396824c3@if20',
                    'vethe7aaf6c3@if22', 'veth59e22e6f@if24',
                    'veth8aa19e05@if26', 'veth0d284c32@if28',
                    'vxlan_sys_4789', 'tap0e778df8-ca']
        helper = host_network.HostNetworkingHelper()
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
        helper = host_network.HostNetworkingHelper()
        ifaces = helper.host_interfaces_all
        names = [iface.name for iface in ifaces]
        self.assertEqual(names, expected)

    def test_get_interface_with_addr_not_exists(self):
        helper = host_network.HostNetworkingHelper()
        iface = helper.get_interface_with_addr('1.2.3.4')
        self.assertIsNone(iface)

    def test_get_interface_with_addr_exists(self):
        expected = {'br-ens3': {
                        'addresses': ['10.0.0.128'],
                        'hwaddr': '22:c2:7b:1c:12:1b',
                        'mtu': 1500,
                        'state': 'UP',
                        'speed': 'unknown'}}
        helper = host_network.HostNetworkingHelper()
        iface = helper.get_interface_with_addr('10.0.0.128')
        self.assertEqual(iface.to_dict(), expected)

    @mock.patch.object(host_network, 'CLIHelper')
    def test_get_interface_with_speed_exists(self, mock_cli):
        cli = host_cli.CLIHelper()
        orig_ip_addr = cli.ip_addr()
        orig_ip_link = cli.ip_link()
        mock_cli.return_value = mock.MagicMock()
        mock_cli.return_value.ethtool.return_value = ['Speed: 100000Mb/s\n']
        mock_cli.return_value.ip_addr.return_value = orig_ip_addr
        mock_cli.return_value.ip_link.return_value = orig_ip_link
        expected = {'br-ens3': {'addresses': ['10.0.0.128'],
                                'hwaddr': '22:c2:7b:1c:12:1b',
                                'mtu': 1500,
                                'state': 'UP',
                                'speed': '100000Mb/s'}}
        helper = host_network.HostNetworkingHelper()
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
        helper = host_network.HostNetworkingHelper()
        iface = helper.get_interface_with_addr('10.0.0.128')
        self.assertEqual(iface.stats, expected)

    def test_get_interfaces_cached(self):
        helper = host_network.HostNetworkingHelper()
        _ = helper.host_interfaces_all
        ifaces = helper.cache.get('interfaces')  # pylint: disable=E1111
        expected = ['lo',
                    'ens3',
                    'ens4',
                    'ens5',
                    'ens6',
                    'ens7',
                    'ens8',
                    'ens9',
                    'br-ens3',
                    'ovs-system',
                    'br-tun',
                    'br-int',
                    'br-ex',
                    'br-data',
                    'lxdbr0',
                    'veth1883dceb@if16',
                    'veth5cc250bc@if18',
                    'veth396824c3@if20',
                    'vethe7aaf6c3@if22',
                    'veth59e22e6f@if24',
                    'veth8aa19e05@if26',
                    'veth0d284c32@if28',
                    'vxlan_sys_4789',
                    'tap0e778df8-ca']
        self.assertEqual([i['name'] for i in ifaces], expected)
        ns_ifaces = helper.cache.get('ns-interfaces')  # pylint: disable=E1111
        expected = [('lo',
                     'fip-32981f34-497a-4fae-914a-8576055c8d0d'),
                    ('fpr-984c22fd-6@if2',
                     'fip-32981f34-497a-4fae-914a-8576055c8d0d'),
                    ('fg-c8dcce74-c4',
                     'fip-32981f34-497a-4fae-914a-8576055c8d0d'),
                    ('lo', 'qrouter-984c22fd-64b3-4fa1-8ddd-87090f401ce5'),
                    ('rfp-984c22fd-6@if2',
                     'qrouter-984c22fd-64b3-4fa1-8ddd-87090f401ce5'),
                    ('qr-3a70b31c-3f',
                     'qrouter-984c22fd-64b3-4fa1-8ddd-87090f401ce5'),
                    ('lo', 'snat-984c22fd-64b3-4fa1-8ddd-87090f401ce5'),
                    ('ha-550dc175-c0',
                     'snat-984c22fd-64b3-4fa1-8ddd-87090f401ce5'),
                    ('qg-14f81a43-69',
                     'snat-984c22fd-64b3-4fa1-8ddd-87090f401ce5'),
                    ('sg-189f4c40-9d',
                     'snat-984c22fd-64b3-4fa1-8ddd-87090f401ce5')]
        self.assertEqual([(i['name'], i['namespace']) for i in ns_ifaces],
                         expected)

        addr = '10.0.0.128'
        iface = helper.get_interface_with_addr(addr)
        # do this to cache stats
        _ = iface.stats
        helper = host_network.HostNetworkingHelper()
        data = helper.cache_load('interfaces')
        iface_found = False
        for _iface in data:
            if _iface['name'] == iface.name:
                iface_found = True
                self.assertEqual(_iface['addresses'], [addr])

        with mock.patch.object(host_network, 'CLIHelper') as mock_cli:
            mock_cli.return_value = mock.MagicMock()
            helper = host_network.HostNetworkingHelper()
            iface = helper.get_interface_with_addr(addr)
            self.assertEqual(iface.addresses, [addr])
            # these should no longer be called
            self.assertFalse(mock_cli.return_value.ip_addr.called)
            self.assertFalse(mock_cli.return_value.ip_netns.called)
            self.assertFalse(mock_cli.return_value.ns_ip_addr.called)
            self.assertFalse(mock_cli.return_value.ip_link.called)
            self.assertFalse(mock_cli.return_value.ethtool.called)

        self.assertTrue(iface_found)

    def test_get_ns_interfaces(self):
        expected = ['lo', 'rfp-984c22fd-6@if2', 'qr-3a70b31c-3f']
        helper = host_network.HostNetworkingHelper()
        ns = 'qrouter-984c22fd-64b3-4fa1-8ddd-87090f401ce5'
        ifaces = helper.get_ns_interfaces(ns)
        names = [iface.name for iface in ifaces]
        self.assertEqual(names, expected)
