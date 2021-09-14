import utils

from core.host_helpers import HostNetworkingHelper


class TestHostHelpers(utils.BaseTestCase):

    def test_get_host_interfaces(self):
        expected = ['lo', 'ens3', 'ens4', 'ens5', 'ens6', 'ens7',
                    'ens8', 'ens9', 'br-ens3', 'ovs-system', 'vxlan_sys_4789',
                    'br-tun', 'br-ex', 'br-int', 'br-data', 'lxdbr0',
                    '1lxd0-0@if22', '1lxd1-0@if24', '1lxd2-0@if26',
                    '1lxd3-0@if28', 'tap03c4d61b-60', 'tap0906171f-17',
                    'bond1', 'br-bond1', 'bond1.4003@bond1']
        helper = HostNetworkingHelper()
        ifaces = helper.host_interfaces
        names = [iface.name for iface in ifaces]
        self.assertEqual(names, expected)

    def test_get_host_interfaces_w_ns(self):
        expected = ['lo', 'ens3', 'ens4', 'ens5', 'ens6', 'ens7',
                    'ens8', 'ens9', 'br-ens3', 'ovs-system', 'vxlan_sys_4789',
                    'br-tun', 'br-ex', 'br-int', 'br-data', 'lxdbr0',
                    '1lxd0-0@if22', '1lxd1-0@if24', '1lxd2-0@if26',
                    '1lxd3-0@if28', 'tap03c4d61b-60', 'tap0906171f-17',
                    'bond1', 'br-bond1', 'bond1.4003@bond1', 'lo',
                    'fpr-1e086be2-9@if2', 'fg-7450b342-b1', 'lo',
                    'fpr-1e086be2-9@if2', 'fg-7450b342-b1', 'lo',
                    'fpr-1e086be2-9@if2', 'fg-7450b342-b1', 'lo',
                    'fpr-1e086be2-9@if2', 'fg-7450b342-b1']
        helper = HostNetworkingHelper()
        ifaces = helper.host_interfaces_all
        names = [iface.name for iface in ifaces]
        self.assertEqual(names, expected)

    def test_get_interface_with_addr_not_exists(self):
        helper = HostNetworkingHelper()
        iface = helper.get_interface_with_addr('1.2.3.4')
        self.assertIsNone(iface)

    def test_get_interface_with_addr_exists(self):
        expected = {'br-ens3': {'addresses': ['10.0.0.49'],
                                'hwaddr': '52:54:00:e2:28:a3',
                                'state': 'UP'}}
        helper = HostNetworkingHelper()
        iface = helper.get_interface_with_addr('10.0.0.49')
        self.assertEqual(iface.to_dict(), expected)

    def test_get_interface_stats(self):
        expected = {'rx': {'dropped': 131579,
                           'errors': 0,
                           'overrun': 0,
                           'packets': 229792},
                    'tx': {'dropped': 0,
                           'errors': 0,
                           'packets': 216802}}
        helper = HostNetworkingHelper()
        iface = helper.get_interface_with_addr('10.0.0.49')
        self.assertEqual(iface.stats, expected)
