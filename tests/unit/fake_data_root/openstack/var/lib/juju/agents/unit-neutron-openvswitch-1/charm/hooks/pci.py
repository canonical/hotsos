#!/usr/bin/env python3
#
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

import os
import glob
import subprocess
import shlex


def format_pci_addr(pci_addr):
    domain, bus, slot_func = pci_addr.split(':')
    slot, func = slot_func.split('.')
    return '{}:{}:{}.{}'.format(domain.zfill(4), bus.zfill(2), slot.zfill(2),
                                func)


def get_sysnet_interfaces_and_macs():
    '''Catalog interface information from local system

    each device dict contains:

        interface: logical name
        mac_address: MAC address
        pci_address: PCI address
        state: Current interface state (up/down)
        sriov: Boolean indicating whether inteface is an SR-IOV
               capable device.
        sriov_totalvfs: Total VF capacity of device
        sriov_numvfs: Configured VF capacity of device

    :returns: array: of dict objects containing details of each interface
    '''
    net_devs = []
    for sdir in glob.glob('/sys/class/net/*'):
        sym_link = sdir + "/device"
        if os.path.islink(sym_link):
            fq_path = os.path.realpath(sym_link)
            path = fq_path.split('/')
            if 'virtio' in path[-1]:
                pci_address = path[-2]
            else:
                pci_address = path[-1]
            device = {
                'interface': get_sysnet_interface(sdir),
                'mac_address': get_sysnet_mac(sdir),
                'pci_address': pci_address,
                'state': get_sysnet_device_state(sdir),
                'sriov': is_sriov(sdir)
            }
            if device['sriov']:
                device['sriov_totalvfs'] = \
                    get_sriov_totalvfs(sdir)
                device['sriov_numvfs'] = \
                    get_sriov_numvfs(sdir)
            net_devs.append(device)

    return net_devs


def get_sysnet_mac(sysdir):
    '''Read MAC address for a device

    :sysdir: string: path to device /sys directory

    :returns: string: MAC address of device
    '''
    mac_addr_file = sysdir + '/address'
    with open(mac_addr_file, 'r') as f:
        read_data = f.read()
    mac = read_data.strip()
    return mac


def get_sysnet_device_state(sysdir):
    '''Read operational state of a device

    :sysdir: string: path to device /sys directory

    :returns: string: current device state
    '''
    state_file = sysdir + '/operstate'
    with open(state_file, 'r') as f:
        read_data = f.read()
    state = read_data.strip()
    return state


def is_sriov(sysdir):
    '''Determine whether a device is SR-IOV capable

    :sysdir: string: path to device /sys directory

    :returns: boolean: indicating whether device is SR-IOV
                       capable or not.
    '''
    return os.path.exists(os.path.join(sysdir,
                                       'device',
                                       'sriov_totalvfs'))


def get_sriov_totalvfs(sysdir):
    '''Read total VF capacity for a device

    :sysdir: string: path to device /sys directory

    :returns: int: number of VF's the device supports
    '''
    sriov_totalvfs_file = os.path.join(sysdir,
                                       'device',
                                       'sriov_totalvfs')
    with open(sriov_totalvfs_file, 'r') as f:
        read_data = f.read()
    sriov_totalvfs = int(read_data.strip())
    return sriov_totalvfs


def get_sriov_numvfs(sysdir):
    '''Read configured VF capacity for a device

    :sysdir: string: path to device /sys directory

    :returns: int: number of VF's the device is configured for
    '''
    sriov_numvfs_file = os.path.join(sysdir,
                                     'device',
                                     'sriov_numvfs')
    with open(sriov_numvfs_file, 'r') as f:
        read_data = f.read()
    sriov_numvfs = int(read_data.strip())
    return sriov_numvfs


def get_sysnet_interface(sysdir):
    return sysdir.split('/')[-1]


class PCINetDevice(object):

    def __init__(self, pci_address):
        self.pci_address = pci_address
        self.interface_name = None
        self.mac_address = None
        self.state = None
        self.sriov = False
        self.sriov_totalvfs = None
        self.sriov_numvfs = None
        self.update_attributes()

    def update_attributes(self):
        self.update_interface_info()

    def update_interface_info(self):
        net_devices = get_sysnet_interfaces_and_macs()
        for interface in net_devices:
            if self.pci_address == interface['pci_address']:
                self.interface_name = interface['interface']
                self.mac_address = interface['mac_address']
                self.state = interface['state']
                self.sriov = interface['sriov']
                if self.sriov:
                    self.sriov_totalvfs = interface['sriov_totalvfs']
                    self.sriov_numvfs = interface['sriov_numvfs']


class PCINetDevices(object):

    def __init__(self):
        pci_addresses = self.get_pci_ethernet_addresses()
        self.pci_devices = [PCINetDevice(dev) for dev in pci_addresses]

    def get_pci_ethernet_addresses(self):
        cmd = ['lspci', '-m', '-D']
        lspci_output = subprocess.check_output(cmd).decode('UTF-8')
        pci_addresses = []
        for line in lspci_output.split('\n'):
            columns = shlex.split(line)
            if len(columns) > 1 and columns[1] == 'Ethernet controller':
                pci_address = columns[0]
                pci_addresses.append(format_pci_addr(pci_address))
        return pci_addresses

    def update_devices(self):
        for pcidev in self.pci_devices:
            pcidev.update_attributes()

    def get_macs(self):
        macs = []
        for pcidev in self.pci_devices:
            if pcidev.mac_address:
                macs.append(pcidev.mac_address)
        return macs

    def get_device_from_mac(self, mac):
        for pcidev in self.pci_devices:
            if pcidev.mac_address == mac:
                return pcidev
        return None

    def get_device_from_pci_address(self, pci_addr):
        for pcidev in self.pci_devices:
            if pcidev.pci_address == pci_addr:
                return pcidev
        return None

    def get_device_from_interface_name(self, interface_name):
        for pcidev in self.pci_devices:
            if pcidev.interface_name == interface_name:
                return pcidev
        return None
