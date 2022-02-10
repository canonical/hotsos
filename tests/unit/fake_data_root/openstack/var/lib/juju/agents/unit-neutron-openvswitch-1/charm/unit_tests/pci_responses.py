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

# flake8: noqa
LSPCI = b"""
0000:00:00.0 "Host bridge" "Intel Corporation" "Haswell-E DMI2" -r02 "Intel Corporation" "Device 0000"
0000:00:03.0 "PCI bridge" "Intel Corporation" "Haswell-E PCI Express Root Port 3" -r02 "" ""
0000:00:03.2 "PCI bridge" "Intel Corporation" "Haswell-E PCI Express Root Port 3" -r02 "" ""
0000:00:05.0 "System peripheral" "Intel Corporation" "Haswell-E Address Map, VTd_Misc, System Management" -r02 "" ""
0000:00:05.1 "System peripheral" "Intel Corporation" "Haswell-E Hot Plug" -r02 "" ""
0000:00:05.2 "System peripheral" "Intel Corporation" "Haswell-E RAS, Control Status and Global Errors" -r02 "" ""
0000:00:05.4 "PIC" "Intel Corporation" "Haswell-E I/O Apic" -r02 -p20 "Intel Corporation" "Device 0000"
0000:00:11.0 "Unassigned class [ff00]" "Intel Corporation" "Wellsburg SPSR" -r05 "Intel Corporation" "Device 7270"
0000:00:11.4 "SATA controller" "Intel Corporation" "Wellsburg sSATA Controller [AHCI mode]" -r05 -p01 "Cisco Systems Inc" "Device 0067"
0000:00:16.0 "Communication controller" "Intel Corporation" "Wellsburg MEI Controller #1" -r05 "Intel Corporation" "Device 7270"
0000:00:16.1 "Communication controller" "Intel Corporation" "Wellsburg MEI Controller #2" -r05 "Intel Corporation" "Device 7270"
0000:00:1a.0 "USB controller" "Intel Corporation" "Wellsburg USB Enhanced Host Controller #2" -r05 -p20 "Intel Corporation" "Device 7270"
0000:00:1c.0 "PCI bridge" "Intel Corporation" "Wellsburg PCI Express Root Port #1" -rd5 "" ""
0000:00:1c.3 "PCI bridge" "Intel Corporation" "Wellsburg PCI Express Root Port #4" -rd5 "" ""
0000:00:1c.4 "PCI bridge" "Intel Corporation" "Wellsburg PCI Express Root Port #5" -rd5 "" ""
0000:00:1d.0 "USB controller" "Intel Corporation" "Wellsburg USB Enhanced Host Controller #1" -r05 -p20 "Intel Corporation" "Device 7270"
0000:00:1f.0 "ISA bridge" "Intel Corporation" "Wellsburg LPC Controller" -r05 "Intel Corporation" "Device 7270"
0000:00:1f.2 "SATA controller" "Intel Corporation" "Wellsburg 6-Port SATA Controller [AHCI mode]" -r05 -p01 "Cisco Systems Inc" "Device 0067"
0000:01:00.0 "PCI bridge" "Cisco Systems Inc" "VIC 82 PCIe Upstream Port" -r01 "" ""
0000:02:00.0 "PCI bridge" "Cisco Systems Inc" "VIC PCIe Downstream Port" -ra2 "" ""
0000:02:01.0 "PCI bridge" "Cisco Systems Inc" "VIC PCIe Downstream Port" -ra2 "" ""
0000:03:00.0 "Unclassified device [00ff]" "Cisco Systems Inc" "VIC Management Controller" -ra2 "Cisco Systems Inc" "Device 012e"
0000:04:00.0 "PCI bridge" "Cisco Systems Inc" "VIC PCIe Upstream Port" -ra2 "" ""
0000:05:00.0 "PCI bridge" "Cisco Systems Inc" "VIC PCIe Downstream Port" -ra2 "" ""
0000:05:01.0 "PCI bridge" "Cisco Systems Inc" "VIC PCIe Downstream Port" -ra2 "" ""
0000:05:02.0 "PCI bridge" "Cisco Systems Inc" "VIC PCIe Downstream Port" -ra2 "" ""
0000:05:03.0 "PCI bridge" "Cisco Systems Inc" "VIC PCIe Downstream Port" -ra2 "" ""
0000:08:00.0 "Fibre Channel" "Cisco Systems Inc" "VIC FCoE HBA" -ra2 "Cisco Systems Inc" "Device 012e"
0000:09:00.0 "Fibre Channel" "Cisco Systems Inc" "VIC FCoE HBA" -ra2 "Cisco Systems Inc" "Device 012e"
0000:0b:00.0 "RAID bus controller" "LSI Logic / Symbios Logic" "MegaRAID SAS-3 3108 [Invader]" -r02 "Cisco Systems Inc" "Device 00db"
0000:0f:00.0 "VGA compatible controller" "Matrox Electronics Systems Ltd." "MGA G200e [Pilot] ServerEngines (SEP1)" -r02 "Cisco Systems Inc" "Device 0101"
0000:10:00.0 "Ethernet controller" "Intel Corporation" "I350 Gigabit Network Connection" -r01 "Cisco Systems Inc" "Device 00d6"
0000:10:00.1 "Ethernet controller" "Intel Corporation" "I350 Gigabit Network Connection" -r01 "Cisco Systems Inc" "Device 00d6"
0000:7f:08.0 "System peripheral" "Intel Corporation" "Haswell-E QPI Link 0" -r02 "Intel Corporation" "Haswell-E QPI Link 0"
"""

SYS_TREE = {
    '/sys/class/net/eth2': '../../devices/pci0000:00/0000:00:1c.4/0000:10:00.0/net/eth2',
    '/sys/class/net/eth3': '../../devices/pci0000:00/0000:00:1c.4/0000:10:00.1/net/eth3',
    '/sys/class/net/juju-br0': '../../devices/virtual/net/juju-br0',
    '/sys/class/net/lo': '../../devices/virtual/net/lo',
    '/sys/class/net/lxcbr0': '../../devices/virtual/net/lxcbr0',
    '/sys/class/net/veth1GVRCF': '../../devices/virtual/net/veth1GVRCF',
    '/sys/class/net/veth7AXEUK': '../../devices/virtual/net/veth7AXEUK',
    '/sys/class/net/vethACOIJJ': '../../devices/virtual/net/vethACOIJJ',
    '/sys/class/net/vethMQ819H': '../../devices/virtual/net/vethMQ819H',
    '/sys/class/net/virbr0': '../../devices/virtual/net/virbr0',
    '/sys/class/net/virbr0-nic': '../../devices/virtual/net/virbr0-nic',
    '/sys/devices/pci0000:00/0000:00:1c.4/0000:10:00.0/net/eth2/device': '../../../0000:10:00.0',
    '/sys/devices/pci0000:00/0000:00:1c.4/0000:10:00.1/net/eth3/device': '../../../0000:10:00.1',
}

FILE_CONTENTS = {
    '/sys/class/net/eth2/address': 'a8:9d:21:cf:93:fc',
    '/sys/class/net/eth3/address': 'a8:9d:21:cf:93:fd',
    '/sys/class/net/eth2/operstate': 'up',
    '/sys/class/net/eth3/operstate': 'down',
}

COMMANDS = {
   'LSPCI_MD': ['lspci', '-m', '-D'],
}

NET_SETUP = {
    'LSPCI_MD': LSPCI,
}
