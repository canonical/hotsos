# Copyright 2016 Canonical Ltd
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from test_utils import CharmTestCase, patch_open
from test_pci_helper import (
    check_device,
    mocked_subprocess,
    mocked_filehandle,
    mocked_globs,
    mocked_islink,
    mocked_realpath,
)
from unittest.mock import patch, MagicMock
import pci

TO_PATCH = [
    'glob',
    'subprocess',
]
NOT_JSON = "Im not json"


class PCITest(CharmTestCase):

    def setUp(self):
        super(PCITest, self).setUp(pci, TO_PATCH)

    def test_format_pci_addr(self):
        self.assertEqual(pci.format_pci_addr('0:0:1.1'), '0000:00:01.1')
        self.assertEqual(pci.format_pci_addr(
            '0000:00:02.1'), '0000:00:02.1')


class PCINetDeviceTest(CharmTestCase):

    def setUp(self):
        super(PCINetDeviceTest, self).setUp(pci, TO_PATCH)

    @patch('os.path.islink')
    @patch('os.path.realpath')
    def eth_int(self, pci_address, _osrealpath, _osislink, subproc_map=None):
        self.glob.glob.side_effect = mocked_globs
        _osislink.side_effect = mocked_islink
        _osrealpath.side_effect = mocked_realpath
        self.subprocess.check_output.side_effect = mocked_subprocess(
            subproc_map=subproc_map)

        with patch_open() as (_open, _file):
            super_fh = mocked_filehandle()
            _file.readlines = MagicMock()
            _open.side_effect = super_fh._setfilename
            _file.read.side_effect = super_fh._getfilecontents_read
            _file.readlines.side_effect = super_fh._getfilecontents_readlines
            netint = pci.PCINetDevice(pci_address)
        return netint

    def test_base_eth_device(self):
        net = self.eth_int('0000:10:00.0')
        expect = {
            'interface_name': 'eth2',
            'mac_address': 'a8:9d:21:cf:93:fc',
            'pci_address': '0000:10:00.0',
            'state': 'up',
            'sriov': False,
        }
        self.assertTrue(check_device(net, expect))

    @patch('pci.get_sysnet_interfaces_and_macs')
    @patch('pci.PCINetDevice.update_attributes')
    def test_update_interface_info(self, _update, _sysnet_ints):
        dev = pci.PCINetDevice('0000:10:00.0')
        _sysnet_ints.return_value = [
            {
                'interface': 'eth2',
                'mac_address': 'a8:9d:21:cf:93:fc',
                'pci_address': '0000:10:00.0',
                'state': 'up',
                'sriov': False,
            },
            {
                'interface': 'eth3',
                'mac_address': 'a8:9d:21:cf:93:fd',
                'pci_address': '0000:10:00.1',
                'state': 'down',
                'sriov': False,
            }
        ]
        dev.update_interface_info()
        self.assertEqual(dev.interface_name, 'eth2')

    @patch('os.path.islink')
    @patch('os.path.realpath')
    @patch('pci.is_sriov')
    @patch('pci.get_sysnet_device_state')
    @patch('pci.get_sysnet_mac')
    @patch('pci.get_sysnet_interface')
    @patch('pci.PCINetDevice.update_attributes')
    def test_get_sysnet_interfaces_and_macs(self, _update, _interface, _mac,
                                            _state, _sriov, _osrealpath,
                                            _osislink):
        self.glob.glob.return_value = ['/sys/class/net/eth2']
        _interface.return_value = 'eth2'
        _mac.return_value = 'a8:9d:21:cf:93:fc'
        _state.return_value = 'up'
        _sriov.return_value = False
        _osrealpath.return_value = ('/sys/devices/pci0000:00/0000:00:02.0/'
                                    '0000:02:00.0/0000:03:00.0/0000:04:00.0/'
                                    '0000:05:01.0/0000:07:00.0')
        expect = {
            'interface': 'eth2',
            'mac_address': 'a8:9d:21:cf:93:fc',
            'pci_address': '0000:07:00.0',
            'state': 'up',
            'sriov': False,
        }
        self.assertEqual(pci.get_sysnet_interfaces_and_macs(), [expect])

    @patch('os.path.islink')
    @patch('os.path.realpath')
    @patch('pci.is_sriov')
    @patch('pci.get_sysnet_device_state')
    @patch('pci.get_sysnet_mac')
    @patch('pci.get_sysnet_interface')
    @patch('pci.PCINetDevice.update_attributes')
    def test_get_sysnet_interfaces_and_macs_virtio(self, _update, _interface,
                                                   _mac, _state, _sriov,
                                                   _osrealpath,
                                                   _osislink):
        self.glob.glob.return_value = ['/sys/class/net/eth2']
        _interface.return_value = 'eth2'
        _mac.return_value = 'a8:9d:21:cf:93:fc'
        _state.return_value = 'up'
        _sriov.return_value = False
        _osrealpath.return_value = ('/sys/devices/pci0000:00/0000:00:07.0/'
                                    'virtio5')
        expect = {
            'interface': 'eth2',
            'mac_address': 'a8:9d:21:cf:93:fc',
            'pci_address': '0000:00:07.0',
            'state': 'up',
            'sriov': False,
        }
        self.assertEqual(pci.get_sysnet_interfaces_and_macs(), [expect])

    @patch('pci.PCINetDevice.update_attributes')
    def test_get_sysnet_mac(self, _update):
        with patch_open() as (_open, _file):
            super_fh = mocked_filehandle()
            _file.readlines = MagicMock()
            _open.side_effect = super_fh._setfilename
            _file.read.side_effect = super_fh._getfilecontents_read
            macaddr = pci.get_sysnet_mac('/sys/class/net/eth3')
        self.assertEqual(macaddr, 'a8:9d:21:cf:93:fd')

    @patch('pci.PCINetDevice.update_attributes')
    def test_get_sysnet_device_state(self, _update):
        with patch_open() as (_open, _file):
            super_fh = mocked_filehandle()
            _file.readlines = MagicMock()
            _open.side_effect = super_fh._setfilename
            _file.read.side_effect = super_fh._getfilecontents_read
            state = pci.get_sysnet_device_state('/sys/class/net/eth3')
        self.assertEqual(state, 'down')

    @patch('pci.PCINetDevice.update_attributes')
    def test_get_sysnet_interface(self, _update):
        self.assertEqual(
            pci.get_sysnet_interface('/sys/class/net/eth3'), 'eth3')


class PCINetDevicesTest(CharmTestCase):

    def setUp(self):
        super(PCINetDevicesTest, self).setUp(pci, TO_PATCH)

    @patch('os.path.islink')
    def pci_devs(self, _osislink, subproc_map=None):
        self.glob.glob.side_effect = mocked_globs
        rp_patcher = patch('os.path.realpath')
        rp_mock = rp_patcher.start()
        rp_mock.side_effect = mocked_realpath
        _osislink.side_effect = mocked_islink
        self.subprocess.check_output.side_effect = mocked_subprocess(
            subproc_map=subproc_map)

        with patch_open() as (_open, _file):
            super_fh = mocked_filehandle()
            _file.readlines = MagicMock()
            _open.side_effect = super_fh._setfilename
            _file.read.side_effect = super_fh._getfilecontents_read
            _file.readlines.side_effect = super_fh._getfilecontents_readlines
            devices = pci.PCINetDevices()
        rp_patcher.stop()
        return devices

    def test_base(self):
        devices = self.pci_devs()
        self.assertEqual(len(devices.pci_devices), 2)
        expect = {
            '0000:10:00.0': {
                'interface_name': 'eth2',
                'mac_address': 'a8:9d:21:cf:93:fc',
                'pci_address': '0000:10:00.0',
                'state': 'up',
                'sriov': False,
            },
            '0000:10:00.1': {
                'interface_name': 'eth3',
                'mac_address': 'a8:9d:21:cf:93:fd',
                'pci_address': '0000:10:00.1',
                'state': 'down',
                'sriov': False,
            },
        }
        for device in devices.pci_devices:
            self.assertTrue(check_device(device, expect[device.pci_address]))

    def test_get_pci_ethernet_addresses(self):
        devices = self.pci_devs()
        expect = ['0000:10:00.0', '0000:10:00.1']
        self.assertEqual(devices.get_pci_ethernet_addresses(), expect)

    @patch('pci.PCINetDevice.update_attributes')
    def test_update_devices(self, _update):
        devices = self.pci_devs()
        call_count = _update.call_count
        devices.update_devices()
        self.assertEqual(_update.call_count, call_count + 2)

    def test_get_macs(self):
        devices = self.pci_devs()
        expect = ['a8:9d:21:cf:93:fc', 'a8:9d:21:cf:93:fd']
        self.assertEqual(devices.get_macs(), expect)

    def test_get_device_from_mac(self):
        devices = self.pci_devs()
        expect = {
            '0000:10:00.1': {
                'interface_name': 'eth3',
                'mac_address': 'a8:9d:21:cf:93:fd',
                'pci_address': '0000:10:00.1',
                'state': 'down',
                'sriov': False,
            },
        }
        self.assertTrue(check_device(
            devices.get_device_from_mac('a8:9d:21:cf:93:fd'),
            expect['0000:10:00.1']))

    def test_get_device_from_pci_address(self):
        devices = self.pci_devs()
        expect = {
            '0000:10:00.1': {
                'interface_name': 'eth3',
                'mac_address': 'a8:9d:21:cf:93:fd',
                'pci_address': '0000:10:00.1',
                'state': 'down',
            },
        }
        self.assertTrue(check_device(
            devices.get_device_from_pci_address('0000:10:00.1'),
            expect['0000:10:00.1']))
