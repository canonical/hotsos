#!/usr/bin/python
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

import pci
from test_utils import patch_open
from unittest.mock import patch, MagicMock
import pci_responses
import os


def check_device(device, attr_dict):
    equal = device.interface_name == attr_dict['interface_name'] and \
        device.mac_address == attr_dict['mac_address'] and \
        device.pci_address == attr_dict['pci_address'] and \
        device.state == attr_dict['state']
    return equal


def mocked_subprocess(subproc_map=None):
    def _subproc(cmd, stdin=None):
        for key in pci_responses.COMMANDS.keys():
            if pci_responses.COMMANDS[key] == cmd:
                return subproc_map[key]
            elif pci_responses.COMMANDS[key] == cmd[:-1]:
                return subproc_map[cmd[-1]][key]

    if not subproc_map:
        subproc_map = pci_responses.NET_SETUP
    return _subproc


class mocked_filehandle(object):
    def _setfilename(self, fname, omode):
        self.FILENAME = fname

    def _getfilecontents_read(self):
        return pci_responses.FILE_CONTENTS[self.FILENAME]

    def _getfilecontents_readlines(self):
        return pci_responses.FILE_CONTENTS[self.FILENAME].split('\n')


def mocked_globs(path):
    check_path = path.rstrip('*').rstrip('/')
    dirs = []
    for sdir in pci_responses.SYS_TREE:
        if check_path in sdir:
            dirs.append(sdir)
    return dirs


def mocked_islink(link):
    resolved_relpath = mocked_resolve_link(link)
    if pci_responses.SYS_TREE.get(resolved_relpath):
        return True
    else:
        return False


def mocked_resolve_link(link):
    resolved_relpath = None
    for sdir in pci_responses.SYS_TREE:
        if sdir in link:
            rep_dir = "{}/{}".format(os.path.dirname(sdir),
                                     pci_responses.SYS_TREE[sdir])
            resolved_symlink = link.replace(sdir, rep_dir)
            resolved_relpath = os.path.abspath(resolved_symlink)
    return resolved_relpath


def mocked_realpath(link):
    resolved_link = mocked_resolve_link(link)
    return pci_responses.SYS_TREE[resolved_link]


@patch('pci.cached')
@patch('pci.log')
@patch('pci.subprocess.Popen')
@patch('pci.subprocess.check_output')
@patch('pci.glob.glob')
@patch('pci.os.path.islink')
def pci_devs(_osislink, _glob, _check_output, _Popen, _log,
             _cached, subproc_map=None):
    _glob.side_effect = mocked_globs
    _osislink.side_effect = mocked_islink
    _check_output.side_effect = mocked_subprocess(
        subproc_map=subproc_map)

    with patch_open() as (_open, _file), \
            patch('pci.os.path.realpath') as _realpath:
        super_fh = mocked_filehandle()
        _file.readlines = MagicMock()
        _open.side_effect = super_fh._setfilename
        _file.read.side_effect = super_fh._getfilecontents_read
        _file.readlines.side_effect = super_fh._getfilecontents_readlines
        _realpath.side_effect = mocked_realpath
        devices = pci.PCINetDevices()
    return devices
