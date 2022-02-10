# Copyright 2014-2015 Canonical Limited.
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
import re
from stat import S_ISBLK

from subprocess import (
    CalledProcessError,
    check_call,
    check_output,
    call
)


def _luks_uuid(dev):
    """
    Check to see if dev is a LUKS encrypted volume, returning the UUID
    of volume if it is.

    :param: dev: path to block device to check.
    :returns: str. UUID of LUKS device or None if not a LUKS device
    """
    try:
        cmd = ['cryptsetup', 'luksUUID', dev]
        return check_output(cmd).decode('UTF-8').strip()
    except CalledProcessError:
        return None


def is_luks_device(dev):
    """
    Determine if dev is a LUKS-formatted block device.

    :param: dev: A full path to a block device to check for LUKS header
    presence
    :returns: boolean: indicates whether a device is used based on LUKS header.
    """
    return True if _luks_uuid(dev) else False


def is_mapped_luks_device(dev):
    """
    Determine if dev is a mapped LUKS device
    :param: dev: A full path to a block device to be checked
    :returns: boolean: indicates whether a device is mapped
    """
    _, dirs, _ = next(os.walk(
        '/sys/class/block/{}/holders/'
        .format(os.path.basename(os.path.realpath(dev))))
    )
    is_held = len(dirs) > 0
    return is_held and is_luks_device(dev)


def is_block_device(path):
    '''
    Confirm device at path is a valid block device node.

    :returns: boolean: True if path is a block device, False if not.
    '''
    if not os.path.exists(path):
        return False
    return S_ISBLK(os.stat(path).st_mode)


def zap_disk(block_device):
    '''
    Clear a block device of partition table. Relies on sgdisk, which is
    installed as pat of the 'gdisk' package in Ubuntu.

    :param block_device: str: Full path of block device to clean.
    '''
    # https://github.com/ceph/ceph/commit/fdd7f8d83afa25c4e09aaedd90ab93f3b64a677b
    # sometimes sgdisk exits non-zero; this is OK, dd will clean up
    call(['sgdisk', '--zap-all', '--', block_device])
    call(['sgdisk', '--clear', '--mbrtogpt', '--', block_device])
    dev_end = check_output(['blockdev', '--getsz',
                            block_device]).decode('UTF-8')
    gpt_end = int(dev_end.split()[0]) - 100
    check_call(['dd', 'if=/dev/zero', 'of=%s' % (block_device),
                'bs=1M', 'count=1'])
    check_call(['dd', 'if=/dev/zero', 'of=%s' % (block_device),
                'bs=512', 'count=100', 'seek=%s' % (gpt_end)])


def is_device_mounted(device):
    '''Given a device path, return True if that device is mounted, and False
    if it isn't.

    :param device: str: Full path of the device to check.
    :returns: boolean: True if the path represents a mounted device, False if
        it doesn't.
    '''
    try:
        out = check_output(['lsblk', '-P', device]).decode('UTF-8')
    except Exception:
        return False
    return bool(re.search(r'MOUNTPOINT=".+"', out))


def mkfs_xfs(device, force=False, inode_size=1024):
    """Format device with XFS filesystem.

    By default this should fail if the device already has a filesystem on it.
    :param device: Full path to device to format
    :ptype device: tr
    :param force: Force operation
    :ptype: force: boolean
    :param inode_size: XFS inode size in bytes
    :ptype inode_size: int"""
    cmd = ['mkfs.xfs']
    if force:
        cmd.append("-f")

    cmd += ['-i', "size={}".format(inode_size), device]
    check_call(cmd)
